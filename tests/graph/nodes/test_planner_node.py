from graph.nodes.planner import PlannerNode
from graph.schemas import IssueType, PlannerClassification, RunStatus
from graph.state import TriageState
from tests.graph.nodes.conftest import make_fake_planner_node


def _make_node(classification: PlannerClassification) -> PlannerNode:
    return make_fake_planner_node(parsed_result=classification)


async def test_execute_classifies_bug_report(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=["search codebase for the referenced exception"],
        reasoning="Stack trace matches a known exception type.",
    )
    node = _make_node(classification)

    update = await node.execute(triage_state)

    assert "planner_output" in update
    output = update["planner_output"]
    assert output is not None
    assert output.issue_type == IssueType.BUG
    assert output.classification_confidence == 0.9
    assert output.investigation_plan == ["search codebase for the referenced exception"]
    assert output.classified_at is not None
    assert "status" in update
    assert update["status"] == RunStatus.PLANNING


async def test_execute_classifies_feature_request(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.FEATURE_REQUEST,
        classification_confidence=0.75,
        investigation_plan=[],
        reasoning="Author is asking for new functionality, not reporting a defect.",
    )
    node = _make_node(classification)

    update = await node.execute(triage_state)

    assert "planner_output" in update
    output = update["planner_output"]
    assert output is not None
    assert output.issue_type == IssueType.FEATURE_REQUEST


async def test_execute_increases_estimated_cost(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    node = _make_node(classification)

    update = await node.execute(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.estimated_cost_usd > triage_state["run_meta"].estimated_cost_usd


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    node = _make_node(classification)

    update = await node(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.iteration_count == 1
