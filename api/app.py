"""FastAPI composition root: opens the checkpointer's shared psycopg pool,
the SQLAlchemy engine/session backing the ORM `triage_runs` repository, the
Researcher's tool set, and the episodic memory store once per process
(lifespan-scoped), constructs the one `TriageRunService` instance every
route handler shares via `app.state`, and closes everything on shutdown.

`tools.sandbox.sandbox_toolset` is deliberately *not* opened here -- it's
per-run (repo-scoped), constructed fresh inside `TriageRunService.run_fresh`/
`run_resume` for each call instead (see that module's docstring).
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from api.routers.runs import router as runs_router
from api.routers.runs_collection import router as runs_collection_router
from api.routers.webhooks import router as webhooks_router
from config.settings import get_settings
from db.engine import session_factory, triage_run_engine
from graph.checkpointer import postgres_checkpointer
from observability.tracing import ensure_langfuse_client
from repositories.triage_run_repository import TriageRunRepository
from services.triage_run_service import TriageRunService
from tools.mcp_clients import researcher_toolset
from utils.episodic_memory_store import episodic_memory_store
from utils.github_client import get_github_client
from utils.postgres_pool import postgres_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL must be set to run the API")
    ensure_langfuse_client(settings)

    async with AsyncExitStack() as stack:
        pool = await stack.enter_async_context(
            postgres_pool(settings.database_url.get_secret_value())
        )
        checkpointer = await stack.enter_async_context(postgres_checkpointer(pool))
        researcher_tools = await stack.enter_async_context(researcher_toolset(settings))
        memory_store = await stack.enter_async_context(episodic_memory_store(settings))
        engine = await stack.enter_async_context(
            triage_run_engine(settings.database_url.get_secret_value())
        )

        runs_repo = TriageRunRepository(
            session_factory(engine),
            stale_run_threshold=timedelta(minutes=settings.guardrails.stale_run_threshold_minutes),
            stale_resume_threshold=timedelta(
                minutes=settings.guardrails.stale_resume_threshold_minutes
            ),
        )

        app.state.run_service = TriageRunService(
            settings=settings,
            checkpointer=checkpointer,
            researcher_tools=researcher_tools,
            memory_store=memory_store,
            github_client=get_github_client(),
            runs_repo=runs_repo,
        )
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="Triage Bot API", lifespan=lifespan)
    app.include_router(webhooks_router)
    app.include_router(runs_collection_router)
    app.include_router(runs_router)
    return app


app = create_app()
