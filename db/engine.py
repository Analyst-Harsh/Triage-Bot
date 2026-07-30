"""SQLAlchemy async engine + session factory for the ORM-backed
`triage_runs` table (`repositories.triage_run_repository`). Separate from
the checkpointer's own `psycopg_pool.AsyncConnectionPool`
(`utils.postgres_pool`) -- `langgraph-checkpoint-postgres` isn't built on
SQLAlchemy, so the two can't share a pool object; both point at the same
Postgres instance via the same `settings.database_url`. Three connection
pools, one database: the checkpointer's `psycopg_pool`, this SQLAlchemy
engine, and `utils/episodic_memory_store.py`'s own `AsyncPostgresStore` pool
-- the natural consequence of putting a real ORM in front of this one table
while the checkpointer and episodic memory store each stay on their own
native driver. This engine's pool is explicitly sized (`pool_size=5,
max_overflow=10`, capped at 15 connections) rather than left at whatever
SQLAlchemy's own default happens to be, so the total budget across all three
pools is a deliberate, stated number: this engine's 15 + the checkpointer
pool's `max_size=10` (`utils/postgres_pool.py`) + the episodic store's
`max_size=5` = 30, comfortably under Postgres's default
`max_connections=100` -- assuming a single API process/replica; this budget
must be revisited (lower per-process caps, or an external pooler) before
running more than one.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models.base import Base


def _sqlalchemy_url(database_url: str) -> str:
    """SQLAlchemy needs the `+psycopg` dialect suffix to select the
    async-capable psycopg v3 dialect; every other consumer of
    `settings.database_url` in this codebase (the checkpointer's
    `psycopg_pool`, `AsyncPostgresStore`) takes the plain `postgresql://`
    DSN directly. Converting it in this one place keeps that distinction
    from leaking into callers."""
    return database_url.replace("postgresql://", "postgresql+psycopg://", 1)


@asynccontextmanager
async def triage_run_engine(database_url: str) -> AsyncGenerator[AsyncEngine]:
    """Opens one engine for the process's lifetime, creates the
    `triage_runs` table if it doesn't exist yet (idempotent, safe on every
    process start -- the ORM-native equivalent of `utils/episodic_memory_
    store.py`'s `pg_store.setup()` convention), and disposes the engine's
    pool on exit. `create_all` is a sync method, hence `run_sync` to bridge
    it through the async connection. `pool_pre_ping=True` brings this engine
    to parity with the other two pools, which get idle/lifetime connection
    recycling for free from `psycopg_pool`'s own defaults -- the
    `triage_runs` table this pool backs can go untouched for hours/days
    while a row sits at `pending_approval`, making a dead connection on the
    next claim attempt a real risk without it."""
    engine = create_async_engine(
        _sqlalchemy_url(database_url), pool_size=5, max_overflow=10, pool_pre_ping=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
