from typing import ClassVar

import pytest

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
