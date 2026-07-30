"""Thin adapter turning a `services.errors.ServiceError` into an
`HTTPException`, so `api/routers/runs.py` doesn't hand-roll its own
status-code choice per route -- the status code comes from `exc.status_code`
(see `services/errors.py`'s class hierarchy), never re-decided here. Extra
body fields (beyond `detail`) come from `exc.extra_detail()` -- a per-class
override on `ServiceError` itself, not a second table this module would have
to keep in sync with new exception types.

`api/routers/webhooks.py`'s `RunAlreadyInFlightError` -> 200 branch
deliberately does not use this adapter: a redelivered webhook is an
idempotent success, not a conflict, and that divergence is documented at its
own call site rather than folded into this shared table."""

from fastapi import HTTPException

from api.schemas import ErrorDetail
from services.errors import ServiceError


def to_http_exception(exc: ServiceError, *, detail: str | None = None) -> HTTPException:
    """`detail` overrides the default `str(exc)` message for a route that
    wants route-specific wording; the status code always comes from
    `exc.status_code` and is never overridable per-call."""
    body = ErrorDetail.model_validate(
        {"detail": detail if detail is not None else str(exc), **exc.extra_detail()}
    ).model_dump(mode="json", exclude_none=True)
    return HTTPException(exc.status_code, body)
