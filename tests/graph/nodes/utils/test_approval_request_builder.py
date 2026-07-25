from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from graph.nodes.utils.approval_request_builder import ApprovalRequestBuilder
from graph.schemas import (
    DIFF_PREVIEW_MAX_BYTES,
    ActionRiskAssessment,
    CloseAction,
    CodeFixAction,
    CommentAction,
    DraftedAction,
    DraftOutput,
    IssuePayload,
    IssueSource,
    LabelAction,
    RiskAssessment,
    RiskLevel,
    RunMeta,
    SandboxResult,
)


def make_issue(**overrides: Any) -> IssuePayload:
    defaults: dict[str, Any] = {
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "title": "Something broke",
        "body": "Here is what happened...",
        "author": "octocat",
        "created_at": datetime.now(UTC),
        "url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK,
    }
    defaults.update(overrides)
    return IssuePayload(**defaults)


def make_run_meta(**overrides: Any) -> RunMeta:
    defaults: dict[str, Any] = {
        "run_id": uuid4(),
        "thread_id": "octo/repo#42",
        "started_at": datetime.now(UTC),
        "max_iterations": 15,
        "max_cost_usd": 2.5,
    }
    defaults.update(overrides)
    return RunMeta(**defaults)


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


def make_action_risk_assessment(**overrides: Any) -> ActionRiskAssessment:
    defaults: dict[str, Any] = {
        "level": RiskLevel.MEDIUM,
        "risk_factors": ["assertive tone"],
        "reasoning": "Makes a claim not fully backed by evidence.",
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


def make_code_fix_action(**overrides: Any) -> CodeFixAction:
    defaults: dict[str, Any] = {
        "diff": "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n",
        "target_files": ["foo.py"],
        "sandbox_result": SandboxResult(
            passed=True,
            logs="1 passed",
            test_command="pytest tests/test_foo.py",
            duration_seconds=1.23,
        ),
        "base_commit_sha": "a1b2c3d4e5f6",  # pragma: allowlist secret -- fake SHA fixture
        "base_ref": "main",
    }
    defaults.update(overrides)
    return CodeFixAction(**defaults)


def test_build_summarizes_only_queued_indices() -> None:
    issue = make_issue()
    draft = make_draft(
        actions=[
            make_drafted_action(),
            make_drafted_action(
                action=LabelAction(labels_to_add=["bug"]), rationale="Clear bug report."
            ),
            make_drafted_action(
                action=CloseAction(reason="duplicate", close_comment="Duplicate of #10"),
                rationale="Matches a known duplicate.",
            ),
        ]
    )
    risk = make_risk(
        action_assessments=[
            make_action_risk_assessment(level=RiskLevel.MEDIUM),
            make_action_risk_assessment(level=RiskLevel.LOW),
            make_action_risk_assessment(level=RiskLevel.HIGH),
        ]
    )
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder()

    request = builder.build(issue, draft, risk, run_meta, queued_indices=[0, 2])

    assert [a.index for a in request.actions] == [0, 2]
    assert request.run_id == run_meta.run_id
    assert request.repo_full_name == issue.repo_full_name
    assert request.issue_url == issue.url
    assert request.actions[1].action_type == "close"
    assert request.actions[1].risk_level is RiskLevel.HIGH


def test_build_code_fix_carries_sandbox_and_files() -> None:
    issue = make_issue()
    code_fix = make_code_fix_action(target_files=["a.py", "b.py"])
    draft = make_draft(
        actions=[make_drafted_action(action=code_fix, rationale="Fixes the null check.")]
    )
    risk = make_risk(action_assessments=[make_action_risk_assessment(level=RiskLevel.HIGH)])
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder()

    request = builder.build(issue, draft, risk, run_meta, queued_indices=[0])
    summary = request.actions[0]

    assert summary.action_type == "code_fix"
    assert summary.target_files == ["a.py", "b.py"]
    assert summary.sandbox_passed is True
    assert summary.sandbox_test_command == "pytest tests/test_foo.py"
    assert summary.diff_preview == code_fix.diff
    assert summary.diff_truncated is False


def test_build_non_code_fix_leaves_code_fix_fields_empty() -> None:
    issue = make_issue()
    draft = make_draft()
    risk = make_risk()
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder()

    request = builder.build(issue, draft, risk, run_meta, queued_indices=[0])
    summary = request.actions[0]

    assert summary.target_files == []
    assert summary.sandbox_passed is None
    assert summary.sandbox_test_command is None
    assert summary.diff_preview is None
    assert summary.diff_truncated is False


def test_diff_preview_under_cap_is_untruncated() -> None:
    issue = make_issue()
    code_fix = make_code_fix_action(diff="short diff")
    draft = make_draft(actions=[make_drafted_action(action=code_fix)])
    risk = make_risk(action_assessments=[make_action_risk_assessment(level=RiskLevel.HIGH)])
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder()

    request = builder.build(issue, draft, risk, run_meta, queued_indices=[0])

    assert request.actions[0].diff_preview == "short diff"
    assert request.actions[0].diff_truncated is False


def test_diff_preview_over_cap_is_truncated_with_marker() -> None:
    issue = make_issue()
    huge_diff = "x" * (DIFF_PREVIEW_MAX_BYTES + 500)
    code_fix = make_code_fix_action(diff=huge_diff)
    draft = make_draft(actions=[make_drafted_action(action=code_fix)])
    risk = make_risk(action_assessments=[make_action_risk_assessment(level=RiskLevel.HIGH)])
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder()

    request = builder.build(issue, draft, risk, run_meta, queued_indices=[0])
    summary = request.actions[0]

    assert summary.diff_truncated is True
    assert summary.diff_preview is not None
    assert "diff truncated" in summary.diff_preview
    assert len(summary.diff_preview.encode("utf-8")) < len(huge_diff.encode("utf-8"))


def test_diff_preview_cap_is_constructor_configurable() -> None:
    """The byte cap is per-instance config (`ApprovalRequestBuilder(
    diff_preview_max_bytes=...)`), not just the module-level default --
    lets a test (or a future caller with different payload-size needs)
    exercise truncation without needing a giant fixture string."""
    issue = make_issue()
    code_fix = make_code_fix_action(diff="0123456789")
    draft = make_draft(actions=[make_drafted_action(action=code_fix)])
    risk = make_risk(action_assessments=[make_action_risk_assessment(level=RiskLevel.HIGH)])
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder(diff_preview_max_bytes=4)

    request = builder.build(issue, draft, risk, run_meta, queued_indices=[0])
    summary = request.actions[0]

    assert summary.diff_truncated is True
    assert summary.diff_preview is not None
    assert summary.diff_preview.startswith("0123")


def test_build_raises_on_empty_queued_indices() -> None:
    issue = make_issue()
    draft = make_draft()
    risk = make_risk()
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder()

    with pytest.raises(ValueError, match="at least one queued index"):
        builder.build(issue, draft, risk, run_meta, queued_indices=[])


def test_label_action_summary_lists_added_and_removed_labels() -> None:
    issue = make_issue()
    draft = make_draft(
        actions=[
            make_drafted_action(
                action=LabelAction(labels_to_add=["bug"], labels_to_remove=["stale"])
            )
        ]
    )
    risk = make_risk()
    run_meta = make_run_meta()
    builder = ApprovalRequestBuilder()

    request = builder.build(issue, draft, risk, run_meta, queued_indices=[0])

    assert "+bug" in request.actions[0].summary
    assert "-stale" in request.actions[0].summary
