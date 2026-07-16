from graph.nodes.drafter import DrafterNode
from graph.schemas import RunStatus
from graph.state import TriageState


def test_execute_returns_stub_comment_action(triage_state: TriageState) -> None:
    node = DrafterNode()
    update = node.execute(triage_state)

    assert "draft" in update
    assert update["draft"] is not None
    assert update["draft"].action.action_type == "comment"
    assert "status" in update
    assert update["status"] == RunStatus.DRAFTING


def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    node = DrafterNode()
    update = node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].iteration_count == 1
