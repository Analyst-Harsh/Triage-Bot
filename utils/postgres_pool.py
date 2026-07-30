"""One shared `psycopg_pool.AsyncConnectionPool` per process for the
checkpointer (`graph.checkpointer.postgres_checkpointer`). The ORM-backed
`repositories.triage_run_repository.TriageRunRepository` uses its own,
separate SQLAlchemy-managed pool instead (`db.engine`) -- `langgraph-
checkpoint-postgres` isn't built on SQLAlchemy, so the two can't share a
pool object; both point at the same Postgres instance via the same
`settings.database_url`. `utils/episodic_memory_store.py`'s
`AsyncPostgresStore` likewise opens its own third pool via its own
`from_conn_string` -- unchanged by this module.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool


@asynccontextmanager
async def postgres_pool(
    database_url: str,
) -> AsyncGenerator[AsyncConnectionPool[AsyncConnection[DictRow]]]:
    """Opens with `open=False` then awaits `.open()` explicitly -- psycopg_pool
    deprecates implicit opening in the constructor. `min_size=1` keeps this
    cheap when the API process is idle; `max_size=10` bounds it well under
    Postgres's default `max_connections` even with the episodic-memory
    store's own pool open alongside it. `autocommit=True` is required by
    `AsyncPostgresSaver`: its `.setup()` migration runs `CREATE INDEX
    CONCURRENTLY`, which Postgres refuses to run inside a transaction block,
    and the saver manages its own transaction boundaries per-operation
    rather than relying on connection-level implicit transactions.
    `prepare_threshold: 0` matches what `AsyncPostgresSaver`/`AsyncPostgresStore`'s
    own `from_conn_string` sets by default -- without it, this hand-built
    pool would be the odd one out among the three feeding `AsyncPostgresSaver`
    with long-lived prepared statements enabled, a known source of `cached
    plan must not change result type` errors and unsafe behind a
    transaction-pooling proxy (PgBouncer)."""
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        database_url,
        connection_class=AsyncConnection[DictRow],
        kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": 0},
        min_size=1,
        max_size=10,
        open=False,
    )
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()
