from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

import pytest
from github import GithubException

from api.github_client import GitHubClient
from graph.nodes.utils.action_executor import ActionExecutor
from graph.schemas import (
    CloseAction,
    CodeFixAction,
    CommentAction,
    IssuePayload,
    IssueSource,
    LabelAction,
    PostOutcome,
    SandboxResult,
)


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


def _code_fix_action() -> CodeFixAction:
    return CodeFixAction(
        diff="--- a/foo.py\n+++ b/foo.py\n",
        target_files=["foo.py"],
        sandbox_result=SandboxResult(
            passed=True, logs="all green", test_command="pytest", duration_seconds=1.2
        ),
        base_commit_sha="abc123",
        base_ref="main",
    )


async def test_comment_action_posts_and_returns_url() -> None:
    executor, github_client = make_executor()
    github_client.post_comment.return_value = "https://github.com/octo/repo/issues/42#c1"

    result = await executor.execute(
        CommentAction(comment_body="Thanks!"), make_issue(), dry_run=False
    )

    assert result.outcome == PostOutcome.POSTED
    assert result.detail == "https://github.com/octo/repo/issues/42#c1"
    github_client.post_comment.assert_called_once_with("octo/repo", 42, "Thanks!")


async def test_label_action_applies_labels_and_returns_no_detail() -> None:
    executor, github_client = make_executor()

    result = await executor.execute(
        LabelAction(labels_to_add=["bug"], labels_to_remove=["stale"]),
        make_issue(),
        dry_run=False,
    )

    assert result.outcome == PostOutcome.POSTED
    assert result.detail is None
    github_client.apply_labels.assert_called_once_with("octo/repo", 42, ["bug"], ["stale"])


async def test_close_action_posts_comment_then_closes() -> None:
    executor, github_client = make_executor()

    result = await executor.execute(
        CloseAction(reason="duplicate", close_comment="Duplicate of #10."),
        make_issue(),
        dry_run=False,
    )

    assert result.outcome == PostOutcome.POSTED
    github_client.close_issue.assert_called_once_with("octo/repo", 42, "Duplicate of #10.")


async def test_dry_run_returns_posted_without_calling_github() -> None:
    executor, github_client = make_executor()

    result = await executor.execute(
        CommentAction(comment_body="Thanks!"), make_issue(), dry_run=True
    )

    assert result.outcome == PostOutcome.POSTED
    assert result.detail is None
    github_client.post_comment.assert_not_called()


async def test_github_exception_produces_failed_result_with_error_detail() -> None:
    executor, github_client = make_executor()
    github_client.post_comment.side_effect = GithubException(500, {"message": "boom"}, None)

    result = await executor.execute(
        CommentAction(comment_body="Thanks!"), make_issue(), dry_run=False
    )

    assert result.outcome == PostOutcome.FAILED
    assert result.detail is not None
    assert "boom" in result.detail


async def test_code_fix_raises_assertion_error_with_dry_run_false() -> None:
    executor, _ = make_executor()

    with pytest.raises(AssertionError):
        await executor.execute(_code_fix_action(), make_issue(), dry_run=False)


async def test_code_fix_raises_assertion_error_even_with_dry_run_true() -> None:
    """The invariant guard must not be bypassable just because a run is
    simulated -- proves the guard runs before, not after, the dry-run
    short-circuit."""
    executor, github_client = make_executor()

    with pytest.raises(AssertionError):
        await executor.execute(_code_fix_action(), make_issue(), dry_run=True)

    github_client.post_comment.assert_not_called()
    github_client.apply_labels.assert_not_called()
    github_client.close_issue.assert_not_called()
