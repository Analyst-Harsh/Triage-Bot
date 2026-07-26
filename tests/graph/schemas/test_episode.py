from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from graph.schemas import (
    ActionPostResult,
    CommentAction,
    DraftedAction,
    Episode,
    IssueType,
    PostOutcome,
    PostResults,
    RiskLevel,
    RunStatus,
)


def make_episode(**overrides: Any) -> Episode:
    defaults: dict[str, Any] = {
        "run_id": uuid4(),
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "issue_summary": "Null pointer when handler receives an empty payload.",
        "issue_type": IssueType.BUG,
        "issue_text": "Null pointer when handler receives an empty payload.\n\nFull body text.",
        "actions_taken": [
            DraftedAction(
                action=CommentAction(comment_body="Thanks for the report!"),
                rationale="A quick acknowledgement while we investigate.",
            )
        ],
        "risk_levels": [RiskLevel.LOW],
        "post_results": PostResults(
            action_results=[ActionPostResult(outcome=PostOutcome.POSTED, detail="url")],
            evaluated_at=datetime.now(UTC),
        ),
        "outcome": RunStatus.AUTO_POSTED,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Episode(**defaults)


def test_construction() -> None:
    episode = make_episode()
    assert episode.issue_type is IssueType.BUG
    assert episode.outcome is RunStatus.AUTO_POSTED
    assert len(episode.actions_taken) == len(episode.risk_levels)


def test_json_round_trip() -> None:
    episode = make_episode()
    restored = Episode.model_validate_json(episode.model_dump_json())
    assert restored == episode


def test_construction_with_post_results_none() -> None:
    """A spam-rejected run (`SpamRejectedNode`) never reaches drafting/
    risk-check/posting, so it writes an episode with `post_results=None`."""
    episode = make_episode(
        actions_taken=[],
        risk_levels=[],
        post_results=None,
        outcome=RunStatus.REJECTED,
    )
    assert episode.post_results is None
    assert episode.actions_taken == []


def test_json_round_trip_with_post_results_none() -> None:
    episode = make_episode(actions_taken=[], risk_levels=[], post_results=None)
    restored = Episode.model_validate_json(episode.model_dump_json())
    assert restored == episode
    assert restored.post_results is None


def test_deserializes_without_post_results_for_backward_compatibility() -> None:
    """An episode written before `post_results` could be absent must still
    deserialize -- it defaults to `None`."""
    payload = make_episode().model_dump(mode="json")
    del payload["post_results"]

    restored = Episode.model_validate(payload)

    assert restored.post_results is None


def test_can_hold_multiple_actions_and_risk_levels() -> None:
    episode = make_episode(
        actions_taken=[
            DraftedAction(
                action=CommentAction(comment_body="Thanks for the report!"),
                rationale="Acknowledge.",
            ),
            DraftedAction(
                action=CommentAction(comment_body="Closing as a duplicate."),
                rationale="Matches a known duplicate.",
            ),
        ],
        risk_levels=[RiskLevel.LOW, RiskLevel.MEDIUM],
        outcome=RunStatus.APPROVED_AND_POSTED,
    )
    assert len(episode.actions_taken) == 2
    assert episode.risk_levels == [RiskLevel.LOW, RiskLevel.MEDIUM]
