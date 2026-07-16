from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from inspect import isclass

import aiosqlite
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

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
    """Local-dev checkpointer factory: a SQLite-backed `AsyncSqliteSaver`
    scoped to the connection's lifetime. Production will get its own
    Postgres-backed factory once `api/` lands (see AGENTS.md).

    Opens the connection directly (mirroring what
    `AsyncSqliteSaver.from_conn_string` does internally) rather than using
    that classmethod, since it doesn't expose a `serde` override — needed
    here to pass the schema-aware serde from `_build_checkpoint_serde`.
    """
    async with aiosqlite.connect(db_path) as conn:
        yield AsyncSqliteSaver(conn, serde=_build_checkpoint_serde())
