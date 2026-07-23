from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from graph.schemas import (
    CloseAction,
    CodeFixAction,
    CodeFixIntent,
    CommentAction,
    DraftedAction,
    DraftOutput,
    DraftProposal,
    ProposedAction,
    SandboxResult,
)


def make_proposed_action(**overrides: Any) -> ProposedAction:
    defaults: dict[str, Any] = {
        "action": CommentAction(comment_body="Could you share a reproduction?"),
        "rationale": "Not enough information to act yet.",
    }
    defaults.update(overrides)
    return ProposedAction(**defaults)


def make_draft_proposal(**overrides: Any) -> DraftProposal:
    defaults: dict[str, Any] = {
        "actions": [make_proposed_action()],
        "overall_rationale": "The issue lacks reproduction steps.",
    }
    defaults.update(overrides)
    return DraftProposal(**defaults)


def make_drafted_action(**overrides: Any) -> DraftedAction:
    defaults: dict[str, Any] = {
        "action": CommentAction(comment_body="Could you share a reproduction?"),
        "rationale": "Not enough information to act yet.",
    }
    defaults.update(overrides)
    return DraftedAction(**defaults)


def make_draft(**overrides: Any) -> DraftOutput:
    defaults: dict[str, Any] = {
        "actions": [make_drafted_action()],
        "overall_rationale": "The issue lacks reproduction steps.",
        "unsupported_claims": [],
        "drafted_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return DraftOutput(**defaults)


def test_proposed_action_construction() -> None:
    proposed = make_proposed_action()
    assert isinstance(proposed.action, CommentAction)


def test_proposed_action_json_round_trip() -> None:
    proposed = make_proposed_action()
    restored = ProposedAction.model_validate_json(proposed.model_dump_json())
    assert restored == proposed


def test_draft_proposal_construction() -> None:
    proposal = make_draft_proposal()
    assert len(proposal.actions) == 1
    assert proposal.overall_rationale == "The issue lacks reproduction steps."


def test_draft_proposal_json_round_trip() -> None:
    proposal = make_draft_proposal()
    restored = DraftProposal.model_validate_json(proposal.model_dump_json())
    assert restored == proposal


def test_draft_proposal_rejects_empty_actions() -> None:
    with pytest.raises(ValidationError):
        DraftProposal(actions=[], overall_rationale="No actions proposed.")


def test_draft_proposal_can_hold_multiple_actions() -> None:
    proposal = make_draft_proposal(
        actions=[
            make_proposed_action(action=CommentAction(comment_body="Thanks!")),
            make_proposed_action(
                action=CloseAction(reason="duplicate", close_comment="Duplicate of #10")
            ),
        ]
    )
    assert len(proposal.actions) == 2


def test_drafted_action_construction() -> None:
    drafted = make_drafted_action()
    assert isinstance(drafted.action, CommentAction)


def test_drafted_action_json_round_trip() -> None:
    drafted = make_drafted_action()
    restored = DraftedAction.model_validate_json(drafted.model_dump_json())
    assert restored == drafted


def test_drafted_action_accepts_code_fix_action() -> None:
    """`DraftedAction.action` is typed against the full `DraftAction` union
    (unlike `ProposedAction`, restricted to `DraftIntent`) so this shape
    didn't need to change now that the sandbox code-fix path has landed --
    it just started populating the `code_fix` variant that was always a
    valid member of this type."""
    drafted = make_drafted_action(
        action=CodeFixAction(
            diff="--- a/foo.py\n+++ b/foo.py\n",
            target_files=["foo.py"],
            sandbox_result=SandboxResult(
                passed=True,
                logs="1 passed",
                test_command="pytest tests/test_foo.py",
                duration_seconds=1.23,
            ),
            base_commit_sha="a1b2c3d4e5f6",
            base_ref="main",
        )
    )
    assert isinstance(drafted.action, CodeFixAction)


def test_proposed_action_accepts_code_fix_intent() -> None:
    proposed = make_proposed_action(action=CodeFixIntent())
    assert isinstance(proposed.action, CodeFixIntent)


def test_proposed_action_rejects_raw_code_fix_action_payload() -> None:
    """`ProposedAction.action` is typed as `DraftIntent`, whose `code_fix`
    variant is `CodeFixIntent` — a raw `CodeFixAction`-shaped payload (with
    a fabricated diff/target_files/sandbox_result) must be rejected."""
    payload = {
        "action": {
            "action_type": "code_fix",
            "diff": "--- a/foo.py\n+++ b/foo.py\n",
            "target_files": ["foo.py"],
            "sandbox_result": {
                "passed": True,
                "logs": "1 passed",
                "test_command": "pytest tests/test_foo.py",
                "duration_seconds": 1.23,
            },
            "base_commit_sha": "a1b2c3d4e5f6",
            "base_ref": "main",
        },
        "rationale": "Attempting a code fix.",
    }
    with pytest.raises(ValidationError):
        ProposedAction.model_validate(payload)


def test_draft_construction() -> None:
    draft = make_draft()
    assert isinstance(draft.actions[0].action, CommentAction)
    assert draft.unsupported_claims == []


def test_draft_json_round_trip() -> None:
    draft = make_draft()
    restored = DraftOutput.model_validate_json(draft.model_dump_json())
    assert restored == draft


def test_draft_rejects_empty_actions() -> None:
    with pytest.raises(ValidationError):
        DraftOutput(
            actions=[],
            overall_rationale="No actions proposed.",
            unsupported_claims=[],
            drafted_at=datetime.now(UTC),
        )


def test_draft_can_hold_multiple_actions_with_unsupported_claims() -> None:
    draft = make_draft(
        actions=[
            make_drafted_action(),
            make_drafted_action(
                action=CloseAction(reason="duplicate", close_comment="Duplicate of #10"),
                rationale="Matches a known duplicate pattern.",
            ),
        ],
        unsupported_claims=["Claims the fix shipped in v2.1, which evidence never states."],
    )
    assert len(draft.actions) == 2
    assert draft.unsupported_claims == [
        "Claims the fix shipped in v2.1, which evidence never states."
    ]
