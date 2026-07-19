from typing import Any

from graph.schemas import GroundingCritique


def make_critique(**overrides: Any) -> GroundingCritique:
    defaults: dict[str, Any] = {
        "unsupported_claims": ["Claims the fix was already released in v2.1."],
    }
    defaults.update(overrides)
    return GroundingCritique(**defaults)


def test_construction() -> None:
    critique = make_critique()
    assert critique.unsupported_claims == ["Claims the fix was already released in v2.1."]


def test_defaults_to_empty_unsupported_claims() -> None:
    critique = GroundingCritique()
    assert critique.unsupported_claims == []


def test_json_round_trip() -> None:
    critique = make_critique()
    restored = GroundingCritique.model_validate_json(critique.model_dump_json())
    assert restored == critique
