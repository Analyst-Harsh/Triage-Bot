from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec
from uuid import UUID, uuid4

from github import GithubException

from graph.nodes.utils.action_executor import ActionExecutor
from graph.schemas import (
    CloseAction,
    CodeFixAction,
    CommentAction,
    DraftedAction,
    IssuePayload,
    IssueSource,
    LabelAction,
    PostOutcome,
    SandboxResult,
)
from utils.diff_applier import DiffApplyError
from utils.github_client import GitHubClient


class _FakeActionExecutor(ActionExecutor):
    """Test double: overrides `ActionExecutor.__init__` (which otherwise
    resolves the real process-wide `get_github_client()` singleton) to
    accept a `GitHubClient`-shaped fake directly -- the real `execute()`/
    `_post()` logic (inherited, not overridden) is what's actually under
    test."""

    def __init__(self, github_client: Any) -> None:
        self._github_client = github_client


def make_executor() -> tuple[ActionExecutor, Any]:
    github_client = create_autospec(GitHubClient, instance=True, spec_set=True)
    return _FakeActionExecutor(github_client), github_client


def make_issue() -> IssuePayload:
    return IssuePayload(
        repo_full_name="octo/repo",
        issue_number=42,
        title="Crash on startup",
        body="App crashes with a NoneType error.",
        author="octocat",
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/42",
        source=IssueSource.WEBHOOK,
    )


def make_drafted_action(**overrides: Any) -> DraftedAction:
    defaults: dict[str, Any] = {
        "action": CommentAction(comment_body="Thanks!"),
        "rationale": "Acknowledging the report.",
    }
    defaults.update(overrides)
    return DraftedAction(**defaults)


def _code_fix_action(**overrides: Any) -> CodeFixAction:
    defaults: dict[str, Any] = {
        "diff": "--- a/foo.py\n+++ b/foo.py\n",
        "target_files": ["foo.py"],
        "sandbox_result": SandboxResult(
            passed=True, logs="all green", test_command="pytest", duration_seconds=1.2
        ),
        "base_commit_sha": "abc123",
        "base_ref": "main",
    }
    defaults.update(overrides)
    return CodeFixAction(**defaults)


RUN_ID: UUID = uuid4()


async def test_comment_action_posts_and_returns_url() -> None:
    executor, github_client = make_executor()
    github_client.post_comment.return_value = "https://github.com/octo/repo/issues/42#c1"

    result = await executor.execute(
        make_drafted_action(action=CommentAction(comment_body="Thanks!")),
        make_issue(),
        dry_run=False,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.POSTED
    assert result.detail == "https://github.com/octo/repo/issues/42#c1"
    github_client.post_comment.assert_called_once_with("octo/repo", 42, "Thanks!")


async def test_label_action_applies_labels_and_returns_no_detail() -> None:
    executor, github_client = make_executor()

    result = await executor.execute(
        make_drafted_action(action=LabelAction(labels_to_add=["bug"], labels_to_remove=["stale"])),
        make_issue(),
        dry_run=False,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.POSTED
    assert result.detail is None
    github_client.apply_labels.assert_called_once_with("octo/repo", 42, ["bug"], ["stale"])


async def test_close_action_posts_comment_then_closes() -> None:
    executor, github_client = make_executor()

    result = await executor.execute(
        make_drafted_action(
            action=CloseAction(reason="duplicate", close_comment="Duplicate of #10.")
        ),
        make_issue(),
        dry_run=False,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.POSTED
    github_client.close_issue.assert_called_once_with("octo/repo", 42, "Duplicate of #10.")


async def test_dry_run_returns_posted_without_calling_github() -> None:
    executor, github_client = make_executor()

    result = await executor.execute(
        make_drafted_action(action=CommentAction(comment_body="Thanks!")),
        make_issue(),
        dry_run=True,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.POSTED
    assert result.detail is None
    github_client.post_comment.assert_not_called()


async def test_github_exception_produces_failed_result_with_error_detail() -> None:
    executor, github_client = make_executor()
    github_client.post_comment.side_effect = GithubException(500, {"message": "boom"}, None)

    result = await executor.execute(
        make_drafted_action(action=CommentAction(comment_body="Thanks!")),
        make_issue(),
        dry_run=False,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.FAILED
    assert result.detail is not None
    assert "boom" in result.detail


async def test_code_fix_dry_run_returns_posted_without_github_calls() -> None:
    executor, github_client = make_executor()

    result = await executor.execute(
        make_drafted_action(action=_code_fix_action()),
        make_issue(),
        dry_run=True,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.POSTED
    assert result.detail is None
    github_client.create_pull_request_from_diff.assert_not_called()


async def test_code_fix_creates_pr_and_returns_url_as_detail() -> None:
    executor, github_client = make_executor()
    github_client.create_pull_request_from_diff.return_value = "https://github.com/octo/repo/pull/7"
    run_id = uuid4()
    action = _code_fix_action()
    drafted = make_drafted_action(action=action, rationale="Fixes the null check in foo.py.")

    result = await executor.execute(drafted, make_issue(), dry_run=False, run_id=run_id)

    assert result.outcome == PostOutcome.POSTED
    assert result.detail == "https://github.com/octo/repo/pull/7"
    github_client.create_pull_request_from_diff.assert_called_once()
    _, kwargs = github_client.create_pull_request_from_diff.call_args
    assert kwargs["diff"] == action.diff
    assert kwargs["target_files"] == action.target_files
    assert kwargs["base_commit_sha"] == action.base_commit_sha
    assert kwargs["base_branch"] == action.base_ref
    assert kwargs["branch_name"] == f"triage-bot/issue-42-{run_id.hex[:8]}"
    assert "#42" in kwargs["title"]
    assert "Fixes the null check in foo.py." in kwargs["body"]
    assert "pytest" in kwargs["body"]
    assert "passed" in kwargs["body"]
    assert action.base_commit_sha in kwargs["body"]


async def test_code_fix_github_exception_produces_failed_result() -> None:
    executor, github_client = make_executor()
    github_client.create_pull_request_from_diff.side_effect = GithubException(
        422, {"message": "Reference already exists"}, None
    )

    result = await executor.execute(
        make_drafted_action(action=_code_fix_action()),
        make_issue(),
        dry_run=False,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.FAILED
    assert result.detail is not None
    assert "Reference already exists" in result.detail


async def test_code_fix_diff_apply_error_produces_failed_result() -> None:
    executor, github_client = make_executor()
    github_client.create_pull_request_from_diff.side_effect = DiffApplyError(
        "diff failed to apply: context mismatch"
    )

    result = await executor.execute(
        make_drafted_action(action=_code_fix_action()),
        make_issue(),
        dry_run=False,
        run_id=RUN_ID,
    )

    assert result.outcome == PostOutcome.FAILED
    assert result.detail is not None
    assert "context mismatch" in result.detail


async def test_code_fix_failing_sandbox_result_is_reflected_in_pr_body() -> None:
    executor, github_client = make_executor()
    github_client.create_pull_request_from_diff.return_value = "https://github.com/octo/repo/pull/8"
    action = _code_fix_action(
        sandbox_result=SandboxResult(
            passed=False, logs="1 failed", test_command="pytest", duration_seconds=0.5
        )
    )

    await executor.execute(
        make_drafted_action(action=action), make_issue(), dry_run=False, run_id=RUN_ID
    )

    _, kwargs = github_client.create_pull_request_from_diff.call_args
    assert "FAILED" in kwargs["body"]
