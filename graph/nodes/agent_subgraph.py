from abc import ABC, abstractmethod
from typing import Annotated, ClassVar, TypedDict, cast

import structlog
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.middleware import ModelFallbackMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from config.settings import get_settings
from graph.nodes.node_names import NodeName
from graph.nodes.trajectory import derive_tool_call_records, estimate_trajectory_cost
from graph.schemas import ToolCallRecord
from graph.state import TriageState, TriageStateUpdate
from llm.config import NodeLLMConfig
from llm.factory import create_chat_model
from llm.structured import call_structured

log = structlog.get_logger(__name__)


class AgentLoopState(TriageState):
    """`TriageState` plus private trajectory-bridging channels. None of
    these keys exist on `TriageState` itself, so they start empty/absent
    every run and never propagate back to the parent graph — each agent-loop
    node owns its own trajectory, with no cross-node scoping to manage (see
    the "Messages scoping" note in `AGENTS.md`).

    `summary` is typed loosely (`BaseModel | None`) rather than generically:
    it's purely internal bridging between this module's own `_summarize_node`
    and `_assemble_node`, never seen by subclass authors directly — they get
    the properly-typed `SummaryT` via `finalize()`'s signature instead (see
    the `cast` in `_assemble_node`).
    """

    messages: Annotated[list[BaseMessage], add_messages]
    summary: BaseModel | None
    summarize_cost: float


class _LoopUpdate(TypedDict, total=False):
    """Partial-update contract for this module's own nodes (`prepare`,
    `summarize`) — mirrors `TriageStateUpdate`'s total=False convention."""

    messages: list[BaseMessage]
    summary: BaseModel | None
    summarize_cost: float


class AgentSubgraph[SummaryT: BaseModel](ABC):
    """Subgraph-level counterpart to `TriageNode`, for nodes whose logic is
    an LLM tool-calling loop rather than a single call. `TriageNode` can't be
    reused directly here: LangGraph's subgraph detection (checkpoint
    namespacing, nested streaming) requires the loop to be its own compiled
    `StateGraph`, registered directly via `add_node()` — wrapping a
    `.invoke()` call inside a `TriageNode.execute()` body would silently
    defeat that detection (see `TriageNode`'s docstring in `base.py`). So
    this class's product is a compiled graph, not an executed result:
    `compile()` returns a `CompiledStateGraph` for the caller to
    `add_node(name, ...)` directly, exactly like a plain `TriageNode`
    instance.

    Concrete subclasses supply only two hooks — `prepare` (build the initial
    trajectory message, or short-circuit) and `finalize` (map the parsed
    summary into the node's own output slot). Everything else — the
    tool-call cap, the post-loop structured summary call, run-meta
    bookkeeping, structured logging — is uniform machinery on this base,
    mirroring how `TriageNode.__call__` is uniform over every simple node.
    """

    name: ClassVar[NodeName]
    llm_config: ClassVar[NodeLLMConfig]
    max_tool_calls: ClassVar[int]
    summary_schema: ClassVar[type[BaseModel]]

    def __init__(self, tools: list[BaseTool]) -> None:
        """Tools are injected (loaded by the composition root — see
        `tools/mcp_clients.py`), not constructed here: graph/subgraph
        construction must stay side-effect-free, and MCP tool loading is
        inherently I/O."""
        settings = get_settings()
        self._tools = tools
        self._settings = settings
        self._primary_model = create_chat_model(self.llm_config.primary, settings)
        self._fallback_model = create_chat_model(self.llm_config.fallback, settings)

    def system_prompt(self) -> str | None:
        """Static system prompt for the tool-calling loop, built from
        `self._tools` (already loaded by `__init__`) so it can name what's
        actually available this run. `None` (the default) means the model's
        own default system behavior — override when a node needs to frame
        its task and tool set explicitly, which every real subclass does."""
        return None

    @abstractmethod
    def prepare(self, state: TriageState) -> list[BaseMessage] | None:
        """Build the initial trajectory message(s) for this run, or return
        `None` to short-circuit: skip the tool-calling loop *and* the
        `summarize` LLM call entirely (e.g. the Planner already decided no
        investigation is warranted) — `finalize` then receives `summary=None`
        and must build minimal output programmatically, at zero LLM/tool
        spend."""
        raise NotImplementedError

    @abstractmethod
    def finalize(
        self,
        summary: SummaryT | None,
        tool_calls: list[ToolCallRecord],
        state: TriageState,
    ) -> TriageStateUpdate:
        """Map the parsed summary (or `None`, on the short-circuit path) plus
        the derived tool-call records into this node's output slot and
        `status`. Run-meta bookkeeping (cost, `tool_calls_made`,
        `iteration_count`) is applied by `_assemble_node` after this
        returns — don't set `run_meta` here; a `run_meta` update this method
        does set is still respected as the base to accumulate onto (same
        contract as `TriageNode.execute()`)."""
        raise NotImplementedError

    def compile(self) -> CompiledStateGraph[AgentLoopState, None, AgentLoopState, AgentLoopState]:
        """Returns a compiled graph over `AgentLoopState`, for the caller to
        `add_node(name, ...)` directly into a `TriageState`-schema parent
        graph. Only keys the two schemas share (`issue`, `planner_output`,
        `research_findings`, ..., `run_meta`) flow across that boundary in
        either direction — LangGraph's subgraph nesting matches state by key
        name, not by declared schema type, so `messages`/`summary`/
        `summarize_cost` here stay private to this subgraph."""
        graph = StateGraph(AgentLoopState)
        graph.add_node("prepare", self.prepare_node)  # pyright: ignore[reportUnknownMemberType]
        graph.add_node("agent", self.build_agent())  # pyright: ignore[reportUnknownMemberType]
        graph.add_node("summarize", self.summarize_node)  # pyright: ignore[reportUnknownMemberType]
        graph.add_node("assemble", self.assemble_node)  # pyright: ignore[reportUnknownMemberType]
        graph.add_edge(START, "prepare")
        graph.add_conditional_edges(  # pyright: ignore[reportUnknownMemberType]
            "prepare", self.route_after_prepare, {"agent": "agent", "assemble": "assemble"}
        )
        graph.add_edge("agent", "summarize")
        graph.add_edge("summarize", "assemble")
        graph.add_edge("assemble", END)
        return graph.compile()  # pyright: ignore[reportUnknownMemberType]

    def prepare_node(self, state: AgentLoopState) -> _LoopUpdate:
        """Graph-node wrapper around `prepare()`. Not underscore-prefixed:
        it's the template-method contact point tests exercise directly (see
        `tests/graph/nodes/test_agent_subgraph.py`), the same way
        `TriageNode.execute()` is a public override point despite existing
        purely to be called by graph wiring."""
        log.info("agent_subgraph_started", node=self.name)
        initial_messages = self.prepare(state)
        if initial_messages is None:
            return _LoopUpdate()
        return _LoopUpdate(messages=initial_messages)

    def route_after_prepare(self, state: AgentLoopState) -> str:
        return "agent" if state["messages"] else "assemble"

    def build_agent(
        self,
    ) -> CompiledStateGraph[AgentLoopState, None, AgentLoopState, AgentLoopState]:
        # create_agent's overloads / AgentMiddleware's generics don't line up
        # cleanly with a mixed middleware list under strict pyright — same
        # category of third-party stub incompleteness as the ChatAnthropic/
        # ChatOpenAI `reportCallIssue` ignores in llm/factory.py, verified
        # working at runtime (see the spike in the implementation plan).
        middleware = [
            ToolCallLimitMiddleware(run_limit=self.max_tool_calls, exit_behavior="end"),
            ModelFallbackMiddleware(self._fallback_model),
        ]
        return create_agent(  # pyright: ignore[reportCallIssue, reportUnknownVariableType]
            self._primary_model,
            tools=self._tools,
            system_prompt=self.system_prompt(),
            middleware=middleware,  # pyright: ignore[reportArgumentType]
        )

    async def summarize_node(self, state: AgentLoopState) -> _LoopUpdate:
        result = await call_structured(
            self._primary_model, self._fallback_model, state["messages"], self.summary_schema
        )
        return _LoopUpdate(summary=result.parsed, summarize_cost=result.estimated_cost_usd)

    def assemble_node(self, state: AgentLoopState) -> TriageStateUpdate:
        tool_calls = derive_tool_call_records(state["messages"])
        trajectory_cost = estimate_trajectory_cost(state["messages"])
        summarize_cost = state.get("summarize_cost", 0.0)
        # Set by summarize_node with `self.summary_schema`, so this is
        # always either None (short-circuit path) or a SummaryT instance —
        # a cast, not a runtime check, since pydantic already validated it
        # against summary_schema when call_structured parsed it.
        summary = cast(SummaryT | None, state.get("summary"))

        update = self.finalize(summary, tool_calls, state)

        run_meta = update.get("run_meta", state["run_meta"])
        cap_hit = len(tool_calls) >= self.max_tool_calls
        total_cost = run_meta.estimated_cost_usd + trajectory_cost + summarize_cost
        update["run_meta"] = run_meta.model_copy(
            update={
                "estimated_cost_usd": total_cost,
                "tool_calls_made": run_meta.tool_calls_made + len(tool_calls),
                "iteration_count": run_meta.iteration_count + 1,
            }
        )
        log.info(
            "agent_subgraph_finished",
            node=self.name,
            tool_call_count=len(tool_calls),
            tools_used=sorted({call.tool_name for call in tool_calls}),
            cost_usd=trajectory_cost + summarize_cost,
            cap_hit=cap_hit,
        )
        return update
