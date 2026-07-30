from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.schemas import (
    DetailResponse,
    ErrorDetail,
    GitHubIssuesEvent,
    RetryRequest,
    RunAcceptedResponse,
)
from graph.schemas import RunStatus


def test_retry_request_defaults_dry_run_to_none() -> None:
    assert RetryRequest().dry_run is None


def test_retry_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RetryRequest.model_validate({"unexpected_field": True})


def test_run_accepted_response_round_trips() -> None:
    response = RunAcceptedResponse(
        thread_id="octo/repo#42", run_id=uuid4(), status=RunStatus.RECEIVED
    )
    dumped = response.model_dump(mode="json")
    assert dumped["thread_id"] == "octo/repo#42"
    assert dumped["run_id"] is not None
    assert dumped["status"] == "received"


def test_run_accepted_response_allows_run_id_none_for_a_resume() -> None:
    # A resume continues an existing run rather than minting a new one, so
    # `run_id` is `None` for that caller (`api/routers/runs.py::resume_run`)
    # -- unlike a fresh webhook claim or a retry, both of which pass a real
    # `run_id`.
    response = RunAcceptedResponse(
        thread_id="octo/repo#42", run_id=None, status=RunStatus.PENDING_APPROVAL
    )
    dumped = response.model_dump(mode="json")
    assert dumped["run_id"] is None
    assert dumped["status"] == "pending_approval"


def test_run_accepted_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RunAcceptedResponse.model_validate(
            {
                "thread_id": "octo/repo#42",
                "run_id": str(uuid4()),
                "status": "received",
                "extra_field": "sneaky",
            }
        )


def test_detail_response_round_trips() -> None:
    response = DetailResponse(detail="already in progress")
    restored = DetailResponse.model_validate_json(response.model_dump_json())
    assert restored == response


def test_detail_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DetailResponse.model_validate({"detail": "ok", "extra_field": "sneaky"})


def test_error_detail_round_trips_with_only_detail() -> None:
    detail = ErrorDetail(detail="no run found for octo/repo#42")
    restored = ErrorDetail.model_validate_json(detail.model_dump_json())
    assert restored == detail


def test_error_detail_round_trips_with_status_and_error_message() -> None:
    detail = ErrorDetail(
        detail="nothing pending approval for octo/repo#42",
        status=RunStatus.FAILED,
        error_message="boom",
    )
    restored = ErrorDetail.model_validate_json(detail.model_dump_json())
    assert restored == detail


def test_error_detail_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail.model_validate({"detail": "ok", "extra_field": "sneaky"})


def test_github_issues_event_ignores_unknown_fields() -> None:
    payload = {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Crash on startup",
            "body": "App crashes.",
            "user": {"login": "octocat", "id": 999, "extra": "ignored"},
            "author_association": "NONE",
            "labels": [{"name": "bug", "color": "ff0000"}],
            "created_at": datetime.now(UTC).isoformat(),
            "html_url": "https://github.com/octo/repo/issues/42",
            "some_field_github_added_later": "ignored",
        },
        "repository": {"full_name": "octo/repo", "id": 123, "private": False},
        "sender": {"login": "someone-else"},
    }

    event = GitHubIssuesEvent.model_validate(payload)

    assert event.action == "opened"
    assert event.issue.number == 42
    assert event.issue.user.login == "octocat"
    assert event.issue.labels[0].name == "bug"
    assert event.repository.full_name == "octo/repo"


def test_github_issues_event_defaults_body_and_labels() -> None:
    payload = {
        "action": "reopened",
        "issue": {
            "number": 7,
            "title": "No body issue",
            "user": {"login": "someone"},
            "created_at": datetime.now(UTC).isoformat(),
            "html_url": "https://github.com/octo/repo/issues/7",
        },
        "repository": {"full_name": "octo/repo"},
    }

    event = GitHubIssuesEvent.model_validate(payload)

    assert event.issue.body is None
    assert event.issue.labels == []
    assert event.issue.author_association is None
