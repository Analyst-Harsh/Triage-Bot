from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.dependencies import get_run_service
from api.routers.runs import router as runs_router
from api.routers.webhooks import router as webhooks_router
from config.settings import Settings, get_settings
from services.errors import RunAlreadyInFlightError
from tests.api._http import post

WEBHOOK_SECRET = "test-webhook-secret"  # pragma: allowlist secret


class _FakeService:
    def __init__(self, *, claim_error: Exception | None = None) -> None:
        self._claim_error = claim_error
        self.claim_calls: list[Any] = []
        self.run_fresh_calls: list[Any] = []

    async def claim_fresh_run(self, issue: Any, *, run_id: Any, dry_run: bool) -> None:
        self.claim_calls.append((issue, run_id, dry_run))
        if self._claim_error is not None:
            raise self._claim_error

    async def run_fresh(self, issue: Any, run_id: Any) -> None:
        self.run_fresh_calls.append((issue, run_id))


def make_app(service: Any) -> FastAPI:
    # Both routers are included, matching `api/app.py`'s real composition --
    # `receive_github_webhook`'s `Location` header is derived from the
    # `runs` router's `get_pending_approval` route via `url_path_for`, which
    # only resolves if that route is actually registered on this app.
    app = FastAPI()
    app.include_router(webhooks_router)
    app.include_router(runs_router)
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret=SecretStr(WEBHOOK_SECRET)
    )
    app.dependency_overrides[get_run_service] = lambda: service
    return app


def make_payload(action: str = "opened") -> bytes:
    return json.dumps(
        {
            "action": action,
            "issue": {
                "number": 42,
                "title": "Crash on startup",
                "body": "App crashes.",
                "user": {"login": "octocat"},
                "author_association": "NONE",
                "labels": [],
                "created_at": datetime.now(UTC).isoformat(),
                "html_url": "https://github.com/octo/repo/issues/42",
            },
            "repository": {"full_name": "octo/repo"},
        }
    ).encode()


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_rejects_bad_signature() -> None:
    service = _FakeService()
    client = TestClient(make_app(service))
    body = make_payload()

    response = post(
        client,
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "X-GitHub-Event": "issues"},
    )

    assert response.status_code == 401
    assert service.claim_calls == []


def test_webhook_ignores_non_issues_event() -> None:
    service = _FakeService()
    client = TestClient(make_app(service))
    body = make_payload()

    response = post(
        client,
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "ping"},
    )

    assert response.status_code == 200
    assert service.claim_calls == []


def test_webhook_ignores_unhandled_action() -> None:
    service = _FakeService()
    client = TestClient(make_app(service))
    body = make_payload(action="closed")

    response = post(
        client,
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "issues"},
    )

    assert response.status_code == 200
    assert service.claim_calls == []


def test_webhook_ignores_malformed_payload() -> None:
    service = _FakeService()
    client = TestClient(make_app(service))
    body = json.dumps(
        {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Crash on startup",
                "body": "App crashes.",
                "user": None,
                "author_association": "NONE",
                "labels": [],
                "created_at": datetime.now(UTC).isoformat(),
                "html_url": "https://github.com/octo/repo/issues/42",
            },
            "repository": {"full_name": "octo/repo"},
        }
    ).encode()

    response = post(
        client,
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "issues"},
    )

    assert response.status_code == 200
    assert service.claim_calls == []
    assert response.json() == {"detail": "ignored malformed payload"}


def test_webhook_claims_and_schedules_run_on_opened() -> None:
    service = _FakeService()
    client = TestClient(make_app(service))
    body = make_payload(action="opened")

    response = post(
        client,
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "issues"},
    )

    assert response.status_code == 201
    assert response.headers["location"] == "/runs/octo/repo/42/resume"
    assert len(service.claim_calls) == 1
    # A real webhook delivery must never silently run in dry-run mode.
    assert service.claim_calls[0][2] is False
    assert len(service.run_fresh_calls) == 1
    body = response.json()
    assert body["thread_id"] == "octo/repo#42"
    assert body["status"] == "received"
    assert body["run_id"] is not None


def test_webhook_claims_and_schedules_run_on_reopened() -> None:
    service = _FakeService()
    client = TestClient(make_app(service))
    body = make_payload(action="reopened")

    response = post(
        client,
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "issues"},
    )

    assert response.status_code == 201
    assert len(service.claim_calls) == 1


def test_webhook_returns_200_on_duplicate_delivery() -> None:
    service = _FakeService(claim_error=RunAlreadyInFlightError("octo/repo#42"))
    client = TestClient(make_app(service))
    body = make_payload(action="opened")

    response = post(
        client,
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "issues"},
    )

    assert response.status_code == 200
    assert service.run_fresh_calls == []
    assert response.json() == {"detail": "already in progress"}
