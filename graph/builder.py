import structlog
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.errors import BudgetExceededError
from graph.nodes import (
    ApprovalQueueNode,
    AutoPostNode,
    DrafterSubgraph,
    PlannerNode,
    ResearcherSubgraph,
    RiskCheckNode,
    SpamRejectedNode,
    route_after_auto_post,
    route_after_planner,
)
from graph.schemas import RunStatus
from graph.state import TriageState, TriageStateUpdate
from tools.sandbox import SandboxHandle
from utils.episodic_memory_store import BaseEpisodicMemoryStore, NullEpisodicMemoryStore

log = structlog.get_logger(__name__)


def handle_node_error(state: TriageState, error: NodeError) -> TriageStateUpdate:
    """Graph-wide error handler (see `set_node_defaults` below): converts
    any node's uncaught exception into a `RunError` + `status=FAILED`
    update, rather than crashing the run.

    `BudgetExceededError` (`graph/errors.py`) goes through this exact same
    conversion -- deliberately not a special propagation path -- but logs a
    distinct `budget_exceeded` event first, so a cost/iteration-budget abort
    is never confused with a real application bug when scanning traces/logs
    for `node_failed` events."""
    if isinstance(error.error, BudgetExceededError):
        log.error(
            "budget_exceeded",
            node=error.node,
            dimension=error.error.dimension,
            current=error.error.current,
            limit=error.error.limit,
            run_id=str(state["run_meta"].run_id),
            thread_id=state["run_meta"].thread_id,
        )
    else:
        log.error(
            "node_failed",
            node=error.node,
            error=str(error.error),
            run_id=str(state["run_meta"].run_id),
            thread_id=state["run_meta"].thread_id,
            exc_info=error.error,
        )
    updated_run_meta = state["run_meta"].with_error(
        node_name=error.node, error_message=str(error.error)
    )
    return TriageStateUpdate(status=RunStatus.FAILED, run_meta=updated_run_meta)


def build_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    *,
    researcher_tools: list[BaseTool] | None = None,
    drafter_tools: list[BaseTool] | None = None,
    drafter_sandbox_handle: SandboxHandle | None = None,
    memory_store: BaseEpisodicMemoryStore | None = None,
) -> CompiledStateGraph[TriageState]:
    """Wires the Planner -> Researcher -> Drafter -> Risk check -> Auto-post
    pipeline. From `planner`, `route_after_planner` conditionally routes a
    `SPAM_OR_ABUSE`-classified issue straight to `spam_rejected` (a graceful
    terminal outcome, `status=REJECTED`) instead of continuing into
    Researcher/Drafter/RiskCheck/AutoPost; every other `IssueType` continues
    to `researcher` as before. From `auto_post`, `route_after_auto_post`
    conditionally routes to `approval_queue` only when at least one drafted
    action was left queued (non-LOW risk); an all-LOW-risk run ends right
    after `auto_post` instead.

    Stays synchronous and does no I/O: `researcher_tools`/`drafter_tools`
    (MCP/Tavily tools, inherently async to load) are injected by the
    composition root (`main.py`, via `tools.mcp_clients.researcher_toolset()`
    and `tools.sandbox.sandbox_toolset()`) rather than loaded here — graph
    construction doing network calls would be an architecture smell, and this
    is also what keeps this function's own tests network-free. `None`/empty
    means a zero-tool node (still runs; for the Researcher that means low
    confidence, for the Drafter it's the normal case unless the sandboxed
    code-fix path is wired in). `drafter_sandbox_handle` is likewise an
    already-constructed handle (cheap, no I/O per `SandboxHandle`'s lazy
    `ensure_ready()` design) passed straight through to `DrafterSubgraph`,
    which reads it in `finalize()` to resolve a proposed code fix against the
    sandbox's recorded attempts. `AutoPostNode` similarly resolves its own
    `GitHubClient` internally (via `get_github_client()`), so it isn't
    threaded through here at all.

    `memory_store` is likewise already-constructed (`main.py` opens it via
    `utils.episodic_memory_store.episodic_memory_store()`, an async context
    manager -- the underlying `AsyncPostgresStore` connection pool needs real
    open/close lifecycle, unlike `GitHubClient`'s singleton) and defaults to
    a `NullEpisodicMemoryStore()` no-op when omitted. It's threaded into
    `PlannerNode` (reads similar past episodes), `AutoPostNode`,
    `ApprovalQueueNode`, and `SpamRejectedNode` (each writes a completed
    run's outcome back, `SpamRejectedNode` with `draft_actions=[]`/
    `risk_assessment=None`/`post_results=None` since a spam-rejected run
    never reaches drafting).

    Every simple node here is a `TriageNode` (see `graph/nodes/base.py`).
    The Researcher and the Drafter are `AgentSubgraph`s instead — their own
    compiled `StateGraph`s registered directly via
    `add_node(name, compiled_subgraph)`, bypassing `TriageNode` entirely so
    LangGraph's automatic subgraph detection (checkpoint namespacing, nested
    streaming) applies. They still get `handle_node_error` for free, since
    `set_node_defaults` applies to any node regardless of what its action is.
    """
    workflow = StateGraph(TriageState).set_node_defaults(  # pyright: ignore[reportUnknownMemberType]
        error_handler=handle_node_error,  # pyright: ignore[reportArgumentType]
    )

    # Nodes
    memory_store = memory_store or NullEpisodicMemoryStore()
    planner = PlannerNode(memory_store)
    spam_rejected = SpamRejectedNode(memory_store)
    researcher = ResearcherSubgraph(researcher_tools or [])
    drafter = DrafterSubgraph(drafter_tools or [], sandbox_handle=drafter_sandbox_handle)
    risk_check = RiskCheckNode()
    auto_post = AutoPostNode(memory_store)
    approval_queue = ApprovalQueueNode(memory_store)

    # Add nodes and edges. The Researcher's and Drafter's compiled subgraphs
    # are what get registered under their names, not the `AgentSubgraph`
    # instances themselves.
    workflow.add_node(planner.name, planner)  # pyright: ignore[reportUnknownMemberType]
    workflow.add_node(researcher.name, researcher.compile())  # pyright: ignore[reportUnknownMemberType]
    workflow.add_node(drafter.name, drafter.compile())  # pyright: ignore[reportUnknownMemberType]
    for node in (spam_rejected, risk_check, auto_post, approval_queue):
        workflow.add_node(node.name, node)  # pyright: ignore[reportUnknownMemberType]

    workflow.add_edge(START, planner.name)

    # Short circuit SPAM_OR_ABUSE issues straight to spam_rejected
    workflow.add_conditional_edges(planner.name, route_after_planner)  # pyright: ignore[reportUnknownMemberType]
    workflow.add_edge(spam_rejected.name, END)

    workflow.add_edge(researcher.name, drafter.name)
    workflow.add_edge(drafter.name, risk_check.name)
    workflow.add_edge(risk_check.name, auto_post.name)
    workflow.add_conditional_edges(auto_post.name, route_after_auto_post)  # pyright: ignore[reportUnknownMemberType]
    workflow.add_edge(approval_queue.name, END)

    return workflow.compile(checkpointer=checkpointer)  # pyright: ignore[reportUnknownMemberType]
