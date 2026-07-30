from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from inspect import isclass

import aiosqlite
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool

from graph import schemas as graph_schemas

DEFAULT_CHECKPOINT_DB_PATH = "checkpoints.db"


def _build_checkpoint_serde() -> JsonPlusSerializer:
    """Explicitly allow-lists every schema type nested in `TriageState` for
    checkpoint (de)serialization.

    `JsonPlusSerializer` warns by default on any custom type it isn't
    explicitly told is safe ("Deserializing unregistered type ... This will
    be blocked in a future version") — reconstructing an arbitrary Python
    class from checkpoint bytes is a real deserialization-attack surface
    (an attacker with write access to the checkpoint store could otherwise
    trigger instantiation of an arbitrary class on load), so LangGraph is
    moving toward blocking anything not on an explicit allow-list.

    Derived from `graph.schemas.__all__` rather than a hand-maintained list
    of module/class-name strings, so a new schema added there is covered
    automatically instead of silently reintroducing the warning.
    """
    allowed_types = [
        obj for name in graph_schemas.__all__ if isclass(obj := getattr(graph_schemas, name))
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=allowed_types)


@asynccontextmanager
async def sqlite_checkpointer(
    db_path: str = DEFAULT_CHECKPOINT_DB_PATH,
) -> AsyncGenerator[AsyncSqliteSaver]:
    """Local-dev/replay checkpointer factory: a SQLite-backed
    `AsyncSqliteSaver` scoped to the connection's lifetime. `main.py` (the
    replay pipeline) and this module's own tests are its only callers --
    production (`api/app.py`) uses `postgres_checkpointer` below instead.

    Opens the connection directly (mirroring what
    `AsyncSqliteSaver.from_conn_string` does internally) rather than using
    that classmethod, since it doesn't expose a `serde` override — needed
    here to pass the schema-aware serde from `_build_checkpoint_serde`.
    """
    async with aiosqlite.connect(db_path) as conn:
        yield AsyncSqliteSaver(conn, serde=_build_checkpoint_serde())


@asynccontextmanager
async def postgres_checkpointer(
    pool: AsyncConnectionPool[AsyncConnection[DictRow]],
) -> AsyncGenerator[AsyncPostgresSaver]:
    """Production checkpointer factory: builds an `AsyncPostgresSaver` over
    an already-open, externally-owned connection pool (see
    `utils.postgres_pool`) -- shared with the episodic memory store's own
    pool only in the sense of pointing at the same Postgres instance, not
    the same pool object (that store opens its own via `from_conn_string`).
    `AsyncPostgresSaver.__init__` accepts a pool directly (confirmed against
    `langgraph.checkpoint.postgres._ainternal.Conn`'s type alias:
    `AsyncConnection[DictRow] | AsyncConnectionPool[AsyncConnection[DictRow]]`),
    so no per-checkpointer pool is created here. Runs `.setup()` once --
    idempotent, safe on every process start, the same convention
    `utils/episodic_memory_store.py`'s `pg_store.setup()` already uses --
    before yielding.

    Uses the same schema-aware serde as `sqlite_checkpointer` (see
    `_build_checkpoint_serde`'s docstring for why): checkpoint bytes are the
    same deserialization-attack surface regardless of which database stores
    them.
    """
    saver = AsyncPostgresSaver(pool, serde=_build_checkpoint_serde())
    await saver.setup()
    yield saver
