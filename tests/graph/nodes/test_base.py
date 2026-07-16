from typing import ClassVar

import pytest
import structlog
from structlog.testing import capture_logs

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.state import TriageState, TriageStateUpdate


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


async def test_call_unbinds_context_after_completion(triage_state: TriageState) -> None:
    """Contextvars bound during __call__ must not leak into log lines
    emitted after it returns — proves the `with bound_contextvars(...)`
    scoping, not just that binding happens at all."""
    node = _StubNode()
    await node(triage_state)

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        structlog.get_logger().info("after_call")

    assert cap_logs == [{"event": "after_call", "log_level": "info"}]
