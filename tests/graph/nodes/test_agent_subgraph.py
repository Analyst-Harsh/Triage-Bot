from typing import ClassVar, Literal

import pytest
import structlog
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelFallbackMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel
from structlog.testing import capture_logs

import graph.nodes.agent_subgraph as agent_subgraph_module
from graph.errors import BudgetExceededError
from graph.nodes.agent_subgraph import AgentLoopState, AgentSubgraph
from graph.nodes.node_names import NodeName
from graph.nodes.utils.budget_guard_middleware import BudgetGuardMiddleware
from graph.schemas import ToolCallRecord
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from tests.graph.nodes.conftest import (
    FakeStructuredChatModel,
    RecordingNodeSpan,
    make_fake_chat_model,
)


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
    summary_schema: ClassVar[type[BaseModel]] = _StubSummary

    def __init__(
        self,
        primary_model: FakeStructuredChatModel,
        fallback_model: FakeStructuredChatModel,
        prepare_result: list[BaseMessage] | None = None,
    ) -> None:
        self._tools = []
        self.max_tool_calls = 3
        self._structured_output_max_attempts = 2
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
    summarize_cache_read_tokens: int = 0,
    summarize_cache_creation_tokens: int = 0,
) -> AgentLoopState:
    return AgentLoopState(
        issue=triage_state["issue"],
        planner_output=triage_state["planner_output"],
        research_findings=triage_state["research_findings"],
        draft=triage_state["draft"],
        risk_assessment=triage_state["risk_assessment"],
        post_results=triage_state["post_results"],
        episodic_context=triage_state["episodic_context"],
        status=triage_state["status"],
        run_meta=triage_state["run_meta"],
        messages=messages or [],
        summary=summary,
        summarize_cost=summarize_cost,
        summarize_cache_read_tokens=summarize_cache_read_tokens,
        summarize_cache_creation_tokens=summarize_cache_creation_tokens,
    )


def test_prepare_node_raises_budget_exceeded_before_prepare_when_already_over_budget(
    triage_state: TriageState,
) -> None:
    class _CountingStubAgentSubgraph(_StubAgentSubgraph):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            self.prepare_calls = 0

        def prepare(self, state: TriageState) -> list[BaseMessage] | None:
            self.prepare_calls += 1
            return super().prepare(state)

    primary = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    fallback = make_fake_chat_model(model_name="gpt-4o-mini")
    node = _CountingStubAgentSubgraph(primary, fallback)
    triage_state["run_meta"] = triage_state["run_meta"].model_copy(
        update={"estimated_cost_usd": triage_state["run_meta"].max_cost_usd}
    )

    with pytest.raises(BudgetExceededError) as exc_info:
        node.prepare_node(make_loop_state(triage_state))

    assert node.prepare_calls == 0
    assert exc_info.value.node_name == NodeName.RESEARCHER
    assert exc_info.value.dimension == "cost_usd"


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


async def test_assemble_node_accumulates_cache_tokens_from_trajectory_and_summarize(
    triage_state: TriageState,
) -> None:
    node = make_node()
    messages: list[BaseMessage] = [
        AIMessage(
            content="",
            usage_metadata={
                "input_tokens": 2000,
                "output_tokens": 50,
                "total_tokens": 2050,
                "input_token_details": {"cache_read": 1500, "cache_creation": 10},
            },
            response_metadata={"model_name": "gpt-4o-mini"},
        )
    ]
    state = make_loop_state(
        triage_state,
        summary=_StubSummary(note="x"),
        messages=messages,
        summarize_cache_read_tokens=100,
        summarize_cache_creation_tokens=5,
    )

    update = await node.assemble_node(state)

    run_meta = update.get("run_meta")
    assert run_meta is not None
    assert run_meta.cache_read_tokens == triage_state["run_meta"].cache_read_tokens + 1600
    assert run_meta.cache_creation_tokens == triage_state["run_meta"].cache_creation_tokens + 15


async def test_assemble_node_logs_cache_token_totals(triage_state: TriageState) -> None:
    node = make_node()
    messages: list[BaseMessage] = [
        AIMessage(
            content="",
            usage_metadata={
                "input_tokens": 2000,
                "output_tokens": 50,
                "total_tokens": 2050,
                "input_token_details": {"cache_read": 1500, "cache_creation": 0},
            },
            response_metadata={"model_name": "gpt-4o-mini"},
        )
    ]
    state = make_loop_state(triage_state, summary=_StubSummary(note="x"), messages=messages)

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        await node.assemble_node(state)

    finished = next(entry for entry in cap_logs if entry["event"] == "agent_subgraph_finished")
    assert finished["cache_read_tokens"] == 1500
    assert finished["cache_creation_tokens"] == 0
    assert finished["trajectory_cache_hit_ratio"] == pytest.approx(1500 / 2000)


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


async def test_assemble_node_wraps_finalize_in_a_node_span_named_after_the_node(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = RecordingNodeSpan()
    monkeypatch.setattr(agent_subgraph_module, "node_span", recording)
    node = make_node()
    state = make_loop_state(triage_state, summary=_StubSummary(note="x"), messages=[])

    await node.assemble_node(state)

    assert len(recording.spans) == 1
    assert recording.spans[0].name == NodeName.RESEARCHER


async def test_assemble_node_enriches_span_with_authoritative_usage_metadata(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = RecordingNodeSpan()
    monkeypatch.setattr(agent_subgraph_module, "node_span", recording)
    node = make_node()
    messages: list[BaseMessage] = [
        AIMessage(
            content="",
            tool_calls=[{"name": "lookup", "args": {}, "id": "call_0"}],
            usage_metadata={
                "input_tokens": 2000,
                "output_tokens": 50,
                "total_tokens": 2050,
                "input_token_details": {"cache_read": 1500, "cache_creation": 0},
            },
            response_metadata={"model_name": "gpt-4o-mini"},
        ),
        ToolMessage(content="ok", tool_call_id="call_0", status="success"),
    ]
    state = make_loop_state(triage_state, summary=_StubSummary(note="x"), messages=messages)

    await node.assemble_node(state)

    span = recording.spans[0]
    assert len(span.update_calls) == 1
    metadata = span.update_calls[0]["metadata"]
    assert metadata["tool_call_count"] == 1
    assert metadata["tools_used"] == ["lookup"]
    assert metadata["authoritative_cache_read_tokens"] == 1500
    assert metadata["cap_hit"] is False


async def test_summarize_node_raises_budget_exceeded_before_calling_model(
    triage_state: TriageState,
) -> None:
    """`summarize_node`'s LLM call sits outside both `prepare_node`'s entry
    check and `BudgetGuardMiddleware` (which only wraps the create_agent
    loop) -- this proves it re-checks on its own, before the model is ever
    called."""
    node = make_node()
    triage_state["run_meta"] = triage_state["run_meta"].model_copy(
        update={"estimated_cost_usd": triage_state["run_meta"].max_cost_usd}
    )
    state = make_loop_state(triage_state, messages=[])

    with pytest.raises(BudgetExceededError) as exc_info:
        await node.summarize_node(state)

    assert exc_info.value.node_name == NodeName.RESEARCHER
    assert exc_info.value.dimension == "cost_usd"
    assert node._primary_model.received_messages == []  # pyright: ignore[reportPrivateUsage]


async def test_summarize_node_parses_structured_output(triage_state: TriageState) -> None:
    node = make_node()
    state = make_loop_state(triage_state, messages=[])

    update = await node.summarize_node(state)

    assert update.get("summary") == _StubSummary(note="found it")
    assert (update.get("summarize_cost") or 0.0) >= 0.0
    assert update.get("messages") is None


async def test_summarize_node_defaults_to_function_calling_method(
    triage_state: TriageState,
) -> None:
    """`summary_schema_method` defaults to `"function_calling"` on the base
    class -- the safe choice for any subclass whose `summary_schema` might
    contain a discriminated union (e.g. `DrafterSubgraph`'s `DraftProposal`).
    A subclass with no such union (e.g. `ResearcherSubgraph`) overrides it."""
    node = make_node()
    state = make_loop_state(triage_state, messages=[])

    await node.summarize_node(state)

    assert node._primary_model.received_structured_output_kwargs == [  # pyright: ignore[reportPrivateUsage]
        {"method": "function_calling"}
    ]


class _StubAgentSubgraphJsonSchema(_StubAgentSubgraph):
    """Same as `_StubAgentSubgraph`, but overriding `summary_schema_method`
    -- the same override shape `ResearcherSubgraph` uses in production."""

    summary_schema_method: ClassVar[Literal["function_calling", "json_schema"]] = "json_schema"


async def test_summarize_node_forwards_overridden_schema_method(
    triage_state: TriageState,
) -> None:
    """A subclass overriding `summary_schema_method` (e.g. `ResearcherSubgraph`
    setting it to `"json_schema"`) must have that value actually reach
    `with_structured_output`, not just `function_calling`'s default."""
    primary = make_fake_chat_model(
        model_name="claude-haiku-4-5-20251001", parsed_result=_StubSummary(note="found it")
    )
    fallback = make_fake_chat_model(model_name="gpt-4o-mini")
    node = _StubAgentSubgraphJsonSchema(primary, fallback)
    state = make_loop_state(triage_state, messages=[])

    await node.summarize_node(state)

    assert primary.received_structured_output_kwargs == [{"method": "json_schema"}]


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


# ---------------------------------------------------------------------------
# Context-editing middleware (token bloat mitigation)
# ---------------------------------------------------------------------------


def test_middleware_order_starts_budget_guard_then_context_editing() -> None:
    node = make_node()

    middleware = node._middleware()  # pyright: ignore[reportPrivateUsage]

    assert isinstance(middleware[0], BudgetGuardMiddleware)
    assert isinstance(middleware[1], ContextEditingMiddleware)
    assert isinstance(middleware[2], ToolCallLimitMiddleware)
    assert isinstance(middleware[3], ModelFallbackMiddleware)


def test_middleware_context_editing_uses_expected_constants() -> None:
    node = make_node()

    middleware = node._middleware()  # pyright: ignore[reportPrivateUsage]

    context_editing = middleware[1]
    assert isinstance(context_editing, ContextEditingMiddleware)
    edit = context_editing.edits[0]
    assert isinstance(edit, ClearToolUsesEdit)
    assert edit.trigger == node.context_edit_trigger_tokens
    assert edit.keep == node.context_edit_keep_tool_results
    assert edit.placeholder == node.context_edit_placeholder


def test_middleware_context_editing_respects_subclass_override() -> None:
    """Proves the constants are read from `self`, not hardcoded twice."""

    class _OverriddenStubAgentSubgraph(_StubAgentSubgraph):
        context_edit_trigger_tokens: ClassVar[int] = 5
        context_edit_keep_tool_results: ClassVar[int] = 1
        context_edit_placeholder: ClassVar[str] = "[custom placeholder]"

    primary = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    fallback = make_fake_chat_model(model_name="gpt-4o-mini")
    node = _OverriddenStubAgentSubgraph(primary, fallback)

    context_editing = node._middleware()[1]  # pyright: ignore[reportPrivateUsage]
    assert isinstance(context_editing, ContextEditingMiddleware)
    edit = context_editing.edits[0]
    assert isinstance(edit, ClearToolUsesEdit)
    assert edit.trigger == 5
    assert edit.keep == 1
    assert edit.placeholder == "[custom placeholder]"


async def test_summarize_node_sends_clamped_messages_to_model(triage_state: TriageState) -> None:
    """`summarize_node` sits outside `build_agent()`'s create_agent loop, so
    `ContextEditingMiddleware` never runs over it -- this exercises the
    separate clamping pass it applies itself (`clamp_trajectory_for_model_call`),
    proving old tool results are cleared before the structured-output call,
    the most recent `keep` are preserved, and the checkpointed `state["messages"]`
    is never mutated in the process."""

    class _LowTriggerStubAgentSubgraph(_StubAgentSubgraph):
        context_edit_trigger_tokens: ClassVar[int] = 10
        context_edit_keep_tool_results: ClassVar[int] = 2
        context_edit_placeholder: ClassVar[str] = "[cleared]"

    primary = make_fake_chat_model(
        model_name="claude-haiku-4-5-20251001", parsed_result=_StubSummary(note="found it")
    )
    fallback = make_fake_chat_model(model_name="gpt-4o-mini")
    node = _LowTriggerStubAgentSubgraph(primary, fallback)

    messages: list[BaseMessage] = []
    original_contents: list[str] = []
    for i in range(5):
        content = f"result-{i}-" + ("x" * 200)
        original_contents.append(content)
        messages.append(
            AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": f"call_{i}"}])
        )
        messages.append(ToolMessage(content=content, tool_call_id=f"call_{i}", status="success"))
    state = make_loop_state(triage_state, messages=messages)

    await node.summarize_node(state)

    assert len(primary.received_messages) == 1
    sent = primary.received_messages[0]
    sent_tool_messages = [msg for msg in sent if isinstance(msg, ToolMessage)]
    assert len(sent_tool_messages) == 5
    # Oldest 3 (keep=2 preserves only the most recent 2) are cleared.
    assert [msg.content for msg in sent_tool_messages[:3]] == ["[cleared]"] * 3
    # Most recent 2 keep their original content.
    assert [msg.content for msg in sent_tool_messages[3:]] == original_contents[3:]

    # The checkpointed trajectory itself was never mutated.
    original_tool_messages = [msg for msg in state["messages"] if isinstance(msg, ToolMessage)]
    assert [msg.content for msg in original_tool_messages] == original_contents
