from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from graph.schemas import (
    ActionType,
    EpisodicActionOutcome,
    EpisodicMemoryHit,
    PostOutcome,
    RunStatus,
)


def make_action_outcome(**overrides: Any) -> EpisodicActionOutcome:
    defaults: dict[str, Any] = {
        "action_type": ActionType.CODE_FIX,
        "outcome": PostOutcome.POSTED,
    }
    defaults.update(overrides)
    return EpisodicActionOutcome(**defaults)


def make_hit(**overrides: Any) -> EpisodicMemoryHit:
    defaults: dict[str, Any] = {
        "past_issue_number": 17,
        "past_repo": "octo/repo",
        "summary": "Similar null-pointer bug in the same handler.",
        "actions_taken": [make_action_outcome()],
        "outcome": RunStatus.APPROVED_AND_POSTED,
        "similarity_score": 0.93,
        "retrieved_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return EpisodicMemoryHit(**defaults)


def test_action_outcome_construction() -> None:
    action = make_action_outcome()
    assert action.action_type is ActionType.CODE_FIX
    assert action.outcome is PostOutcome.POSTED


def test_action_outcome_json_round_trip() -> None:
    action = make_action_outcome()
    restored = EpisodicActionOutcome.model_validate_json(action.model_dump_json())
    assert restored == action


def test_construction() -> None:
    hit = make_hit()
    assert hit.actions_taken == [make_action_outcome()]


def test_actions_taken_can_have_multiple_entries_with_different_outcomes() -> None:
    hit = make_hit(
        actions_taken=[
            make_action_outcome(action_type=ActionType.LABEL, outcome=PostOutcome.POSTED),
            make_action_outcome(action_type=ActionType.COMMENT, outcome=PostOutcome.REJECTED),
        ]
    )
    assert [a.action_type for a in hit.actions_taken] == [ActionType.LABEL, ActionType.COMMENT]
    assert [a.outcome for a in hit.actions_taken] == [PostOutcome.POSTED, PostOutcome.REJECTED]


def test_similarity_score_out_of_bounds_rejected() -> None:
    with pytest.raises(ValidationError):
        make_hit(similarity_score=1.5)


def test_json_round_trip() -> None:
    hit = make_hit()
    restored = EpisodicMemoryHit.model_validate_json(hit.model_dump_json())
    assert restored == hit
