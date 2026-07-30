from typing import Annotated
from uuid import uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from pydantic import ValidationError

from api.dependencies import RunServiceDep, verify_github_webhook_signature
from api.routers.runs import RunIdentity
from api.schemas import DetailResponse, GitHubIssuesEvent, RunAcceptedResponse
from graph.schemas import IssuePayload, IssueSource, RunStatus
from services.errors import RunAlreadyInFlightError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_TRIGGERING_ACTIONS = {"opened", "reopened"}


@router.post(
    "/github",
    status_code=status.HTTP_201_CREATED,
    response_model=RunAcceptedResponse | DetailResponse,
)
async def receive_github_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    service: RunServiceDep,
    raw_body: Annotated[bytes, Depends(verify_github_webhook_signature)],
) -> RunAcceptedResponse | DetailResponse:
    """Real production runs must never be silently dry-run: this is the one
    place `dry_run=False` is passed explicitly to `claim_fresh_run`, whose
    own signature has no default specifically so a caller can't forget."""
    event_type = request.headers.get("X-GitHub-Event")
    if event_type != "issues":
        response.status_code = status.HTTP_200_OK
        return DetailResponse(detail=f"ignored event type {event_type!r}")

    try:
        event = GitHubIssuesEvent.model_validate_json(raw_body)
    except ValidationError as exc:
        # An untrusted, external payload shape we don't control (e.g. a
        # deleted/ghost author account) -- treated as another "ignored, 2xx"
        # branch, same as an unhandled event type/action, so GitHub stops
        # redelivering something that can never succeed.
        log.warning("malformed_webhook_payload", error=str(exc))
        response.status_code = status.HTTP_200_OK
        return DetailResponse(detail="ignored malformed payload")

    if event.action not in _TRIGGERING_ACTIONS:
        response.status_code = status.HTTP_200_OK
        log.info(
            "ignored_action",
            action=event.action,
            repo=event.repository.full_name,
            issue=event.issue.number,
        )
        return DetailResponse(detail=f"ignored action {event.action!r}")

    issue = IssuePayload(
        repo_full_name=event.repository.full_name,
        issue_number=event.issue.number,
        title=event.issue.title,
        body=event.issue.body or "",
        author=event.issue.user.login,
        author_association=event.issue.author_association,
        labels=[label.name for label in event.issue.labels],
        created_at=event.issue.created_at,
        url=event.issue.html_url,
        source=IssueSource.WEBHOOK,
    )
    run = RunIdentity.from_repo_full_name(issue.repo_full_name, issue.issue_number)
    run_id = uuid4()

    try:
        await service.claim_fresh_run(issue, run_id=run_id, dry_run=False)
    except RunAlreadyInFlightError:
        # A redelivered webhook is expected, not an error -- returning 2xx
        # (not the 201 a genuine new claim gets) tells GitHub the delivery
        # succeeded so it doesn't keep retrying a request we've already
        # handled correctly. Deliberately not routed through
        # `api.errors.to_http_exception` (which would map this to 409): a
        # redelivery is an idempotent success from GitHub's point of view,
        # not a conflict.
        log.info("duplicate_delivery_ignored", thread_id=run.thread_id)
        response.status_code = status.HTTP_200_OK
        return DetailResponse(detail="already in progress")

    background_tasks.add_task(service.run_fresh, issue, run_id)
    response.headers["Location"] = run.resume_path(request)
    return RunAcceptedResponse(thread_id=run.thread_id, run_id=run_id, status=RunStatus.RECEIVED)
