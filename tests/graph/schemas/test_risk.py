from datetime import UTC, datetime

from graph.schemas import RiskAssessment, RiskLevel


def make_risk(**overrides) -> RiskAssessment:
    defaults = dict(
        level=RiskLevel.HIGH,
        score=82.5,
        risk_factors=["proposes code change", "first-time contributor"],
        reasoning="Code fix touches auth middleware.",
        requires_human_approval=True,
        assessed_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return RiskAssessment(**defaults)


def test_construction():
    risk = make_risk()
    assert risk.level is RiskLevel.HIGH
    assert risk.requires_human_approval is True


def test_json_round_trip():
    risk = make_risk()
    restored = RiskAssessment.model_validate_json(risk.model_dump_json())
    assert restored == risk
