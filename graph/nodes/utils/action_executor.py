import asyncio

import structlog
from github import GithubException

from api.github_client import GitHubClient, get_github_client
from graph.schemas import (
    ActionPostResult,
    CloseAction,
    CodeFixAction,
    CommentAction,
    DraftAction,
    IssuePayload,
    LabelAction,
    PostOutcome,
)

log = structlog.get_logger(__name__)


class ActionExecutor:
    """Executes one drafted action against GitHub, or -- in dry-run mode --
    simulates it. Shared by `AutoPostNode` (auto-posting LOW-risk actions)
    and `ApprovalQueueNode` (posting an action a human has approved), so the
    dry-run/failure-handling logic exists exactly once rather than being
    duplicated across every node that eventually posts something.
    """

    def __init__(self) -> None:
        self._github_client: GitHubClient = get_github_client()

    async def execute(
        self, action: DraftAction, issue: IssuePayload, *, dry_run: bool
    ) -> ActionPostResult:
        # `code_fix` is never postable, regardless of dry_run -- this guard
        # fires unconditionally, before the dry-run short-circuit below, so
        # simulating a run can never mask the policy violation. Unreachable
        # in real traffic (RiskCheckNode hardcodes code_fix to HIGH), but
        # trusting that invariant silently here would defeat the point of
        # asserting it. Also narrows `action` for pyright to the 3 remaining
        # variants `_post` handles.
        if isinstance(action, CodeFixAction):
            raise AssertionError(
                "code_fix actions are never LOW risk by RiskCheckNode policy; "
                "ActionExecutor must never attempt to post one"
            )

        if dry_run:
            log.info(
                "action_dry_run", issue_number=issue.issue_number, action_type=action.action_type
            )
            return ActionPostResult(outcome=PostOutcome.POSTED, detail=None)

        try:
            detail = await self._post(action, issue)
            return ActionPostResult(outcome=PostOutcome.POSTED, detail=detail)
        except GithubException as exc:
            log.warning(
                "action_post_failed",
                issue_number=issue.issue_number,
                action_type=action.action_type,
                error=str(exc),
            )
            return ActionPostResult(outcome=PostOutcome.FAILED, detail=str(exc))

    async def _post(
        self, action: CommentAction | LabelAction | CloseAction, issue: IssuePayload
    ) -> str | None:
        """Matches on `action` itself (class patterns), not
        `action.action_type`, so `pyright` narrows `action` to the concrete
        variant and its type-specific fields (`comment_body`/
        `labels_to_add`/`close_comment`) are usable below."""
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
