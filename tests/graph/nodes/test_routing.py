from datetime import UTC, datetime

import pytest

from graph.nodes.routing import route_by_risk
from graph.schemas import ActionRiskAssessment, RiskAssessment, RiskLevel
from graph.state import TriageState


def _risk_assessment(*, requires_human_approval: bool) -> RiskAssessment:
    return RiskAssessment(
        action_assessments=[
            ActionRiskAssessment(
                level=RiskLevel.HIGH if requires_human_approval else RiskLevel.LOW,
                risk_factors=[],
                reasoning="test",
            )
        ],
        assessed_at=datetime.now(UTC),
    )


def test_routes_to_auto_post_when_approval_not_required(triage_state: TriageState) -> None:
    triage_state["risk_assessment"] = _risk_assessment(requires_human_approval=False)

    assert route_by_risk(triage_state) == "auto_post"


def test_routes_to_approval_queue_when_approval_required(triage_state: TriageState) -> None:
    triage_state["risk_assessment"] = _risk_assessment(requires_human_approval=True)

    assert route_by_risk(triage_state) == "approval_queue"


def test_routes_to_approval_queue_when_any_action_is_above_low(
    triage_state: TriageState,
) -> None:
    triage_state["risk_assessment"] = RiskAssessment(
        action_assessments=[
            ActionRiskAssessment(level=RiskLevel.LOW, risk_factors=[], reasoning="Label."),
            ActionRiskAssessment(level=RiskLevel.MEDIUM, risk_factors=[], reasoning="Comment."),
        ],
        assessed_at=datetime.now(UTC),
    )

    assert route_by_risk(triage_state) == "approval_queue"


def test_raises_when_risk_assessment_missing(triage_state: TriageState) -> None:
    with pytest.raises(ValueError, match="risk_assessment"):
        route_by_risk(triage_state)
