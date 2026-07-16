from graph.nodes.approval_queue import ApprovalQueueNode
from graph.schemas import RunStatus
from graph.state import TriageState


def test_execute_returns_pending_approval_status(triage_state: TriageState) -> None:
    node = ApprovalQueueNode()
    update = node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.PENDING_APPROVAL


def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    node = ApprovalQueueNode()
    update = node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].iteration_count == 1
