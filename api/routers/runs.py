from typing import Annotated, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status

from api.dependencies import RunServiceDep, require_bearer_token
from api.errors import to_http_exception
from api.schemas import RetryRequest, RunAcceptedResponse
from graph.schemas import ApprovalDecision, ApprovalRequest, RunStatus
from graph.state import thread_id_for
from services.errors import (
    DecisionMismatchError,
    IssueFetchError,
    NothingPendingError,
    RetryLimitExceededError,
    RunAlreadyInFlightError,
    RunNotFailedError,
    RunNotFoundError,
)
from services.triage_run_service import validate_decision_matches

GET_PENDING_APPROVAL_ROUTE_NAME = "get_pending_approval"

router = APIRouter(
    prefix="/runs/{owner}/{repo}/{issue_number}",
    tags=["runs"],
    dependencies=[Depends(require_bearer_token)],
)


class RunIdentity:
    """Every `/runs/{owner}/{repo}/{issue_number}` route addresses the same
    run by these three path params; this groups the two things 2+ routes
    derive from them -- `thread_id` and the shared "nothing pending" 404
    body -- onto one class rather than accumulating standalone functions.
    FastAPI resolves it straight from the path params via
    `Annotated[RunIdentity, Depends()]`, since `__init__`'s parameter names
    match this router's path template exactly."""

    def __init__(self, owner: str, repo: str, issue_number: int) -> None:
        self.owner = owner
        self.repo = repo
        self.issue_number = issue_number
        self.thread_id = thread_id_for(f"{owner}/{repo}", issue_number)

    @classmethod
    def from_repo_full_name(cls, repo_full_name: str, issue_number: int) -> RunIdentity:
        """Used by `api.routers.webhooks`, which only has `repo_full_name`
        (GitHub-guaranteed `owner/repo` shape) rather than the two path
        segments separately."""
        owner, repo = repo_full_name.split("/", 1)
        return cls(owner, repo, issue_number)

    def resume_path(self, request: Request) -> str:
        """The exact path a `Location` header must point at, derived from
        the actual registered route rather than re-typed as an f-string."""
        return request.app.url_path_for(
            GET_PENDING_APPROVAL_ROUTE_NAME,
            owner=self.owner,
            repo=self.repo,
            issue_number=self.issue_number,
        )

    async def raise_not_pending(self, service: RunServiceDep) -> NoReturn:
        """Always raises: `RunNotFoundError` if no row exists at all,
        `NothingPendingError` if one exists but isn't currently paused --
        the typed replacement for a hand-built 404 tuple, routed through
        `api.errors.to_http_exception` by both callers below like every
        other error path in this file."""
        record = await service.get_run(self.thread_id)
        if record is None:
            raise RunNotFoundError(self.thread_id)
        raise NothingPendingError(self.thread_id, record.status, record.error_message)


@router.get("/resume", response_model=ApprovalRequest, name=GET_PENDING_APPROVAL_ROUTE_NAME)
async def get_pending_approval(
    run: Annotated[RunIdentity, Depends()],
    service: RunServiceDep,
) -> ApprovalRequest:
    request = await service.get_pending_approval(run.thread_id)
    if request is not None:
        return request
    try:
        await run.raise_not_pending(service)
    except RunNotFoundError as exc:
        raise to_http_exception(exc, detail="no run found for this issue") from exc
    except NothingPendingError as exc:
        raise to_http_exception(exc) from exc


@router.post("/resume", status_code=status.HTTP_202_ACCEPTED, response_model=RunAcceptedResponse)
async def resume_run(
    run: Annotated[RunIdentity, Depends()],
    decision: ApprovalDecision,
    background_tasks: BackgroundTasks,
    service: RunServiceDep,
) -> RunAcceptedResponse:
    request = await service.get_pending_approval(run.thread_id)
    if request is None:
        try:
            await run.raise_not_pending(service)
        except RunNotFoundError as exc:
            raise to_http_exception(exc, detail="no run found for this issue") from exc
        except NothingPendingError as exc:
            raise to_http_exception(exc) from exc

    try:
        validate_decision_matches(request, decision)
    except DecisionMismatchError as exc:
        raise to_http_exception(exc) from exc

    try:
        await service.claim_resume(run.thread_id)
    except RunAlreadyInFlightError as exc:
        raise to_http_exception(exc, detail="resume already in progress") from exc

    background_tasks.add_task(service.run_resume, run.thread_id, decision)
    return RunAcceptedResponse(
        thread_id=run.thread_id, run_id=None, status=RunStatus.PENDING_APPROVAL
    )


@router.post("/retry", status_code=status.HTTP_202_ACCEPTED, response_model=RunAcceptedResponse)
async def retry_run(
    run: Annotated[RunIdentity, Depends()],
    body: RetryRequest,
    background_tasks: BackgroundTasks,
    service: RunServiceDep,
) -> RunAcceptedResponse:
    thread_id = run.thread_id
    try:
        issue, run_id = await service.prepare_retry(thread_id, dry_run_override=body.dry_run)
    except (RunNotFoundError, RunNotFailedError, RetryLimitExceededError) as exc:
        raise to_http_exception(exc) from exc
    except IssueFetchError as exc:
        # GithubException.__str__ embeds GitHub's raw API error body
        # (status + JSON payload) -- never echo that verbatim to an API
        # caller, even an authenticated one.
        raise to_http_exception(exc, detail="could not fetch issue from GitHub") from exc
    except RunAlreadyInFlightError as exc:
        raise to_http_exception(exc, detail="already being retried") from exc

    background_tasks.add_task(service.run_fresh, issue, run_id)
    return RunAcceptedResponse(thread_id=thread_id, run_id=run_id, status=RunStatus.RECEIVED)
