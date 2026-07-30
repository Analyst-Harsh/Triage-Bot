"""All SQLAlchemy queries against the `triage_runs` table live here -- the
only place in the codebase that constructs a query against `models.TriageRun`.
`services.triage_run_service.TriageRunService` calls this class and never
touches SQLAlchemy directly.

The atomic claim methods (`claim_fresh_run`/`claim_retry`/`claim_resume`) are
the sole concurrency guard for the API: a run stays in flight for minutes
(LLM/tool calls), so guarding only the starting instant isn't enough, and an
in-process lock wouldn't survive more than one API worker. Each claim is a
single statement -- Postgres takes the row lock for that one statement, not
for the run's whole duration.

`_claimable()` governs two of the three races this guards against:
  1. Duplicate start (a redelivered webhook, or a webhook racing a retry) --
     a row is claimable if it's already terminal.
  2. A crashed process -- `updated_at` doubles as a heartbeat (bumped by
     `update_status` after every graph superstep), so a non-`pending_approval`
     row gone quiet for `GuardrailSettings.stale_run_threshold_minutes` is
     treated as abandoned and reclaimable. `pending_approval` is excluded on
     purpose: that state is supposed to sit for hours or days waiting on a
     human, so silence there is expected, not a crash.
The third race -- a concurrent double-approve -- can't use `status` as the
lock (it doesn't change value across a resume attempt until the run
settles), hence the separate `resume_in_progress` column claimed by
`claim_resume`, with its own shorter (`stale_resume_threshold_minutes`)
staleness window since a resume should settle in seconds, not minutes.

Every method opens its own `async with self._session_factory() as session:`
-- a fresh session per call, never reused across calls. That matters for the
upsert methods: SQLAlchemy's docs note that an upsert-with-RETURNING should
pass `execution_options={"populate_existing": True}` so a row already cached
in the session's identity map gets refreshed rather than silently kept
stale. A fresh session has an empty identity map every time, so that concern
doesn't currently apply here -- but it becomes a real bug the moment any
method starts reusing a session across calls, so `populate_existing=True` is
included on every upsert below as a standing invariant, not a fix for a
problem that exists yet.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, Update, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert, ReturningUpdate

from graph.schemas import IssuePayload, IssueSource, RunStatus
from graph.state import thread_id_for
from models.triage_run import TriageRun

# Claimable-terminal: every terminal status, full stop -- a row in any of
# these is safe to reclaim (see `_claimable`'s docstring below).
_TERMINAL = tuple(status.value for status in RunStatus.terminal_statuses())


def _with_cost(values: dict[str, object], estimated_cost_usd: float | None) -> dict[str, object]:
    """Adds `estimated_cost_usd` to an update's `.values()` dict only when
    a real figure is given -- omitting the key (rather than writing `None`)
    means a superstep with no `run_meta` of its own never overwrites a cost
    a previous superstep already persisted."""
    if estimated_cost_usd is not None:
        values["estimated_cost_usd"] = estimated_cost_usd
    return values


class TriageRunRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        stale_run_threshold: timedelta,
        stale_resume_threshold: timedelta,
    ) -> None:
        self._session_factory = session_factory
        self._stale_run_threshold = stale_run_threshold
        self._stale_resume_threshold = stale_resume_threshold

    def _claimable(self) -> ColumnElement[bool]:
        """A row is claimable if it's reached a real terminal outcome, or if
        it's non-pending_approval and has gone quiet for `_stale_run_threshold`
        (a crashed process, not a legitimately slow node)."""
        return or_(
            TriageRun.status.in_(_TERMINAL),
            and_(
                TriageRun.status != RunStatus.PENDING_APPROVAL.value,
                TriageRun.updated_at < datetime.now(UTC) - self._stale_run_threshold,
            ),
        )

    async def _execute_claim(
        self, stmt: ReturningInsert[tuple[TriageRun]] | ReturningUpdate[tuple[TriageRun]]
    ) -> TriageRun | None:
        """Shared session-lifecycle for every atomic claim (`claim_fresh_run`,
        `claim_retry`, `claim_resume`): a fresh session per call, execute
        with `populate_existing` (see this class's docstring for why),
        commit, return the claimed row or `None` if nothing matched."""
        async with self._session_factory() as session:
            result = await session.execute(stmt, execution_options={"populate_existing": True})
            row = result.scalar_one_or_none()
            await session.commit()
            return row

    async def _execute(self, stmt: Update) -> None:
        """Shared session-lifecycle for every plain (non-returning) update
        (`release_resume_lock`, `update_status`, `mark_failed`,
        `mark_terminal`): a fresh session per call, execute, commit."""
        async with self._session_factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def claim_fresh_run(
        self, issue: IssuePayload, *, run_id: UUID, dry_run: bool
    ) -> TriageRun | None:
        """Webhook/retry entry point for a thread that may never have run
        before: inserts a brand-new row, or reclaims an existing one only if
        it's terminal or stale (see `_claimable`). Resets `retry_count` to 0
        -- a fresh webhook delivery (e.g. a reopened issue) is a new triage
        attempt, not a retry of a prior failure."""
        thread_id = thread_id_for(issue.repo_full_name, issue.issue_number)
        now = datetime.now(UTC)
        stmt = (
            insert(TriageRun)
            .values(
                thread_id=thread_id,
                run_id=run_id,
                repo_full_name=issue.repo_full_name,
                issue_number=issue.issue_number,
                issue_title=issue.title,
                issue_url=issue.url,
                source=issue.source.value,
                status=RunStatus.RECEIVED.value,
                resume_in_progress=False,
                retry_count=0,
                error_message=None,
                dry_run=dry_run,
                estimated_cost_usd=None,
                started_at=now,
                updated_at=now,
                completed_at=None,
            )
            .on_conflict_do_update(
                index_elements=[TriageRun.thread_id],
                set_={
                    "run_id": run_id,
                    "issue_title": issue.title,
                    "issue_url": issue.url,
                    "source": issue.source.value,
                    "status": RunStatus.RECEIVED.value,
                    "resume_in_progress": False,
                    "retry_count": 0,
                    "error_message": None,
                    "dry_run": dry_run,
                    "estimated_cost_usd": None,
                    "updated_at": now,
                    "completed_at": None,
                },
                where=self._claimable(),
            )
            .returning(TriageRun)
        )
        return await self._execute_claim(stmt)

    async def claim_retry(self, thread_id: str, *, run_id: UUID, dry_run: bool) -> TriageRun | None:
        """Retry entry point: always an UPDATE, never an INSERT -- a retry
        only ever targets a thread_id that already has a row (the caller
        already validated `status == 'failed'` via `get()` before reaching
        here; this WHERE clause enforces that same invariant independently,
        as the race-proof recheck -- specifically `status == FAILED`, not
        the broader `_claimable()` check `claim_fresh_run` uses, since a
        retry is only ever valid for a run that failed, not any terminal or
        stale one).

        `estimated_cost_usd` is deliberately omitted from `.values()`
        (rather than written as `None`, the way `claim_fresh_run` does) --
        a retry should keep accumulating cost from the attempt that just
        failed, not reset it. `TriageRunService.run_fresh` reads this same
        carried-forward figure back off the freshly re-fetched record and
        seeds the retried attempt's `RunMeta` with it via
        `create_initial_state`'s `starting_cost_usd`."""
        now = datetime.now(UTC)
        stmt = (
            update(TriageRun)
            .where(TriageRun.thread_id == thread_id, TriageRun.status == RunStatus.FAILED.value)
            .values(
                run_id=run_id,
                status=RunStatus.RECEIVED.value,
                resume_in_progress=False,
                retry_count=TriageRun.retry_count + 1,
                error_message=None,
                dry_run=dry_run,
                updated_at=now,
                completed_at=None,
            )
            .returning(TriageRun)
        )
        return await self._execute_claim(stmt)

    async def claim_resume(self, thread_id: str) -> TriageRun | None:
        """Guards a concurrent double-approve: `resume_in_progress` is its
        own lock, separate from `status` (which doesn't change value across
        a resume attempt until the run settles). The staleness half handles
        a crash mid-resume the same way `_claimable` handles a crash
        mid-run, just with a shorter (10-minute) window -- a resume should
        settle in seconds, not minutes."""
        now = datetime.now(UTC)
        stmt = (
            update(TriageRun)
            .where(
                TriageRun.thread_id == thread_id,
                TriageRun.status == RunStatus.PENDING_APPROVAL.value,
                or_(
                    TriageRun.resume_in_progress.is_(False),
                    TriageRun.updated_at < now - self._stale_resume_threshold,
                ),
            )
            .values(resume_in_progress=True, updated_at=now)
            .returning(TriageRun)
        )
        return await self._execute_claim(stmt)

    async def release_resume_lock(self, thread_id: str) -> None:
        """Called unconditionally in `TriageRunService`'s `finally` block
        after a resume attempt, success or failure -- a harmless no-op if
        the lock wasn't held."""
        stmt = (
            update(TriageRun)
            .where(TriageRun.thread_id == thread_id)
            .values(resume_in_progress=False, updated_at=datetime.now(UTC))
        )
        await self._execute(stmt)

    async def update_status(
        self, thread_id: str, *, status: RunStatus, estimated_cost_usd: float | None = None
    ) -> None:
        """Called after every `astream` superstep that carries a `status`
        field in its update -- reflects exactly what `TriageState.status`
        is, never a value the checkpointed state itself doesn't have.

        `estimated_cost_usd` is `None` whenever the same superstep's update
        didn't also carry a `run_meta` -- omitted from `.values()` in that
        case (via `_with_cost`) rather than written as `NULL`, so a status
        change alone never wipes out a cost figure a previous superstep
        already persisted."""
        values = _with_cost(
            {"status": status.value, "updated_at": datetime.now(UTC)}, estimated_cost_usd
        )
        stmt = update(TriageRun).where(TriageRun.thread_id == thread_id).values(**values)
        await self._execute(stmt)

    async def mark_failed(
        self, thread_id: str, *, error_message: str, estimated_cost_usd: float | None = None
    ) -> None:
        now = datetime.now(UTC)
        values = _with_cost(
            {
                "status": RunStatus.FAILED.value,
                "error_message": error_message,
                "resume_in_progress": False,
                "updated_at": now,
                "completed_at": now,
            },
            estimated_cost_usd,
        )
        stmt = update(TriageRun).where(TriageRun.thread_id == thread_id).values(**values)
        await self._execute(stmt)

    async def mark_terminal(
        self, thread_id: str, *, status: RunStatus, estimated_cost_usd: float | None = None
    ) -> None:
        now = datetime.now(UTC)
        values = _with_cost(
            {
                "status": status.value,
                "resume_in_progress": False,
                "updated_at": now,
                "completed_at": now,
            },
            estimated_cost_usd,
        )
        stmt = update(TriageRun).where(TriageRun.thread_id == thread_id).values(**values)
        await self._execute(stmt)

    async def update_cost(self, thread_id: str, *, estimated_cost_usd: float) -> None:
        """Covers graph updates that carry `run_meta` but no `status`
        change (e.g. a Researcher tool call or Drafter iteration) -- the
        status-bearing methods above persist cost themselves when a status
        change happens in the same superstep, so this is only for the
        in-between chunks."""
        stmt = (
            update(TriageRun)
            .where(TriageRun.thread_id == thread_id)
            .values(estimated_cost_usd=estimated_cost_usd, updated_at=datetime.now(UTC))
        )
        await self._execute(stmt)

    async def get(self, thread_id: str) -> TriageRun | None:
        async with self._session_factory() as session:
            return await session.get(TriageRun, thread_id)

    def _list_filters(
        self,
        *,
        statuses: list[RunStatus] | None,
        repo_full_name: str | None,
        source: IssueSource | None,
    ) -> ColumnElement[bool]:
        """Shared WHERE-clause construction for `list_runs`/`count_runs` --
        both must filter identically or a page's `total` could disagree
        with the rows actually returned for it."""
        conditions: list[ColumnElement[bool]] = []
        if statuses is not None:
            conditions.append(TriageRun.status.in_([status.value for status in statuses]))
        if repo_full_name is not None:
            conditions.append(TriageRun.repo_full_name == repo_full_name)
        if source is not None:
            conditions.append(TriageRun.source == source.value)
        return and_(*conditions) if conditions else and_(True)

    async def count_runs(
        self,
        *,
        statuses: list[RunStatus] | None,
        repo_full_name: str | None,
        source: IssueSource | None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(TriageRun)
            .where(
                self._list_filters(statuses=statuses, repo_full_name=repo_full_name, source=source)
            )
        )
        async with self._session_factory() as session:
            return (await session.execute(stmt)).scalar_one()

    async def list_runs(
        self,
        *,
        statuses: list[RunStatus] | None,
        repo_full_name: str | None,
        source: IssueSource | None,
        offset: int,
        limit: int,
    ) -> list[TriageRun]:
        stmt = (
            select(TriageRun)
            .where(
                self._list_filters(statuses=statuses, repo_full_name=repo_full_name, source=source)
            )
            .order_by(TriageRun.updated_at.desc(), TriageRun.thread_id.desc())
            .offset(offset)
            .limit(limit)
        )
        async with self._session_factory() as session:
            return list((await session.execute(stmt)).scalars().all())

    async def count_by_status(self, *, repo_full_name: str | None = None) -> dict[str, int]:
        stmt = select(TriageRun.status, func.count()).group_by(TriageRun.status)
        if repo_full_name is not None:
            stmt = stmt.where(TriageRun.repo_full_name == repo_full_name)
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        # dict(rows) trips pyright here -- SQLAlchemy's Row[tuple[str, int]]
        # isn't recognized as assignable to dict()'s Iterable[tuple[_KT, _VT]]
        # overload, so the comprehension form is kept despite ruff's C416.
        return {status: count for status, count in rows}  # noqa: C416
