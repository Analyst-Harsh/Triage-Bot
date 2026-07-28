from datetime import UTC, datetime
from typing import Any

import pytest

from graph.nodes.spam_close import SpamCloseNode
from graph.schemas import CloseAction, IssueType, PlannerOutput, PostOutcome, RiskLevel, RunStatus
from graph.state import TriageState


def make_planner_output(**overrides: Any) -> PlannerOutput:
    defaults: dict[str, Any] = {
        "issue_type": IssueType.SPAM_OR_ABUSE,
        "classification_confidence": 0.95,
        "investigation_plan": [],
        "reasoning": "Issue body is unrelated promotional content.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)


async def test_execute_proposes_a_close_action(triage_state: TriageState) -> None:
    triage_state["planner_output"] = make_planner_output()
    node = SpamCloseNode()

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.PENDING_APPROVAL
    assert "draft" in update
    draft = update["draft"]
    assert draft is not None
    assert len(draft.actions) == 1
    action = draft.actions[0].action
    assert isinstance(action, CloseAction)
    assert action.reason == "spam or abuse"


async def test_execute_hardcodes_high_risk(triage_state: TriageState) -> None:
    triage_state["planner_output"] = make_planner_output()
    node = SpamCloseNode()

    update = await node.execute(triage_state)

    assert "risk_assessment" in update
    risk_assessment = update["risk_assessment"]
    assert risk_assessment is not None
    assert len(risk_assessment.action_assessments) == 1
    assert risk_assessment.action_assessments[0].level == RiskLevel.HIGH


async def test_execute_queues_the_action_for_approval(triage_state: TriageState) -> None:
    triage_state["planner_output"] = make_planner_output()
    node = SpamCloseNode()

    update = await node.execute(triage_state)

    assert "post_results" in update
    post_results = update["post_results"]
    assert post_results is not None
    assert len(post_results.action_results) == 1
    assert post_results.action_results[0].outcome == PostOutcome.QUEUED


async def test_execute_raises_without_planner_output(triage_state: TriageState) -> None:
    node = SpamCloseNode()

    with pytest.raises(ValueError, match="planner_output"):
        await node.execute(triage_state)
