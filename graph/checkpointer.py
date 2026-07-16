from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

DEFAULT_CHECKPOINT_DB_PATH = "checkpoints.db"


@asynccontextmanager
async def sqlite_checkpointer(
    db_path: str = DEFAULT_CHECKPOINT_DB_PATH,
) -> AsyncGenerator[AsyncSqliteSaver]:
    """Local-dev checkpointer factory: a SQLite-backed `AsyncSqliteSaver`
    scoped to the connection's lifetime. Production will get its own
    Postgres-backed factory once `api/` lands (see AGENTS.md)."""
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        yield checkpointer
