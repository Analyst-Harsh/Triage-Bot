from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.dependencies import get_run_service
from api.routers.runs_collection import router
from api.schemas.run_list_response import RunListResponse
from api.schemas.run_summary import RunSummary
from api.schemas.run_summary_response import RunSummaryResponse
from config.settings import Settings, get_settings
from graph.schemas import IssueSource, RunStatus
from services.triage_run_record import TriageRunRecord
from tests.api._http import get

BEARER_TOKEN = "test-bearer-token"
AUTH_HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


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
        list_runs_result: RunListResponse | None = None,
        status_summary_result: RunSummaryResponse | None = None,
    ) -> None:
        self._list_runs_result = list_runs_result
        self._status_summary_result = status_summary_result
        self.list_runs_calls: list[dict[str, Any]] = []
        self.get_status_summary_calls: list[str | None] = []

    async def list_runs(self, **kwargs: Any) -> RunListResponse:
        self.list_runs_calls.append(kwargs)
        assert self._list_runs_result is not None
        return self._list_runs_result

    async def get_status_summary(self, *, repo_full_name: str | None = None) -> RunSummaryResponse:
        self.get_status_summary_calls.append(repo_full_name)
        assert self._status_summary_result is not None
        return self._status_summary_result


def make_app(service: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_bearer_token=SecretStr(BEARER_TOKEN)
    )
    app.dependency_overrides[get_run_service] = lambda: service
    return app


def make_list_response(**overrides: Any) -> RunListResponse:
    defaults: dict[str, Any] = {
        "items": [RunSummary.from_record(make_record())],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }
    defaults.update(overrides)
    return RunListResponse(**defaults)


def make_summary_response(**overrides: Any) -> RunSummaryResponse:
    defaults: dict[str, Any] = {
        "counts_by_status": dict.fromkeys(RunStatus, 0),
        "total_runs": 0,
    }
    defaults.update(overrides)
    return RunSummaryResponse(**defaults)


def test_list_runs_requires_bearer_token() -> None:
    client = TestClient(make_app(_FakeService()))
    response = get(client, "/runs")
    assert response.status_code == 401


def test_list_runs_returns_items_and_pagination_metadata() -> None:
    service = _FakeService(list_runs_result=make_list_response())
    client = TestClient(make_app(service))

    response = get(client, "/runs", headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["total_pages"] == 1


def test_list_runs_passes_filters_and_pagination_through() -> None:
    service = _FakeService(list_runs_result=make_list_response())
    client = TestClient(make_app(service))

    response = get(
        client,
        "/runs?status=failed&status=pending_approval&repo_full_name=octo/repo"
        "&source=webhook&page=2&page_size=10",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert service.list_runs_calls == [
        {
            "page": 2,
            "page_size": 10,
            "statuses": [RunStatus.FAILED, RunStatus.PENDING_APPROVAL],
            "repo_full_name": "octo/repo",
            "source": IssueSource.WEBHOOK,
        }
    ]


def test_list_runs_defaults_page_and_page_size() -> None:
    service = _FakeService(list_runs_result=make_list_response())
    client = TestClient(make_app(service))

    get(client, "/runs", headers=AUTH_HEADERS)

    assert service.list_runs_calls == [
        {
            "page": 1,
            "page_size": 20,
            "statuses": None,
            "repo_full_name": None,
            "source": None,
        }
    ]


def test_list_runs_rejects_page_size_above_cap() -> None:
    service = _FakeService(list_runs_result=make_list_response())
    client = TestClient(make_app(service))

    response = get(client, "/runs?page_size=1000", headers=AUTH_HEADERS)

    assert response.status_code == 422


def test_get_runs_summary_requires_bearer_token() -> None:
    client = TestClient(make_app(_FakeService()))
    response = get(client, "/runs/summary")
    assert response.status_code == 401


def test_get_runs_summary_returns_counts() -> None:
    result = make_summary_response(
        counts_by_status={**dict.fromkeys(RunStatus, 0), RunStatus.FAILED: 3},
        total_runs=3,
    )
    service = _FakeService(status_summary_result=result)
    client = TestClient(make_app(service))

    response = get(client, "/runs/summary", headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["counts_by_status"]["failed"] == 3
    assert body["total_runs"] == 3


def test_get_runs_summary_passes_repo_filter_through() -> None:
    service = _FakeService(status_summary_result=make_summary_response())
    client = TestClient(make_app(service))

    get(client, "/runs/summary?repo_full_name=octo/repo", headers=AUTH_HEADERS)

    assert service.get_status_summary_calls == ["octo/repo"]
