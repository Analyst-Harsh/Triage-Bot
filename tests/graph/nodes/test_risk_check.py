from graph.nodes.risk_check import RiskCheckNode
from graph.schemas import RiskLevel, RunStatus
from graph.state import TriageState


def test_execute_returns_stub_low_risk_assessment(triage_state: TriageState) -> None:
    node = RiskCheckNode()
    update = node.execute(triage_state)

    assert "risk_assessment" in update
    assert update["risk_assessment"] is not None
    assert update["risk_assessment"].level == RiskLevel.LOW
    assert update["risk_assessment"].requires_human_approval is False
    assert "status" in update
    assert update["status"] == RunStatus.RISK_CHECK


def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    node = RiskCheckNode()
    update = node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].iteration_count == 1
