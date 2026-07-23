import pytest
from pydantic import TypeAdapter, ValidationError

from graph.schemas import (
    CloseAction,
    CodeFixAction,
    CodeFixIntent,
    CommentAction,
    DraftAction,
    DraftIntent,
    LabelAction,
    SandboxResult,
)

draft_action_adapter: TypeAdapter[DraftAction] = TypeAdapter(DraftAction)
draft_intent_adapter: TypeAdapter[DraftIntent] = TypeAdapter(DraftIntent)


def test_comment_action_round_trip() -> None:
    action = CommentAction(comment_body="Thanks for the report!")
    restored = draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CommentAction)
    assert restored == action


def test_label_action_round_trip() -> None:
    action = LabelAction(labels_to_add=["needs-triage"], labels_to_remove=["stale"])
    restored = draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, LabelAction)


def test_close_action_round_trip() -> None:
    action = CloseAction(reason="duplicate", close_comment="Duplicate of #10")
    restored = draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CloseAction)


def test_code_fix_action_round_trip() -> None:
    action = CodeFixAction(
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
    restored = draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CodeFixAction)
    assert restored.sandbox_result.passed is True
    assert restored.base_commit_sha == "a1b2c3d4e5f6"
    assert restored.base_ref == "main"


def test_discriminated_union_dispatches_by_action_type() -> None:
    payload = {"action_type": "label", "labels_to_add": ["bug"], "labels_to_remove": []}
    result = draft_action_adapter.validate_python(payload)
    assert isinstance(result, LabelAction)


def test_incomplete_code_fix_action_is_rejected() -> None:
    payload = {"action_type": "code_fix", "target_files": ["foo.py"]}
    with pytest.raises(ValidationError):
        draft_action_adapter.validate_python(payload)


def test_unknown_action_type_is_rejected() -> None:
    payload = {"action_type": "delete_repo"}
    with pytest.raises(ValidationError):
        draft_action_adapter.validate_python(payload)


def test_code_fix_intent_round_trip() -> None:
    intent = CodeFixIntent()
    restored = CodeFixIntent.model_validate_json(intent.model_dump_json())
    assert restored == intent
    assert restored.action_type == "code_fix"


def test_draft_intent_dispatches_comment() -> None:
    action = CommentAction(comment_body="Thanks for the report!")
    restored = draft_intent_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CommentAction)
    assert restored == action


def test_draft_intent_dispatches_label() -> None:
    action = LabelAction(labels_to_add=["needs-triage"], labels_to_remove=["stale"])
    restored = draft_intent_adapter.validate_python(action.model_dump())
    assert isinstance(restored, LabelAction)


def test_draft_intent_dispatches_close() -> None:
    action = CloseAction(reason="duplicate", close_comment="Duplicate of #10")
    restored = draft_intent_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CloseAction)


def test_draft_intent_dispatches_code_fix_intent() -> None:
    intent = CodeFixIntent()
    restored = draft_intent_adapter.validate_python(intent.model_dump())
    assert isinstance(restored, CodeFixIntent)


def test_draft_intent_rejects_full_code_fix_action_payload() -> None:
    """The core security invariant: the LLM-facing `DraftIntent` union's
    `code_fix` variant is `CodeFixIntent` (intent only), not `CodeFixAction`.
    A payload shaped like a real `CodeFixAction` — with a `diff`/
    `target_files`/`sandbox_result`/`base_commit_sha`/`base_ref` the model
    fabricated — must be rejected, not silently accepted as extra fields."""
    payload = {
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
    }
    with pytest.raises(ValidationError):
        draft_intent_adapter.validate_python(payload)
