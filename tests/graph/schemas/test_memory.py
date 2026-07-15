from datetime import UTC, datetime
from typing import Any

from graph.schemas import ActionType, EpisodicMemoryHit


def make_hit(**overrides: Any) -> EpisodicMemoryHit:
    defaults: dict[str, Any] = {
        "past_issue_number": 17,
        "past_repo": "octo/repo",
        "summary": "Similar null-pointer bug in the same handler.",
        "action_taken": ActionType.CODE_FIX,
        "outcome": "accepted",
        "similarity_score": 0.93,
        "retrieved_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return EpisodicMemoryHit(**defaults)


def test_construction() -> None:
    hit = make_hit()
    assert hit.action_taken is ActionType.CODE_FIX


def test_action_taken_optional() -> None:
    hit = make_hit(action_taken=None)
    assert hit.action_taken is None


def test_json_round_trip() -> None:
    hit = make_hit()
    restored = EpisodicMemoryHit.model_validate_json(hit.model_dump_json())
    assert restored == hit
