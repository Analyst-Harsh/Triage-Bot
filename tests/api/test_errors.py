from typing import cast

import pytest
from fastapi import HTTPException

from api.errors import to_http_exception
from graph.schemas import RunStatus
from services.errors import (
    BadGatewayError,
    BadRequestError,
    ConflictError,
    DecisionMismatchError,
    IssueFetchError,
    NotFoundError,
    NothingPendingError,
    RetryLimitExceededError,
    RunAlreadyInFlightError,
    RunNotFailedError,
    RunNotFoundError,
    ServiceError,
)


def test_base_classes_carry_their_own_status_code() -> None:
    assert BadRequestError.status_code == 400
    assert NotFoundError.status_code == 404
    assert ConflictError.status_code == 409
    assert BadGatewayError.status_code == 502


def _body(http_exc: HTTPException) -> dict[str, object]:
    # `HTTPException.detail` is typed `str | None` in Starlette's own
    # `__init__` (the attribute's inferred type follows that assignment,
    # even though FastAPI's subclass accepts `Any`), but `to_http_exception`
    # always constructs it with a `dict[str, object]` body -- casting once
    # here avoids sprinkling `# type: ignore`s across every assertion below.
    return cast(dict[str, object], http_exc.detail)


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (DecisionMismatchError([0], [1]), 400),
        (RunNotFoundError("octo/repo#42"), 404),
        (RunAlreadyInFlightError("octo/repo#42"), 409),
        (RunNotFailedError("octo/repo#42", RunStatus.RECEIVED), 409),
        (RetryLimitExceededError("octo/repo#42", 3, 3), 409),
        (IssueFetchError("octo/repo#42", "deleted"), 502),
    ],
)
def test_to_http_exception_uses_status_code_from_exception_class(
    exc: ServiceError, expected_status: int
) -> None:
    http_exc = to_http_exception(exc)
    assert http_exc.status_code == expected_status
    # RunNotFailedError's body additionally carries "status" -- covered
    # separately below -- so only the "detail" key is checked generically.
    assert _body(http_exc)["detail"] == str(exc)


def test_to_http_exception_detail_override_does_not_change_status() -> None:
    exc = RunAlreadyInFlightError("octo/repo#42")

    http_exc = to_http_exception(exc, detail="resume already in progress")

    assert http_exc.status_code == 409
    assert _body(http_exc) == {"detail": "resume already in progress"}


def test_to_http_exception_includes_current_status_for_run_not_failed() -> None:
    exc = RunNotFailedError("octo/repo#42", RunStatus.PENDING_APPROVAL)

    http_exc = to_http_exception(exc)

    assert _body(http_exc) == {"detail": str(exc), "status": "pending_approval"}


def test_to_http_exception_includes_status_and_error_message_for_nothing_pending() -> None:
    exc = NothingPendingError("octo/repo#42", RunStatus.FAILED, "boom")

    http_exc = to_http_exception(exc)

    assert http_exc.status_code == 404
    assert _body(http_exc) == {"detail": str(exc), "status": "failed", "error_message": "boom"}


def test_to_http_exception_omits_null_error_message_for_nothing_pending() -> None:
    """`exclude_none=True` means a `None` `error_message` is omitted from the
    body entirely, rather than included as an explicit `null` -- a
    deliberate, minor wire-shape change from the hand-built dict this
    replaced."""
    exc = NothingPendingError("octo/repo#42", RunStatus.RECEIVED, None)

    http_exc = to_http_exception(exc)

    body = _body(http_exc)
    assert body == {"detail": str(exc), "status": "received"}
    assert "error_message" not in body
