"""Every custom exception `TriageRunService` raises, in one place -- mirrors
`graph/errors.py`'s existing convention of a dedicated errors module rather
than piling exceptions into the service file itself.

Each concrete exception's base class names the HTTP status it maps to
(`status_code`, a plain int) -- a status code is fixed per class of error via
inheritance rather than kept in a separate mapping table that a new
exception could forget to update. This module still never imports
FastAPI/HTTPException itself, so the service layer stays decoupled from the
web framework; `api/errors.py` is the thin adapter that turns `status_code`
into a real `HTTPException`."""

from graph.schemas import RunStatus


class ServiceError(Exception):
    """Base for every exception `TriageRunService` raises."""

    status_code: int

    def extra_detail(self) -> dict[str, object]:
        """Extra body fields beyond `detail`, keyed the same way
        `status_code` is: a per-class override rather than a second mapping
        table `api.errors.to_http_exception` would have to keep in sync."""
        return {}


class BadRequestError(ServiceError):
    status_code = 400


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class BadGatewayError(ServiceError):
    status_code = 502


class ServiceUnavailableError(ServiceError):
    status_code = 503


class RunAlreadyInFlightError(ConflictError):
    """A claim (fresh start, retry, or resume) lost the race: another
    request already owns this thread_id right now."""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        super().__init__(f"a run is already in flight for {thread_id}")


class RunNotFoundError(NotFoundError):
    """No `triage_runs` row exists for this thread_id at all."""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        super().__init__(f"no run found for {thread_id}")


class RunNotFailedError(ConflictError):
    """A retry was requested but the run's current status isn't `failed`."""

    def __init__(self, thread_id: str, current_status: RunStatus) -> None:
        self.thread_id = thread_id
        self.current_status = current_status
        super().__init__(f"{thread_id} is not failed (current status: {current_status.value})")

    def extra_detail(self) -> dict[str, object]:
        return {"status": self.current_status.value}


class NothingPendingError(NotFoundError):
    """A resume/pending-approval check found a run, but it isn't currently
    paused waiting on a decision -- the typed replacement for a hand-built
    404 body carrying the run's current status/error_message."""

    def __init__(
        self, thread_id: str, current_status: RunStatus, error_message: str | None
    ) -> None:
        self.thread_id = thread_id
        self.current_status = current_status
        self.error_message = error_message
        super().__init__(f"nothing pending approval for {thread_id}")

    def extra_detail(self) -> dict[str, object]:
        return {"status": self.current_status.value, "error_message": self.error_message}


class RetryLimitExceededError(ConflictError):
    """`GuardrailSettings.max_retry_attempts` has been reached for this
    thread_id -- needs manual investigation, not another automatic retry."""

    def __init__(self, thread_id: str, retry_count: int, max_retry_attempts: int) -> None:
        self.thread_id = thread_id
        self.retry_count = retry_count
        self.max_retry_attempts = max_retry_attempts
        super().__init__(
            f"{thread_id} has reached its retry limit ({retry_count}/{max_retry_attempts})"
        )


class IssueFetchError(BadGatewayError):
    """The issue could no longer be fetched from GitHub (deleted,
    inaccessible) when preparing a retry."""

    def __init__(self, thread_id: str, reason: str) -> None:
        self.thread_id = thread_id
        self.reason = reason
        super().__init__(f"could not fetch issue for {thread_id}: {reason}")


class DecisionMismatchError(BadRequestError):
    """A resume decision's index set doesn't exactly match the queued
    indices in the pending `ApprovalRequest`."""

    def __init__(self, decided: list[int], queued: list[int]) -> None:
        self.decided = decided
        self.queued = queued
        super().__init__(
            f"decision indices {sorted(decided)} do not match queued indices {sorted(queued)}"
        )


class LangfuseNotConfiguredError(ServiceUnavailableError):
    """`Settings.langfuse_public_key`/`langfuse_secret_key` are unset --
    trace data can't be fetched at all. Mirrors
    `api.dependencies.require_bearer_token`'s unset-secret 503: a
    server-configuration gap, not a client error."""

    def __init__(self) -> None:
        super().__init__(
            "Langfuse is not configured (LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY unset)"
        )


class TraceNotFoundError(NotFoundError):
    """`fetch_observations` succeeded but returned nothing for this
    trace_id -- tracing wasn't configured when this run happened, or
    ingestion hasn't caught up yet. Distinct from `RunNotFoundError` (no
    `triage_runs` row at all)."""

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        super().__init__(f"no trace data found in Langfuse for trace_id {trace_id}")


class TraceFetchError(BadGatewayError):
    """The Langfuse API call itself failed (network error, non-2xx
    response) -- distinct from `TraceNotFoundError`, which is a clean empty
    result, not a failure."""

    def __init__(self, trace_id: str, reason: str) -> None:
        self.trace_id = trace_id
        self.reason = reason
        super().__init__(f"could not fetch trace {trace_id} from Langfuse: {reason}")
