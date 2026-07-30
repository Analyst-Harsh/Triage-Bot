from typing import Any

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

import db.engine as db_engine_module
from db.engine import _sqlalchemy_url as sqlalchemy_url  # pyright: ignore[reportPrivateUsage]
from db.engine import session_factory, triage_run_engine


def test_sqlalchemy_url_adds_psycopg_dialect_suffix() -> None:
    assert (
        sqlalchemy_url("postgresql://user:pass@localhost:5432/db")  # pragma: allowlist secret
        == "postgresql+psycopg://user:pass@localhost:5432/db"  # pragma: allowlist secret
    )


def test_sqlalchemy_url_only_replaces_first_occurrence() -> None:
    # A password/db name containing the literal substring "postgresql://"
    # (contrived, but worth pinning) must not have a second replacement
    # applied -- only the leading scheme is ever rewritten.
    assert sqlalchemy_url("postgresql://postgresql://x") == "postgresql+psycopg://postgresql://x"


def test_session_factory_configures_expire_on_commit_false() -> None:
    # No real connection is opened by constructing an engine or a
    # sessionmaker -- both are lazy. Uses aiosqlite (already a dev
    # dependency for the SQLite checkpointer) purely as a throwaway engine
    # to construct against, matching this repo's convention of not
    # requiring a live Postgres for unit tests.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    factory = session_factory(engine)

    assert factory.kw["expire_on_commit"] is False


class _FakeConn:
    async def run_sync(self, _fn: Any) -> None:
        return None


class _FakeBeginContext:
    async def __aenter__(self) -> _FakeConn:
        return _FakeConn()

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeEngine:
    """Stands in for the real `AsyncEngine`: SQLite's pool class doesn't
    accept `pool_size`/`max_overflow` (would raise at construction), and
    `triage_run_engine` unconditionally calls `.begin()`/`.dispose()`, so a
    real throwaway engine can't be used here the way `session_factory`'s
    test above does -- `create_async_engine` itself is faked instead."""

    def begin(self) -> _FakeBeginContext:
        return _FakeBeginContext()

    async def dispose(self) -> None:
        return None


async def test_triage_run_engine_uses_explicit_deliberate_pool_sizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    def _fake_create_async_engine(_url: str, **kwargs: Any) -> _FakeEngine:
        captured_kwargs.update(kwargs)
        return _FakeEngine()

    monkeypatch.setattr(db_engine_module, "create_async_engine", _fake_create_async_engine)

    async with triage_run_engine("postgresql://example") as engine:
        assert isinstance(engine, _FakeEngine)

    assert captured_kwargs == {"pool_size": 5, "max_overflow": 10, "pool_pre_ping": True}
