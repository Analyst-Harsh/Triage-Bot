import asyncio
from uuid import UUID

import structlog
from github import GithubException

from graph.schemas import (
    ActionPostResult,
    CloseAction,
    CodeFixAction,
    CommentAction,
    DraftedAction,
    IssuePayload,
    LabelAction,
    PostOutcome,
)
from utils.diff_applier import DiffApplyError
from utils.github_client import GitHubClient, get_github_client

log = structlog.get_logger(__name__)

_MAX_PR_BODY_LOG_CHARS = 5_000


class ActionExecutor:
    """Executes one drafted action against GitHub, or -- in dry-run mode --
    simulates it. Shared by `AutoPostNode` (auto-posting LOW-risk actions)
    and `ApprovalQueueNode` (posting an action a human has approved), so the
    dry-run/failure-handling logic exists exactly once rather than being
    duplicated across every node that eventually posts something.

    `code_fix` actions are only ever posted via `ApprovalQueueNode`: they
    are always HIGH risk by `RiskCheckNode` policy, so `AutoPostNode` never
    routes one here. Posting one opens a pull request built from the diff
    (see `_post`'s `CodeFixAction` case) rather than commenting/labeling/
    closing.
    """

    def __init__(self) -> None:
        self._github_client: GitHubClient = get_github_client()

    async def execute(
        self, drafted: DraftedAction, issue: IssuePayload, *, dry_run: bool, run_id: UUID
    ) -> ActionPostResult:
        action = drafted.action

        if dry_run:
            log.info(
                "action_dry_run", issue_number=issue.issue_number, action_type=action.action_type
            )
            return ActionPostResult(outcome=PostOutcome.POSTED, detail=None)

        try:
            detail = await self._post(action, issue, rationale=drafted.rationale, run_id=run_id)
            return ActionPostResult(outcome=PostOutcome.POSTED, detail=detail)
        except (GithubException, DiffApplyError) as exc:
            log.warning(
                "action_post_failed",
                issue_number=issue.issue_number,
                action_type=action.action_type,
                error=str(exc),
            )
            return ActionPostResult(outcome=PostOutcome.FAILED, detail=str(exc))

    async def _post(
        self,
        action: CommentAction | LabelAction | CloseAction | CodeFixAction,
        issue: IssuePayload,
        *,
        rationale: str,
        run_id: UUID,
    ) -> str | None:
        """Matches on `action` itself (class patterns), not
        `action.action_type`, so `pyright` narrows `action` to the concrete
        variant and its type-specific fields (`comment_body`/
        `labels_to_add`/`close_comment`/`diff`) are usable below."""
        match action:
            case CommentAction():
                return await asyncio.to_thread(
                    self._github_client.post_comment,
                    issue.repo_full_name,
                    issue.issue_number,
                    action.comment_body,
                )
            case LabelAction():
                await asyncio.to_thread(
                    self._github_client.apply_labels,
                    issue.repo_full_name,
                    issue.issue_number,
                    action.labels_to_add,
                    action.labels_to_remove,
                )
                return None
            case CloseAction():
                await asyncio.to_thread(
                    self._github_client.close_issue,
                    issue.repo_full_name,
                    issue.issue_number,
                    action.close_comment,
                )
                return None
            case CodeFixAction():
                return await asyncio.to_thread(
                    self._github_client.create_pull_request_from_diff,
                    issue.repo_full_name,
                    diff=action.diff,
                    target_files=action.target_files,
                    base_commit_sha=action.base_commit_sha,
                    base_branch=action.base_ref,
                    branch_name=_build_branch_name(issue.issue_number, run_id),
                    title=_build_pr_title(issue),
                    body=_build_pr_body(issue, rationale, action),
                )


def _build_branch_name(issue_number: int, run_id: UUID) -> str:
    return f"triage-bot/issue-{issue_number}-{run_id.hex[:8]}"


def _build_pr_title(issue: IssuePayload) -> str:
    return f"Fix: {issue.title} (#{issue.issue_number})"


def _build_pr_body(issue: IssuePayload, rationale: str, action: CodeFixAction) -> str:
    sandbox = action.sandbox_result
    logs = sandbox.logs
    if len(logs) > _MAX_PR_BODY_LOG_CHARS:
        logs = f"{logs[:_MAX_PR_BODY_LOG_CHARS]}\n… [truncated]"
    status = "passed" if sandbox.passed else "FAILED"
    return (
        f"Fixes #{issue.issue_number}\n\n"
        f"{issue.url}\n\n"
        "## Rationale\n"
        f"{rationale}\n\n"
        "## Sandbox verification\n"
        f"- Command: `{sandbox.test_command}`\n"
        f"- Result: {status}\n"
        f"- Duration: {sandbox.duration_seconds:.2f}s\n\n"
        "<details><summary>Test output</summary>\n\n"
        f"```\n{logs}\n```\n"
        "</details>\n\n"
        f"Base commit: `{action.base_commit_sha}`\n\n"
        "---\n"
        "*This pull request was opened automatically by Triage Bot after human approval.*"
    )
