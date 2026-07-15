from datetime import UTC, datetime
from typing import Any

from graph.schemas import CommentAction, DraftOutput


def make_draft(**overrides: Any) -> DraftOutput:
    defaults: dict[str, Any] = {
        "action": CommentAction(comment_body="Could you share a reproduction?"),
        "rationale": "Not enough information to act yet.",
        "drafted_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return DraftOutput(**defaults)


def test_construction() -> None:
    draft = make_draft()
    assert isinstance(draft.action, CommentAction)


def test_json_round_trip() -> None:
    draft = make_draft()
    restored = DraftOutput.model_validate_json(draft.model_dump_json())
    assert restored == draft
