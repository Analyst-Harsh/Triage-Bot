from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import api.app as app_module
from config.settings import Settings


class _FakePool:
    pass


class _FakeCheckpointer:
    pass


class _FakeMemoryStore:
    pass


class _FakeEngine:
    pass


class _FakeRunsRepository:
    def __init__(
        self, session_factory: Any, *, stale_run_threshold: Any, stale_resume_threshold: Any
    ) -> None:
        self.session_factory = session_factory
        self.stale_run_threshold = stale_run_threshold
        self.stale_resume_threshold = stale_resume_threshold


@asynccontextmanager
async def _fake_postgres_pool(_database_url: str) -> AsyncGenerator[_FakePool]:
    yield _FakePool()


@asynccontextmanager
async def _fake_postgres_checkpointer(_pool: Any) -> AsyncGenerator[_FakeCheckpointer]:
    yield _FakeCheckpointer()


@asynccontextmanager
async def _fake_researcher_toolset(_settings: Any) -> AsyncGenerator[list[Any]]:
    yield []


@asynccontextmanager
async def _fake_episodic_memory_store(_settings: Any) -> AsyncGenerator[_FakeMemoryStore]:
    yield _FakeMemoryStore()


@asynccontextmanager
async def _fake_triage_run_engine(_database_url: str) -> AsyncGenerator[_FakeEngine]:
    yield _FakeEngine()


def _identity_session_factory(engine: _FakeEngine) -> _FakeEngine:
    return engine


def test_app_raises_at_startup_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "get_settings", lambda: Settings(database_url=None))
    app = app_module.create_app()

    with pytest.raises(RuntimeError, match="DATABASE_URL"), TestClient(app):
        pass


def test_app_wires_run_service_into_state(monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_langfuse_client_calls: list[Settings] = []
    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: Settings(
            database_url=SecretStr("postgresql://example"),
            api_bearer_token=SecretStr("secret"),
        ),
    )
    monkeypatch.setattr(app_module, "postgres_pool", _fake_postgres_pool)
    monkeypatch.setattr(app_module, "postgres_checkpointer", _fake_postgres_checkpointer)
    monkeypatch.setattr(app_module, "researcher_toolset", _fake_researcher_toolset)
    monkeypatch.setattr(app_module, "episodic_memory_store", _fake_episodic_memory_store)
    monkeypatch.setattr(app_module, "triage_run_engine", _fake_triage_run_engine)
    monkeypatch.setattr(app_module, "session_factory", _identity_session_factory)
    monkeypatch.setattr(app_module, "TriageRunRepository", _FakeRunsRepository)
    monkeypatch.setattr(app_module, "get_github_client", lambda: object())
    monkeypatch.setattr(app_module, "ensure_langfuse_client", ensure_langfuse_client_calls.append)

    app = app_module.create_app()
    with TestClient(app):
        assert app.state.run_service is not None
        assert isinstance(app.state.run_service.__class__, type)
        assert len(ensure_langfuse_client_calls) == 1
