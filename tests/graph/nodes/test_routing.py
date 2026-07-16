from datetime import UTC, datetime

import pytest

from graph.nodes.routing import route_by_risk
from graph.schemas import RiskAssessment, RiskLevel
from graph.state import TriageState


def _risk_assessment(*, requires_human_approval: bool) -> RiskAssessment:
    return RiskAssessment(
        level=RiskLevel.HIGH if requires_human_approval else RiskLevel.LOW,
        score=0.9 if requires_human_approval else 0.1,
        risk_factors=[],
        reasoning="test",
        requires_human_approval=requires_human_approval,
        assessed_at=datetime.now(UTC),
    )


def test_routes_to_auto_post_when_approval_not_required(triage_state: TriageState) -> None:
    triage_state["risk_assessment"] = _risk_assessment(requires_human_approval=False)

    assert route_by_risk(triage_state) == "auto_post"


def test_routes_to_approval_queue_when_approval_required(triage_state: TriageState) -> None:
    triage_state["risk_assessment"] = _risk_assessment(requires_human_approval=True)

    assert route_by_risk(triage_state) == "approval_queue"


def test_raises_when_risk_assessment_missing(triage_state: TriageState) -> None:
    with pytest.raises(ValueError, match="risk_assessment"):
        route_by_risk(triage_state)
