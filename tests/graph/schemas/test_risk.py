from datetime import UTC, datetime
from typing import Any

from graph.schemas import (
    ActionRiskAssessment,
    ActionRiskJudgment,
    RiskAssessment,
    RiskJudgmentBatch,
    RiskLevel,
)


def make_action_risk_assessment(**overrides: Any) -> ActionRiskAssessment:
    defaults: dict[str, Any] = {
        "level": RiskLevel.HIGH,
        "risk_factors": ["proposes code change", "first-time contributor"],
        "reasoning": "Code fix touches auth middleware.",
    }
    defaults.update(overrides)
    return ActionRiskAssessment(**defaults)


def make_risk(**overrides: Any) -> RiskAssessment:
    defaults: dict[str, Any] = {
        "action_assessments": [make_action_risk_assessment()],
        "assessed_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return RiskAssessment(**defaults)


def make_action_risk_judgment(**overrides: Any) -> ActionRiskJudgment:
    defaults: dict[str, Any] = {
        "action_index": 0,
        "level": RiskLevel.MEDIUM,
        "risk_factors": ["assertive tone"],
        "reasoning": "Makes a strong claim not fully backed by evidence.",
    }
    defaults.update(overrides)
    return ActionRiskJudgment(**defaults)


def make_risk_judgment_batch(**overrides: Any) -> RiskJudgmentBatch:
    defaults: dict[str, Any] = {"judgments": [make_action_risk_judgment()]}
    defaults.update(overrides)
    return RiskJudgmentBatch(**defaults)


def test_action_risk_assessment_construction() -> None:
    assessment = make_action_risk_assessment()
    assert assessment.level is RiskLevel.HIGH
    assert assessment.risk_factors == ["proposes code change", "first-time contributor"]


def test_action_risk_assessment_json_round_trip() -> None:
    assessment = make_action_risk_assessment()
    restored = ActionRiskAssessment.model_validate_json(assessment.model_dump_json())
    assert restored == assessment


def test_risk_assessment_construction() -> None:
    risk = make_risk()
    assert len(risk.action_assessments) == 1
    assert risk.action_assessments[0].level is RiskLevel.HIGH


def test_risk_assessment_json_round_trip() -> None:
    risk = make_risk()
    restored = RiskAssessment.model_validate_json(risk.model_dump_json())
    assert restored == risk


def test_risk_assessment_with_multiple_action_assessments() -> None:
    risk = make_risk(
        action_assessments=[
            make_action_risk_assessment(level=RiskLevel.LOW, risk_factors=[], reasoning="Label."),
            make_action_risk_assessment(level=RiskLevel.HIGH),
        ]
    )
    assert [a.level for a in risk.action_assessments] == [RiskLevel.LOW, RiskLevel.HIGH]


def test_action_risk_judgment_construction() -> None:
    judgment = make_action_risk_judgment()
    assert judgment.action_index == 0
    assert judgment.level is RiskLevel.MEDIUM


def test_action_risk_judgment_json_round_trip() -> None:
    judgment = make_action_risk_judgment()
    restored = ActionRiskJudgment.model_validate_json(judgment.model_dump_json())
    assert restored == judgment


def test_risk_judgment_batch_construction() -> None:
    batch = make_risk_judgment_batch()
    assert len(batch.judgments) == 1
    assert batch.judgments[0].action_index == 0


def test_risk_judgment_batch_json_round_trip() -> None:
    batch = make_risk_judgment_batch()
    restored = RiskJudgmentBatch.model_validate_json(batch.model_dump_json())
    assert restored == batch
