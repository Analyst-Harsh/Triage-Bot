from typing import Any

import pytest
from pydantic import ValidationError

from graph.schemas import ActionDecision, ApprovalDecision


def make_action_decision(**overrides: Any) -> ActionDecision:
    defaults: dict[str, Any] = {"index": 0, "approved": True}
    defaults.update(overrides)
    return ActionDecision(**defaults)


def make_approval_decision(**overrides: Any) -> ApprovalDecision:
    defaults: dict[str, Any] = {"decisions": [make_action_decision()]}
    defaults.update(overrides)
    return ApprovalDecision(**defaults)


def test_action_decision_construction() -> None:
    decision = make_action_decision()
    assert decision.index == 0
    assert decision.approved is True
    assert decision.note is None


def test_action_decision_json_round_trip() -> None:
    decision = make_action_decision(note="Looks good, but tighten the comment wording.")
    restored = ActionDecision.model_validate_json(decision.model_dump_json())
    assert restored == decision


def test_action_decision_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ActionDecision.model_validate({"index": 0, "approved": True, "extra_field": "sneaky"})


def test_action_decision_rejects_negative_index() -> None:
    with pytest.raises(ValidationError):
        ActionDecision(index=-1, approved=True)


def test_approval_decision_construction() -> None:
    decision = make_approval_decision()
    assert len(decision.decisions) == 1


def test_approval_decision_json_round_trip() -> None:
    decision = make_approval_decision(
        decisions=[
            make_action_decision(index=0, approved=True),
            make_action_decision(index=1, approved=False, note="Too risky."),
        ]
    )
    restored = ApprovalDecision.model_validate_json(decision.model_dump_json())
    assert restored == decision


def test_approval_decision_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ApprovalDecision.model_validate(
            {"decisions": [{"index": 0, "approved": True}], "extra_field": "sneaky"}
        )


def test_approval_decision_rejects_empty_decisions() -> None:
    with pytest.raises(ValidationError):
        ApprovalDecision(decisions=[])
