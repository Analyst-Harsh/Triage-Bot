from typing import ClassVar

import pytest
import structlog
from structlog.testing import capture_logs

import graph.nodes.base as base_module
from graph.errors import BudgetExceededError
from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.state import TriageState, TriageStateUpdate
from tests.graph.nodes.conftest import RecordingNodeSpan


class _StubNode(TriageNode):
    # Never registered into a real graph — reusing a real NodeName here (as
    # opposed to an arbitrary string) is just to satisfy TriageNode.name's
    # ClassVar[NodeName] override under strict pyright.
    name: ClassVar[NodeName] = NodeName.PLANNER

    async def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        return TriageStateUpdate()


class _NodeWithOwnRunMeta(TriageNode):
    """A node whose execute() already sets run_meta, to exercise the
    update.get("run_meta", state["run_meta"]) branch in __call__."""

    name: ClassVar[NodeName] = NodeName.RESEARCHER

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        custom_meta = state["run_meta"].model_copy(update={"tool_calls_made": 5})
        return TriageStateUpdate(run_meta=custom_meta)


class _RaisingNode(TriageNode):
    name: ClassVar[NodeName] = NodeName.DRAFTER

    async def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        raise ValueError("boom")


class _NodeWithCost(TriageNode):
    """A node whose execute() reports cost/cache-token usage, to exercise
    the authoritative_* deltas __call__ attaches to its node span."""

    name: ClassVar[NodeName] = NodeName.RISK_CHECK

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        updated = state["run_meta"].with_usage(cost_usd=0.05, cache_read_tokens=200)
        return TriageStateUpdate(run_meta=updated)


class _NodeWithNewError(TriageNode):
    """A node whose execute() appends a RunError without raising -- e.g.
    AutoPostNode/ApprovalQueueNode on a real GitHub post failure -- to
    exercise __call__'s level="ERROR" span enrichment."""

    name: ClassVar[NodeName] = NodeName.AUTO_POST

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        updated = state["run_meta"].with_error(
            node_name=self.name, error_message="2 action(s) failed to post"
        )
        return TriageStateUpdate(run_meta=updated)


class _CountingNode(TriageNode):
    """Tracks whether execute() actually ran, to prove check_budget's
    placement gates it rather than merely running alongside it."""

    name: ClassVar[NodeName] = NodeName.PLANNER

    def __init__(self) -> None:
        self.execute_calls = 0

    async def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        self.execute_calls += 1
        return TriageStateUpdate()


async def test_call_raises_budget_exceeded_before_execute_when_cost_already_at_ceiling(
    triage_state: TriageState,
) -> None:
    triage_state["run_meta"] = triage_state["run_meta"].model_copy(
        update={"estimated_cost_usd": triage_state["run_meta"].max_cost_usd}
    )
    node = _CountingNode()

    with pytest.raises(BudgetExceededError) as exc_info:
        await node(triage_state)

    assert node.execute_calls == 0
    assert exc_info.value.node_name == NodeName.PLANNER
    assert exc_info.value.dimension == "cost_usd"


async def test_call_raises_budget_exceeded_before_execute_when_iterations_already_at_ceiling(
    triage_state: TriageState,
) -> None:
    triage_state["run_meta"] = triage_state["run_meta"].model_copy(
        update={"iteration_count": triage_state["run_meta"].max_iterations}
    )
    node = _CountingNode()

    with pytest.raises(BudgetExceededError) as exc_info:
        await node(triage_state)

    assert node.execute_calls == 0
    assert exc_info.value.dimension == "iterations"


async def test_call_bumps_iteration_count_on_success(triage_state: TriageState) -> None:
    node = _StubNode()
    update = await node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].iteration_count == triage_state["run_meta"].iteration_count + 1


async def test_call_does_not_mutate_original_run_meta(triage_state: TriageState) -> None:
    node = _StubNode()
    await node(triage_state)

    assert triage_state["run_meta"].iteration_count == 0


async def test_call_increments_iteration_count_on_run_meta_returned_by_execute(
    triage_state: TriageState,
) -> None:
    node = _NodeWithOwnRunMeta()
    update = await node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].tool_calls_made == 5
    assert update["run_meta"].iteration_count == triage_state["run_meta"].iteration_count + 1


async def test_call_propagates_exception_from_execute(triage_state: TriageState) -> None:
    node = _RaisingNode()

    with pytest.raises(ValueError, match="boom"):
        await node(triage_state)


async def test_call_binds_run_correlation_context_for_logging(triage_state: TriageState) -> None:
    node = _StubNode()

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        await node(triage_state)

    run_meta = triage_state["run_meta"]
    started = next(entry for entry in cap_logs if entry["event"] == "node_started")
    assert started["run_id"] == str(run_meta.run_id)
    assert started["thread_id"] == run_meta.thread_id
    assert started["trace_id"] == run_meta.trace_id
    assert started["node"] == NodeName.PLANNER


async def test_call_logs_node_finished_with_duration(triage_state: TriageState) -> None:
    node = _StubNode()

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        await node(triage_state)

    finished = next(entry for entry in cap_logs if entry["event"] == "node_finished")
    assert finished["node"] == NodeName.PLANNER
    assert isinstance(finished["duration_ms"], float)
    assert finished["duration_ms"] >= 0


async def test_call_wraps_execute_in_a_node_span_named_after_the_node(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = RecordingNodeSpan()
    monkeypatch.setattr(base_module, "node_span", recording)
    node = _StubNode()

    await node(triage_state)

    assert len(recording.spans) == 1
    assert recording.spans[0].name == NodeName.PLANNER


async def test_call_enriches_node_span_with_duration_and_authoritative_cost(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = RecordingNodeSpan()
    monkeypatch.setattr(base_module, "node_span", recording)
    node = _NodeWithCost()

    await node(triage_state)

    span = recording.spans[0]
    assert len(span.update_calls) == 1
    metadata = span.update_calls[0]["metadata"]
    assert isinstance(metadata["duration_ms"], float)
    assert metadata["duration_ms"] >= 0
    assert metadata["authoritative_cost_usd_delta"] == pytest.approx(0.05)
    assert metadata["authoritative_cache_read_tokens_delta"] == 200


async def test_call_marks_span_error_level_when_execute_appends_a_run_error_without_raising(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = RecordingNodeSpan()
    monkeypatch.setattr(base_module, "node_span", recording)
    node = _NodeWithNewError()

    await node(triage_state)

    span = recording.spans[0]
    update_call = span.update_calls[0]
    assert update_call["level"] == "ERROR"
    assert update_call["status_message"] == "2 action(s) failed to post"
    assert update_call["metadata"]["new_error_count"] == 1


async def test_call_leaves_span_level_default_when_no_new_errors(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = RecordingNodeSpan()
    monkeypatch.setattr(base_module, "node_span", recording)
    node = _StubNode()

    await node(triage_state)

    span = recording.spans[0]
    update_call = span.update_calls[0]
    assert update_call["level"] is None
    assert update_call["status_message"] is None
    assert "new_error_count" not in update_call["metadata"]


async def test_call_does_not_raise_when_tracing_is_unconfigured(
    triage_state: TriageState,
) -> None:
    """The real (unconfigured, in every test's default Settings) `node_span`
    yields `None` -- `__call__` must guard on that rather than assume a span
    always exists."""
    node = _StubNode()

    await node(triage_state)


async def test_call_unbinds_context_after_completion(triage_state: TriageState) -> None:
    """Contextvars bound during __call__ must not leak into log lines
    emitted after it returns — proves the `with bound_contextvars(...)`
    scoping, not just that binding happens at all."""
    node = _StubNode()
    await node(triage_state)

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        structlog.get_logger().info("after_call")

    assert cap_logs == [{"event": "after_call", "log_level": "info"}]
