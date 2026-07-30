"""Episodic memory: the store `PlannerNode` reads past-issue similarity hits
from, and `AutoPostNode`/`ApprovalQueueNode` write a completed run's outcome
into. Backed by LangGraph's own `AsyncPostgresStore` (`langgraph.store.postgres`)
-- the framework's long-term/cross-thread memory primitive, the intended
complement to the checkpointer (short-term/per-thread) already in this
project -- rather than a hand-rolled `asyncpg`/pgvector layer: it already
handles versioned migrations, non-locking (`CONCURRENTLY`) vector index
creation, and semantic search (embed-on-write/embed-on-query) internally.

Composition-root pattern mirrors `graph.checkpointer.sqlite_checkpointer`/
`tools.sandbox.sandbox_toolset`: `episodic_memory_store()` is the async
context manager `main.py` opens once and threads through `build_graph()` --
`AsyncPostgresStore.from_conn_string()` is itself an async context manager,
matching that shape directly.

`Settings.database_url` unset (the default) yields a
`NullEpisodicMemoryStore` -- mirrors the Researcher's DocMind-optional
degrade pattern: episodic memory is an enhancement, not a hard dependency.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
import structlog
from langchain_openai import OpenAIEmbeddings
from langgraph.store.base import SearchItem
from langgraph.store.postgres import AsyncPostgresStore, PoolConfig
from langgraph.store.postgres.base import PostgresIndexConfig
from openai import OpenAIError

from config.settings import Settings
from graph.schemas import (
    ActionType,
    DraftedAction,
    Episode,
    EpisodicActionOutcome,
    EpisodicMemoryHit,
    IssuePayload,
    PlannerOutput,
    PostOutcome,
    PostResults,
    RiskAssessment,
    RunStatus,
)

log = structlog.get_logger(__name__)


class EpisodicMemoryUnavailableError(Exception):
    """Raised by `EpisodicMemoryStore` when the underlying Postgres
    connection or the embedding call fails. Callers (`PlannerNode`/
    `AutoPostNode`/`ApprovalQueueNode`) catch this one specific type to
    degrade gracefully, rather than needing to know about `psycopg`'s or
    OpenAI's own exception hierarchies."""


class BaseEpisodicMemoryStore(ABC):
    """Read/write contract shared by the real store and its no-op
    stand-in, so calling nodes never need to branch on which is active."""

    @abstractmethod
    async def find_similar(self, issue: IssuePayload, *, top_k: int) -> list[EpisodicMemoryHit]:
        raise NotImplementedError

    @abstractmethod
    async def save_episode(
        self,
        *,
        run_id: UUID,
        issue: IssuePayload,
        planner_output: PlannerOutput,
        draft_actions: list[DraftedAction],
        risk_assessment: RiskAssessment | None,
        post_results: PostResults | None,
        outcome: RunStatus,
    ) -> None:
        raise NotImplementedError


class NullEpisodicMemoryStore(BaseEpisodicMemoryStore):
    """No-op stand-in used when `Settings.database_url` is unset, and as
    the test double for node tests that don't exercise memory behavior
    directly."""

    async def find_similar(
        self,
        issue: IssuePayload,  # noqa: ARG002
        *,
        top_k: int,  # noqa: ARG002
    ) -> list[EpisodicMemoryHit]:
        return []

    async def save_episode(
        self,
        *,
        run_id: UUID,  # noqa: ARG002
        issue: IssuePayload,  # noqa: ARG002
        planner_output: PlannerOutput,  # noqa: ARG002
        draft_actions: list[DraftedAction],  # noqa: ARG002
        risk_assessment: RiskAssessment | None,  # noqa: ARG002
        post_results: PostResults | None,  # noqa: ARG002
        outcome: RunStatus,  # noqa: ARG002
    ) -> None:
        return None


class EpisodicMemoryStore(BaseEpisodicMemoryStore):
    """Real implementation, backed by an `AsyncPostgresStore` already
    configured with embeddings (see `episodic_memory_store()`) -- this class
    only maps our domain shapes onto its generic namespace/key/value API."""

    def __init__(self, store: AsyncPostgresStore, *, namespace_prefix: tuple[str, ...]) -> None:
        self._store = store
        self._namespace_prefix = namespace_prefix

    async def find_similar(self, issue: IssuePayload, *, top_k: int) -> list[EpisodicMemoryHit]:
        try:
            # Deliberately narrower than save_episode's write namespace
            # (`(*self._namespace_prefix, repo)`): `asearch`'s `namespace_prefix`
            # is a genuine SQL prefix match (`store.prefix LIKE 'episodes%'`
            # -- verified against `AsyncPostgresStore`'s own query builder),
            # not an exact-namespace filter, so this one search call matches
            # every repo's sub-namespace -- cross-repo retrieval by design,
            # not an accidental namespace mismatch.
            items = await self._store.asearch(
                self._namespace_prefix, query=_issue_text(issue), limit=top_k
            )
        except (psycopg.Error, OSError, OpenAIError) as exc:
            raise EpisodicMemoryUnavailableError(str(exc)) from exc

        return [_item_to_hit(item) for item in items]

    async def save_episode(
        self,
        *,
        run_id: UUID,
        issue: IssuePayload,
        planner_output: PlannerOutput,
        draft_actions: list[DraftedAction],
        risk_assessment: RiskAssessment | None,
        post_results: PostResults | None,
        outcome: RunStatus,
    ) -> None:
        episode = Episode(
            run_id=run_id,
            repo_full_name=issue.repo_full_name,
            issue_number=issue.issue_number,
            issue_summary=issue.title,
            issue_type=planner_output.issue_type,
            issue_text=_issue_text(issue),
            actions_taken=draft_actions,
            risk_levels=(
                [a.level for a in risk_assessment.action_assessments] if risk_assessment else []
            ),
            post_results=post_results,
            outcome=outcome,
            created_at=datetime.now(UTC),
        )
        try:
            # Full/exact namespace, one level deeper than find_similar's
            # search prefix (`self._namespace_prefix` alone) -- organizes
            # writes per repo while still being covered by that broader
            # prefix match on read. See the comment in find_similar for why
            # the two aren't (and shouldn't be) the same tuple.
            await self._store.aput(
                (*self._namespace_prefix, issue.repo_full_name),
                key=str(run_id),
                value=episode.model_dump(mode="json"),
                index=["issue_text"],
            )
        except (psycopg.Error, OSError, OpenAIError) as exc:
            raise EpisodicMemoryUnavailableError(str(exc)) from exc


def _issue_text(issue: IssuePayload) -> str:
    return f"{issue.title}\n\n{issue.body}"


def _item_to_hit(item: SearchItem) -> EpisodicMemoryHit:
    """Maps one semantic-search result back onto the Planner-facing
    `EpisodicMemoryHit`. Folds any reviewer rejection note found in the
    stored `post_results` into `summary` -- this is where the "rejected
    because Y" signal actually surfaces, without a dedicated field."""
    value: dict[str, Any] = item.value
    actions_taken: list[dict[str, Any]] = value["actions_taken"]
    post_results: dict[str, Any] | None = value.get("post_results")
    action_results: list[dict[str, Any]] = (
        post_results["action_results"] if post_results is not None else []
    )

    actions = [
        EpisodicActionOutcome(
            action_type=ActionType(action["action"]["action_type"]),
            outcome=PostOutcome(result["outcome"]),
        )
        for action, result in zip(actions_taken, action_results, strict=True)
    ]

    rejection_notes = [
        result["detail"]
        for result in action_results
        if result["outcome"] == PostOutcome.REJECTED.value and result["detail"]
    ]
    summary = value["issue_summary"]
    if rejection_notes:
        summary = f"{summary} — rejected by reviewer: {'; '.join(rejection_notes)}"

    return EpisodicMemoryHit(
        past_issue_number=value["issue_number"],
        past_repo=value["repo_full_name"],
        summary=summary,
        actions_taken=actions,
        outcome=RunStatus(value["outcome"]),
        similarity_score=max(0.0, min(1.0, item.score if item.score is not None else 0.0)),
        retrieved_at=datetime.now(UTC),
    )


@asynccontextmanager
async def episodic_memory_store(settings: Settings) -> AsyncGenerator[BaseEpisodicMemoryStore]:
    """Yields `NullEpisodicMemoryStore()` if no database is configured.
    Otherwise opens an `AsyncPostgresStore` (small connection pool, semantic
    search configured via `index`), runs its migrations, yields the real
    store, and closes the pool on exit."""
    if settings.database_url is None:
        yield NullEpisodicMemoryStore()
        return

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_key=settings.openai_api_key,  # pyright: ignore[reportCallIssue]
        request_timeout=settings.guardrails.llm_request_timeout_seconds,  # pyright: ignore[reportCallIssue]
        max_retries=settings.guardrails.llm_max_retries,
    )
    index_config = PostgresIndexConfig(dims=settings.embedding_dimensions, embed=embeddings)

    async with AsyncPostgresStore.from_conn_string(
        settings.database_url.get_secret_value(),
        pool_config=PoolConfig(min_size=1, max_size=5),
        index=index_config,
    ) as pg_store:
        await pg_store.setup()
        yield EpisodicMemoryStore(
            pg_store, namespace_prefix=settings.episodic_memory_namespace_prefix
        )
