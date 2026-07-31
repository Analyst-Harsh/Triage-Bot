from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.dependencies import get_run_service
from api.routers.runs import router
from api.schemas.run_detail_response import RunDetailResponse
from api.schemas.run_summary import RunSummary
from api.schemas.trace_summary_response import TraceSummaryResponse
from config.settings import Settings, get_settings
from graph.schemas import (
    ActionType,
    ApprovalRequest,
    IssuePayload,
    IssueSource,
    RiskLevel,
    RunStatus,
)
from graph.schemas.approval_request import QueuedActionSummary
from services.errors import (
    IssueFetchError,
    LangfuseNotConfiguredError,
    RetryLimitExceededError,
    RunAlreadyInFlightError,
    RunNotFailedError,
    RunNotFoundError,
    TraceFetchError,
    TraceNotFoundError,
)
from services.triage_run_record import TriageRunRecord
from tests.api._http import get, post

BEARER_TOKEN = "test-bearer-token"
AUTH_HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


def make_request() -> ApprovalRequest:
    return ApprovalRequest(
        run_id=uuid4(),
        repo_full_name="octo/repo",
        issue_number=42,
        issue_url="https://github.com/octo/repo/issues/42",
        actions=[
            QueuedActionSummary(
                index=0,
                action_type=ActionType.COMMENT,
                summary="s",
                rationale="r",
                risk_level=RiskLevel.MEDIUM,
                risk_reasoning="rr",
            )
        ],
        requested_at=datetime.now(UTC),
    )


def make_record(**overrides: Any) -> TriageRunRecord:
    now = datetime.now(UTC)
    defaults: dict[str, Any] = {
        "thread_id": "octo/repo#42",
        "run_id": uuid4(),
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "issue_title": "Crash on startup",
        "issue_url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK,
        "status": RunStatus.FAILED,
        "resume_in_progress": False,
        "retry_count": 0,
        "error_message": "boom",
        "dry_run": True,
        "estimated_cost_usd": None,
        "started_at": now,
        "updated_at": now,
        "completed_at": now,
    }
    defaults.update(overrides)
    return TriageRunRecord(**defaults)


class _FakeService:
    def __init__(
        self,
        *,
        pending_approval: ApprovalRequest | None = None,
        run: TriageRunRecord | None = None,
        run_detail: RunDetailResponse | None = None,
        claim_resume_error: Exception | None = None,
        prepare_retry_result: tuple[Any, Any] | None = None,
        prepare_retry_error: Exception | None = None,
        trace_summary: TraceSummaryResponse | None = None,
        trace_summary_error: Exception | None = None,
    ) -> None:
        self._pending_approval = pending_approval
        self._run = run
        self._run_detail = run_detail
        self._claim_resume_error = claim_resume_error
        self._prepare_retry_result = prepare_retry_result
        self._prepare_retry_error = prepare_retry_error
        self._trace_summary = trace_summary
        self._trace_summary_error = trace_summary_error
        self.run_resume_calls: list[Any] = []
        self.run_fresh_calls: list[Any] = []

    async def get_pending_approval(self, _thread_id: str) -> ApprovalRequest | None:
        return self._pending_approval

    async def get_run(self, _thread_id: str) -> TriageRunRecord | None:
        return self._run

    async def get_run_detail(self, _thread_id: str) -> RunDetailResponse | None:
        return self._run_detail

    async def get_trace_summary(self, _thread_id: str) -> TraceSummaryResponse:
        if self._trace_summary_error is not None:
            raise self._trace_summary_error
        assert self._trace_summary is not None
        return self._trace_summary

    async def claim_resume(self, thread_id: str) -> None:  # noqa: ARG002
        if self._claim_resume_error is not None:
            raise self._claim_resume_error

    async def run_resume(self, thread_id: str, decision: Any) -> None:
        self.run_resume_calls.append((thread_id, decision))

    async def prepare_retry(
        self,
        thread_id: str,  # noqa: ARG002
        *,
        dry_run_override: bool | None,  # noqa: ARG002
    ) -> Any:
        if self._prepare_retry_error is not None:
            raise self._prepare_retry_error
        assert self._prepare_retry_result is not None
        return self._prepare_retry_result

    async def run_fresh(self, issue: Any, run_id: Any) -> None:
        self.run_fresh_calls.append((issue, run_id))


def make_app(service: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_bearer_token=SecretStr(BEARER_TOKEN)
    )
    app.dependency_overrides[get_run_service] = lambda: service
    return app


def make_detail(**overrides: Any) -> RunDetailResponse:
    defaults: dict[str, Any] = {
        "run": RunSummary.from_record(make_record()),
        "planner_output": None,
        "research_findings": None,
        "draft": None,
        "risk_assessment": None,
        "post_results": None,
        "episodic_context": [],
        "run_meta": None,
    }
    defaults.update(overrides)
    return RunDetailResponse(**defaults)


def test_get_run_detail_requires_bearer_token() -> None:
    client = TestClient(make_app(_FakeService()))
    response = get(client, "/runs/octo/repo/42")
    assert response.status_code == 401


def test_get_run_detail_returns_404_when_no_run() -> None:
    service = _FakeService(run_detail=None)
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["detail"] == "no run found for this issue"


def test_get_run_detail_returns_combined_detail() -> None:
    service = _FakeService(run_detail=make_detail())
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42", headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["thread_id"] == "octo/repo#42"
    assert body["planner_output"] is None
    assert body["episodic_context"] == []


def make_trace_summary(**overrides: Any) -> TraceSummaryResponse:
    defaults: dict[str, Any] = {
        "trace_id": "deadbeef",
        "langfuse_url": "https://cloud.langfuse.com/trace/deadbeef",
        "total_latency_seconds": 5.0,
        "total_cost_usd": 0.01,
        "observations": [],
    }
    defaults.update(overrides)
    return TraceSummaryResponse(**defaults)


def test_get_trace_summary_requires_bearer_token() -> None:
    client = TestClient(make_app(_FakeService()))
    response = get(client, "/runs/octo/repo/42/trace")
    assert response.status_code == 401


def test_get_trace_summary_returns_200_with_summary() -> None:
    service = _FakeService(trace_summary=make_trace_summary())
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/trace", headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "deadbeef"
    assert body["observations"] == []


def test_get_trace_summary_returns_404_when_run_not_found() -> None:
    service = _FakeService(trace_summary_error=RunNotFoundError("octo/repo#42"))
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/trace", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["detail"] == "no run found for this issue"


def test_get_trace_summary_returns_404_when_trace_not_found() -> None:
    service = _FakeService(trace_summary_error=TraceNotFoundError("deadbeef"))
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/trace", headers=AUTH_HEADERS)

    assert response.status_code == 404


def test_get_trace_summary_returns_502_when_fetch_fails() -> None:
    service = _FakeService(trace_summary_error=TraceFetchError("deadbeef", "network error"))
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/trace", headers=AUTH_HEADERS)

    assert response.status_code == 502
    assert response.json()["detail"]["detail"] == "could not fetch trace from Langfuse"


def test_get_trace_summary_returns_503_when_langfuse_not_configured() -> None:
    service = _FakeService(trace_summary_error=LangfuseNotConfiguredError())
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/trace", headers=AUTH_HEADERS)

    assert response.status_code == 503


def test_get_resume_requires_bearer_token() -> None:
    client = TestClient(make_app(_FakeService()))
    response = get(client, "/runs/octo/repo/42/resume")
    assert response.status_code == 401


def test_get_resume_returns_request_when_pending() -> None:
    service = _FakeService(pending_approval=make_request())
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/resume", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["repo_full_name"] == "octo/repo"


def test_get_resume_returns_404_with_no_run_at_all() -> None:
    service = _FakeService(pending_approval=None, run=None)
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/resume", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["detail"] == "no run found for this issue"


def test_get_resume_returns_404_with_status_when_failed() -> None:
    service = _FakeService(pending_approval=None, run=make_record(status=RunStatus.FAILED))
    client = TestClient(make_app(service))

    response = get(client, "/runs/octo/repo/42/resume", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"]["status"] == "failed"
    assert response.json()["detail"]["error_message"] == "boom"


def test_post_resume_rejects_mismatched_decision() -> None:
    service = _FakeService(pending_approval=make_request())
    client = TestClient(make_app(service))

    response = post(
        client,
        "/runs/octo/repo/42/resume",
        json={"decisions": [{"index": 99, "approved": True}]},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 400
    assert service.run_resume_calls == []


def test_post_resume_returns_409_on_claim_conflict() -> None:
    service = _FakeService(
        pending_approval=make_request(),
        claim_resume_error=RunAlreadyInFlightError("octo/repo#42"),
    )
    client = TestClient(make_app(service))

    response = post(
        client,
        "/runs/octo/repo/42/resume",
        json={"decisions": [{"index": 0, "approved": True}]},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409


def test_post_resume_returns_404_when_nothing_pending() -> None:
    service = _FakeService(pending_approval=None, run=None)
    client = TestClient(make_app(service))

    response = post(
        client,
        "/runs/octo/repo/42/resume",
        json={"decisions": [{"index": 0, "approved": True}]},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


def test_post_resume_schedules_run_and_returns_202() -> None:
    service = _FakeService(pending_approval=make_request())
    client = TestClient(make_app(service))

    response = post(
        client,
        "/runs/octo/repo/42/resume",
        json={"decisions": [{"index": 0, "approved": True}]},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    assert len(service.run_resume_calls) == 1
    assert response.json() == {
        "thread_id": "octo/repo#42",
        "run_id": None,
        "status": "pending_approval",
    }


def test_post_retry_maps_run_not_found_to_404() -> None:
    service = _FakeService(prepare_retry_error=RunNotFoundError("octo/repo#42"))
    client = TestClient(make_app(service))

    response = post(client, "/runs/octo/repo/42/retry", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 404


def test_post_retry_maps_run_not_failed_to_409_with_status() -> None:
    service = _FakeService(
        prepare_retry_error=RunNotFailedError("octo/repo#42", RunStatus.PENDING_APPROVAL)
    )
    client = TestClient(make_app(service))

    response = post(client, "/runs/octo/repo/42/retry", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "pending_approval"


def test_post_retry_maps_retry_limit_exceeded_to_409() -> None:
    service = _FakeService(prepare_retry_error=RetryLimitExceededError("octo/repo#42", 3, 3))
    client = TestClient(make_app(service))

    response = post(client, "/runs/octo/repo/42/retry", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 409


def test_post_retry_maps_issue_fetch_error_to_502() -> None:
    service = _FakeService(prepare_retry_error=IssueFetchError("octo/repo#42", "404"))
    client = TestClient(make_app(service))

    response = post(client, "/runs/octo/repo/42/retry", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 502
    # Never echo GithubException's raw message (which embeds GitHub's own
    # API error body) verbatim back to the caller.
    assert response.json()["detail"]["detail"] == "could not fetch issue from GitHub"


def test_post_retry_maps_claim_conflict_to_409() -> None:
    service = _FakeService(prepare_retry_error=RunAlreadyInFlightError("octo/repo#42"))
    client = TestClient(make_app(service))

    response = post(client, "/runs/octo/repo/42/retry", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 409


def test_post_retry_schedules_run_and_returns_202() -> None:
    issue = IssuePayload(
        repo_full_name="octo/repo",
        issue_number=42,
        title="Crash on startup",
        body="App crashes.",
        author="octocat",
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/42",
        source=IssueSource.REPLAY,
    )
    run_id = uuid4()
    service = _FakeService(prepare_retry_result=(issue, run_id))
    client = TestClient(make_app(service))

    response = post(client, "/runs/octo/repo/42/retry", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 202
    body = response.json()
    assert body["thread_id"] == "octo/repo#42"
    assert body["run_id"] == str(run_id)
    assert len(service.run_fresh_calls) == 1


def test_post_retry_honors_dry_run_override_in_body() -> None:
    issue = IssuePayload(
        repo_full_name="octo/repo",
        issue_number=42,
        title="Crash on startup",
        body="App crashes.",
        author="octocat",
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/42",
        source=IssueSource.REPLAY,
    )
    service = _FakeService(prepare_retry_result=(issue, uuid4()))
    client = TestClient(make_app(service))

    response = post(
        client, "/runs/octo/repo/42/retry", json={"dry_run": True}, headers=AUTH_HEADERS
    )

    assert response.status_code == 202


def test_post_retry_rejects_unknown_body_fields() -> None:
    service = _FakeService(prepare_retry_result=(None, None))
    client = TestClient(make_app(service))

    response = post(
        client, "/runs/octo/repo/42/retry", json={"unexpected": True}, headers=AUTH_HEADERS
    )

    assert response.status_code == 422
