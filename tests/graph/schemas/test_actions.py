import pytest
from pydantic import TypeAdapter, ValidationError

from graph.schemas import (
    CloseAction,
    CodeFixAction,
    CommentAction,
    DraftAction,
    LabelAction,
    NonCodeDraftAction,
    SandboxResult,
)

draft_action_adapter: TypeAdapter[DraftAction] = TypeAdapter(DraftAction)
non_code_draft_action_adapter: TypeAdapter[NonCodeDraftAction] = TypeAdapter(NonCodeDraftAction)


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
    )
    restored = draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CodeFixAction)
    assert restored.sandbox_result.passed is True


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


def test_non_code_comment_action_round_trip() -> None:
    action = CommentAction(comment_body="Thanks for the report!")
    restored = non_code_draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CommentAction)
    assert restored == action


def test_non_code_label_action_round_trip() -> None:
    action = LabelAction(labels_to_add=["needs-triage"], labels_to_remove=["stale"])
    restored = non_code_draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, LabelAction)


def test_non_code_close_action_round_trip() -> None:
    action = CloseAction(reason="duplicate", close_comment="Duplicate of #10")
    restored = non_code_draft_action_adapter.validate_python(action.model_dump())
    assert isinstance(restored, CloseAction)


def test_non_code_draft_action_rejects_code_fix() -> None:
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
    }
    with pytest.raises(ValidationError):
        non_code_draft_action_adapter.validate_python(payload)
