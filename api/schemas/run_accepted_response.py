from uuid import UUID

from graph.schemas import RunStatus
from graph.schemas.base import StrictBaseModel


class RunAcceptedResponse(StrictBaseModel):
    """Response body for a run now in flight: a fresh webhook claim, a
    retry, or a resume, all scheduled as a background task and not yet
    finished. `run_id` is `None` for a resume -- unlike a fresh claim or a
    retry, resuming doesn't mint a new `run_id`, it continues the existing
    one. `status` reflects the run's actual current status rather than an
    invented ad hoc label: `RunStatus.RECEIVED` for a fresh claim/retry,
    `RunStatus.PENDING_APPROVAL` for a resume (per
    `repositories.triage_run_repository.TriageRunRepository.claim_resume`'s
    own docstring, `status` doesn't change value until the run settles)."""

    thread_id: str
    run_id: UUID | None = None
    status: RunStatus
