from graph.nodes.planner import PlannerNode
from graph.schemas import IssueType, RunStatus
from graph.state import TriageState


async def test_execute_returns_stub_bug_classification(triage_state: TriageState) -> None:
    node = PlannerNode()
    update = await node.execute(triage_state)

    assert "planner_output" in update
    assert update["planner_output"] is not None
    assert update["planner_output"].issue_type == IssueType.BUG
    assert "status" in update
    assert update["status"] == RunStatus.PLANNING


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    node = PlannerNode()
    update = await node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].iteration_count == 1
