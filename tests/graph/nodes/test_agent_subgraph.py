from typing import ClassVar

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel
from structlog.testing import capture_logs

from graph.nodes.agent_subgraph import AgentLoopState, AgentSubgraph
from graph.nodes.node_names import NodeName
from graph.schemas import ToolCallRecord
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from tests.graph.nodes.conftest import FakeStructuredChatModel, make_fake_chat_model


class _StubSummary(BaseModel):
    note: str


class _StubAgentSubgraph(AgentSubgraph[_StubSummary]):
    """Test double: overrides `AgentSubgraph.__init__` to accept fake chat
    models directly (same pattern as `_FakePlannerNode` in conftest.py),
    and `prepare`/`finalize` are configurable per test rather than fixed
    logic — this file tests the base class's own machinery, not a real
    subclass's business logic (that's `test_researcher.py`'s job)."""

    name: ClassVar[NodeName] = NodeName.RESEARCHER
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="anthropic", model="claude-haiku-4-5-20251001"),
        fallback=LLMEndpointConfig(provider="openai", model="gpt-4o-mini"),
    )
    max_tool_calls: ClassVar[int] = 3
    summary_schema: ClassVar[type[BaseModel]] = _StubSummary

    def __init__(
        self,
        primary_model: FakeStructuredChatModel,
        fallback_model: FakeStructuredChatModel,
        prepare_result: list[BaseMessage] | None = None,
    ) -> None:
        self._tools = []
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._prepare_result = prepare_result
        self.finalize_calls: list[tuple[_StubSummary | None, list[ToolCallRecord]]] = []

    def prepare(self, state: TriageState) -> list[BaseMessage] | None:  # noqa: ARG002
        return self._prepare_result

    async def finalize(
        self,
        summary: _StubSummary | None,
        tool_calls: list[ToolCallRecord],
        state: TriageState,
    ) -> TriageStateUpdate:
        self.finalize_calls.append((summary, tool_calls))
        return TriageStateUpdate(status=state["status"])


def make_node(prepare_result: list[BaseMessage] | None = None) -> _StubAgentSubgraph:
    primary = make_fake_chat_model(
        model_name="claude-haiku-4-5-20251001", parsed_result=_StubSummary(note="found it")
    )
    fallback = make_fake_chat_model(model_name="gpt-4o-mini")
    return _StubAgentSubgraph(primary, fallback, prepare_result=prepare_result)


def make_loop_state(
    triage_state: TriageState,
    *,
    messages: list[BaseMessage] | None = None,
    summary: _StubSummary | None = None,
    summarize_cost: float = 0.0,
) -> AgentLoopState:
    return AgentLoopState(
        issue=triage_state["issue"],
        planner_output=triage_state["planner_output"],
        research_findings=triage_state["research_findings"],
        draft=triage_state["draft"],
        risk_assessment=triage_state["risk_assessment"],
        episodic_context=triage_state["episodic_context"],
        status=triage_state["status"],
        run_meta=triage_state["run_meta"],
        messages=messages or [],
        summary=summary,
        summarize_cost=summarize_cost,
    )


def test_prepare_node_with_none_short_circuits(triage_state: TriageState) -> None:
    node = make_node(prepare_result=None)
    update = node.prepare_node(make_loop_state(triage_state))
    assert update.get("messages") is None


def test_prepare_node_with_messages_populates_channel(triage_state: TriageState) -> None:
    message = HumanMessage(content="a message")
    node = make_node(prepare_result=[message])
    update = node.prepare_node(make_loop_state(triage_state))
    assert update.get("messages") == [message]


def test_route_after_prepare_short_circuits_to_assemble(triage_state: TriageState) -> None:
    node = make_node()
    route = node.route_after_prepare(make_loop_state(triage_state, messages=[]))
    assert route == "assemble"


def test_route_after_prepare_with_messages_goes_to_agent(triage_state: TriageState) -> None:
    node = make_node()
    route = node.route_after_prepare(
        make_loop_state(triage_state, messages=[HumanMessage(content="a message")])
    )
    assert route == "agent"


async def test_assemble_node_calls_finalize_with_derived_tool_calls(
    triage_state: TriageState,
) -> None:
    node = make_node()
    summary = _StubSummary(note="x")
    state = make_loop_state(triage_state, summary=summary, messages=[])

    await node.assemble_node(state)

    assert len(node.finalize_calls) == 1
    called_summary, called_tool_calls = node.finalize_calls[0]
    assert called_summary == summary
    assert called_tool_calls == []


async def test_assemble_node_bumps_iteration_count_and_tool_calls_made(
    triage_state: TriageState,
) -> None:
    node = make_node()
    state = make_loop_state(triage_state, summary=_StubSummary(note="x"), messages=[])

    update = await node.assemble_node(state)

    run_meta = update.get("run_meta")
    assert run_meta is not None
    assert run_meta.iteration_count == triage_state["run_meta"].iteration_count + 1
    assert run_meta.tool_calls_made == triage_state["run_meta"].tool_calls_made


async def test_assemble_node_logs_cap_hit_when_at_or_over_limit(triage_state: TriageState) -> None:
    node = make_node()
    messages: list[BaseMessage] = []
    for i in range(node.max_tool_calls):
        messages.append(
            AIMessage(
                content="",
                tool_calls=[{"name": "lookup", "args": {}, "id": f"call_{i}"}],
            )
        )
        messages.append(ToolMessage(content="ok", tool_call_id=f"call_{i}", status="success"))
    state = make_loop_state(triage_state, summary=_StubSummary(note="x"), messages=messages)

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        await node.assemble_node(state)

    finished = next(entry for entry in cap_logs if entry["event"] == "agent_subgraph_finished")
    assert finished["cap_hit"] is True
    assert finished["tool_call_count"] == node.max_tool_calls


async def test_assemble_node_does_not_log_cap_hit_under_limit(triage_state: TriageState) -> None:
    node = make_node()
    state = make_loop_state(triage_state, summary=_StubSummary(note="x"), messages=[])

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        await node.assemble_node(state)

    finished = next(entry for entry in cap_logs if entry["event"] == "agent_subgraph_finished")
    assert finished["cap_hit"] is False


async def test_summarize_node_parses_structured_output(triage_state: TriageState) -> None:
    node = make_node()
    state = make_loop_state(triage_state, messages=[])

    update = await node.summarize_node(state)

    assert update.get("summary") == _StubSummary(note="found it")
    assert (update.get("summarize_cost") or 0.0) >= 0.0
    assert update.get("messages") is None


async def test_summarize_node_tolerates_unresolved_tool_call(triage_state: TriageState) -> None:
    """Regression test: a parallel tool-call batch that straddles
    `max_tool_calls` can leave a call `ToolCallLimitMiddleware` counted as
    "allowed" with no matching `ToolMessage` (see
    `resolve_dangling_tool_calls`). `summarize_node` must patch the
    trajectory before calling out, or a real provider would reject the
    unresolved tool_call outright — this exercises that path end to end."""
    node = make_node()
    dangling_call = AIMessage(
        content="", tool_calls=[{"name": "search_code", "args": {}, "id": "call_1"}]
    )
    state = make_loop_state(triage_state, messages=[dangling_call])

    update = await node.summarize_node(state)

    assert update.get("summary") == _StubSummary(note="found it")


async def test_assemble_node_records_previously_dangling_tool_call(
    triage_state: TriageState,
) -> None:
    """The other half of the regression: once patched, the dangling call
    shows up in the derived records `finalize` receives, instead of
    silently vanishing (as it did before `resolve_dangling_tool_calls`)."""
    node = make_node()
    dangling_call = AIMessage(
        content="", tool_calls=[{"name": "search_code", "args": {}, "id": "call_1"}]
    )
    state = make_loop_state(triage_state, summary=_StubSummary(note="x"), messages=[dangling_call])

    await node.assemble_node(state)

    assert len(node.finalize_calls) == 1
    _, tool_calls = node.finalize_calls[0]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "search_code"
    assert tool_calls[0].status == "error"
