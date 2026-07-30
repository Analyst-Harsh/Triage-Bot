from graph.schemas import RunStatus
from graph.schemas.base import StrictBaseModel


class ErrorDetail(StrictBaseModel):
    """Typed error-response body built by `api.errors.to_http_exception` --
    `status`/`error_message` are only ever populated by exceptions whose
    `services.errors.ServiceError.extra_detail()` supplies them (e.g.
    `RunNotFailedError`, `NothingPendingError`); every other exception's
    response carries `detail` alone."""

    detail: str
    status: RunStatus | None = None
    error_message: str | None = None
