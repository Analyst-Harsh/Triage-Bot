from collections.abc import AsyncGenerator
from typing import Any

import utils.postgres_pool as postgres_pool_module
from utils.postgres_pool import postgres_pool


class _FakeAsyncConnectionPool:
    """Duck-typed stand-in for `psycopg_pool.AsyncConnectionPool`:
    `postgres_pool()` only ever constructs one, awaits `.open()`, and later
    awaits `.close()`."""

    def __init__(self, conninfo: str, **kwargs: Any) -> None:
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True


async def test_postgres_pool_opens_and_closes(monkeypatch: Any) -> None:
    created: list[_FakeAsyncConnectionPool] = []

    def _fake_pool(conninfo: str, **kwargs: Any) -> _FakeAsyncConnectionPool:
        pool = _FakeAsyncConnectionPool(conninfo, **kwargs)
        created.append(pool)
        return pool

    monkeypatch.setattr(postgres_pool_module, "AsyncConnectionPool", _fake_pool)

    async def _use() -> AsyncGenerator[None]:
        async with postgres_pool("postgresql://example"):
            # Asserted via `created` (the fake instance the patched
            # constructor actually returned), not the `pool` variable bound
            # by `async with` -- that variable's static type is the real
            # `AsyncConnectionPool`, which has no `opened`/`closed`
            # attributes; those only exist on this test's fake.
            assert created[0].opened
            assert not created[0].closed
            yield

    async for _ in _use():
        pass

    assert len(created) == 1
    assert created[0].conninfo == "postgresql://example"
    assert created[0].closed


async def test_postgres_pool_uses_dict_row_factory(monkeypatch: Any) -> None:
    created: list[_FakeAsyncConnectionPool] = []

    def _fake_pool(conninfo: str, **kwargs: Any) -> _FakeAsyncConnectionPool:
        pool = _FakeAsyncConnectionPool(conninfo, **kwargs)
        created.append(pool)
        return pool

    monkeypatch.setattr(postgres_pool_module, "AsyncConnectionPool", _fake_pool)

    async with postgres_pool("postgresql://example"):
        pass

    assert created[0].kwargs["kwargs"] == {
        "row_factory": postgres_pool_module.dict_row,
        "autocommit": True,
        "prepare_threshold": 0,
    }


async def test_postgres_pool_uses_autocommit(monkeypatch: Any) -> None:
    """`AsyncPostgresSaver.setup()` runs `CREATE INDEX CONCURRENTLY`, which
    Postgres refuses to run inside a transaction block -- this pool must be
    opened with `autocommit=True` so no implicit transaction wraps it."""
    created: list[_FakeAsyncConnectionPool] = []

    def _fake_pool(conninfo: str, **kwargs: Any) -> _FakeAsyncConnectionPool:
        pool = _FakeAsyncConnectionPool(conninfo, **kwargs)
        created.append(pool)
        return pool

    monkeypatch.setattr(postgres_pool_module, "AsyncConnectionPool", _fake_pool)

    async with postgres_pool("postgresql://example"):
        pass

    assert created[0].kwargs["kwargs"]["autocommit"] is True


async def test_postgres_pool_uses_prepare_threshold_zero(monkeypatch: Any) -> None:
    """Matches what `AsyncPostgresSaver`/`AsyncPostgresStore`'s own
    `from_conn_string` sets by default -- without it, this hand-built pool
    would be the odd one out among the three feeding `AsyncPostgresSaver`
    with long-lived prepared statements enabled."""
    created: list[_FakeAsyncConnectionPool] = []

    def _fake_pool(conninfo: str, **kwargs: Any) -> _FakeAsyncConnectionPool:
        pool = _FakeAsyncConnectionPool(conninfo, **kwargs)
        created.append(pool)
        return pool

    monkeypatch.setattr(postgres_pool_module, "AsyncConnectionPool", _fake_pool)

    async with postgres_pool("postgresql://example"):
        pass

    assert created[0].kwargs["kwargs"]["prepare_threshold"] == 0
