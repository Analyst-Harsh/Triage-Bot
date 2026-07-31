from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from graph.schemas import IssuePayload, IssueSource, RunStatus
from models.triage_run import TriageRun
from repositories import triage_run_repository as triage_run_repository_module
from repositories.triage_run_repository import TriageRunRepository


def make_issue(**overrides: Any) -> IssuePayload:
    defaults: dict[str, Any] = {
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "title": "Crash on startup",
        "body": "App crashes with a NoneType error.",
        "author": "octocat",
        "created_at": datetime.now(UTC),
        "url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK,
    }
    defaults.update(overrides)
    return IssuePayload(**defaults)


def make_run(**overrides: Any) -> TriageRun:
    now = datetime.now(UTC)
    defaults: dict[str, Any] = {
        "thread_id": "octo/repo#42",
        "run_id": uuid4(),
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "issue_title": "Crash on startup",
        "issue_url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK.value,
        "status": RunStatus.RECEIVED.value,
        "resume_in_progress": False,
        "retry_count": 0,
        "error_message": None,
        "dry_run": True,
        "estimated_cost_usd": None,
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    defaults.update(overrides)
    return TriageRun(**defaults)


def compiled(stmt: Any) -> str:
    """Renders a SQLAlchemy Core statement with literal values inlined, so
    tests can assert on the actual SQL shape (ON CONFLICT clause, WHERE
    conditions) without needing a live database to execute against --
    matching this repo's existing convention of unit-testing calling code
    against fakes rather than requiring Postgres in CI."""
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class _FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _FakeResult:
    def __init__(
        self,
        row: TriageRun | None = None,
        *,
        scalar: int | None = None,
        scalars_rows: list[Any] | None = None,
        all_rows: list[Any] | None = None,
    ) -> None:
        self._row = row
        self._scalar = scalar
        self._scalars_rows = scalars_rows or []
        self._all_rows = all_rows or []

    def scalar_one_or_none(self) -> TriageRun | None:
        return self._row

    def scalar_one(self) -> int:
        assert self._scalar is not None
        return self._scalar

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._scalars_rows)

    def all(self) -> list[Any]:
        return self._all_rows


class _FakeAsyncSession:
    """Duck-typed stand-in for `sqlalchemy.ext.asyncio.AsyncSession`:
    `TriageRunRepository` only ever calls `execute`/`commit`/`get` on it,
    used as an `async with` block."""

    def __init__(
        self,
        row: TriageRun | None = None,
        *,
        get_result: TriageRun | None = None,
        scalar_result: int | None = None,
        scalars_rows: list[Any] | None = None,
        all_rows: list[Any] | None = None,
    ) -> None:
        self._row = row
        self._get_result = get_result
        self._scalar_result = scalar_result
        self._scalars_rows = scalars_rows
        self._all_rows = all_rows
        self.executed: list[tuple[Any, dict[str, Any] | None]] = []
        self.committed = False
        self.get_calls: list[tuple[Any, Any]] = []

    async def execute(self, stmt: Any, execution_options: dict[str, Any] | None = None) -> Any:
        self.executed.append((stmt, execution_options))
        return _FakeResult(
            self._row,
            scalar=self._scalar_result,
            scalars_rows=self._scalars_rows,
            all_rows=self._all_rows,
        )

    async def commit(self) -> None:
        self.committed = True

    async def get(self, model: Any, primary_key: Any) -> TriageRun | None:
        self.get_calls.append((model, primary_key))
        return self._get_result

    async def __aenter__(self) -> _FakeAsyncSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


def make_repo(
    session: _FakeAsyncSession,
    *,
    stale_run_threshold: timedelta = timedelta(minutes=15),
    stale_resume_threshold: timedelta = timedelta(minutes=10),
) -> TriageRunRepository:
    return TriageRunRepository(
        lambda: session,  # type: ignore[arg-type]
        stale_run_threshold=stale_run_threshold,
        stale_resume_threshold=stale_resume_threshold,
    )


async def test_claim_fresh_run_returns_record_on_success() -> None:
    row = make_run()
    session = _FakeAsyncSession(row=row)
    repo = make_repo(session)

    result = await repo.claim_fresh_run(make_issue(), run_id=uuid4(), dry_run=True)

    assert result is row
    assert session.committed
    stmt, execution_options = session.executed[0]
    assert execution_options == {"populate_existing": True}
    sql = compiled(stmt)
    assert "ON CONFLICT" in sql
    assert "octo/repo#42" in sql


async def test_claim_fresh_run_returns_none_when_row_already_in_flight() -> None:
    session = _FakeAsyncSession(row=None)
    repo = make_repo(session)

    result = await repo.claim_fresh_run(make_issue(), run_id=uuid4(), dry_run=True)

    assert result is None


async def test_claim_retry_returns_record_and_increments_retry_count() -> None:
    row = make_run(retry_count=2)
    session = _FakeAsyncSession(row=row)
    repo = make_repo(session)

    result = await repo.claim_retry("octo/repo#42", run_id=uuid4(), dry_run=False)

    assert result is row
    stmt, _ = session.executed[0]
    sql = compiled(stmt)
    assert "triage_runs.retry_count" in sql
    assert "octo/repo#42" in sql


async def test_claim_retry_where_clause_checks_failed_status_specifically() -> None:
    """`claim_retry` must enforce its own `status == 'failed'` invariant at
    the DB layer, independent of the caller's pre-check -- not the broader
    `_claimable()` check (`claim_fresh_run`'s job), which would also match
    any other terminal/stale row."""
    row = make_run(retry_count=2)
    session = _FakeAsyncSession(row=row)
    repo = make_repo(session)

    await repo.claim_retry("octo/repo#42", run_id=uuid4(), dry_run=False)

    stmt, _ = session.executed[0]
    sql = compiled(stmt)
    assert "failed" in sql


async def test_claim_retry_returns_none_when_not_claimable() -> None:
    session = _FakeAsyncSession(row=None)
    repo = make_repo(session)

    result = await repo.claim_retry("octo/repo#42", run_id=uuid4(), dry_run=False)

    assert result is None


async def test_claim_resume_returns_record_and_sets_lock() -> None:
    row = make_run(status=RunStatus.PENDING_APPROVAL.value)
    session = _FakeAsyncSession(row=row)
    repo = make_repo(session)

    result = await repo.claim_resume("octo/repo#42")

    assert result is row
    stmt, _ = session.executed[0]
    sql = compiled(stmt)
    assert "resume_in_progress" in sql
    assert "pending_approval" in sql


async def test_claim_resume_returns_none_when_already_locked() -> None:
    session = _FakeAsyncSession(row=None)
    repo = make_repo(session)

    result = await repo.claim_resume("octo/repo#42")

    assert result is None


async def test_release_resume_lock_commits() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.release_resume_lock("octo/repo#42")

    assert session.committed
    stmt, _ = session.executed[0]
    assert "resume_in_progress" in compiled(stmt)


async def test_update_status_commits_with_new_status() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.update_status("octo/repo#42", status=RunStatus.RESEARCHING)

    assert session.committed
    stmt, _ = session.executed[0]
    assert "researching" in compiled(stmt)


async def test_mark_failed_sets_status_error_and_releases_lock() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.mark_failed("octo/repo#42", error_message="boom")

    assert session.committed
    sql = compiled(session.executed[0][0])
    assert "failed" in sql
    assert "boom" in sql
    assert "resume_in_progress" in sql


async def test_mark_terminal_sets_status_and_releases_lock() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.mark_terminal("octo/repo#42", status=RunStatus.APPROVED_AND_POSTED)

    assert session.committed
    sql = compiled(session.executed[0][0])
    assert "approved_and_posted" in sql
    assert "resume_in_progress" in sql


async def test_update_status_sets_cost_when_given() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.update_status("octo/repo#42", status=RunStatus.RESEARCHING, estimated_cost_usd=0.05)

    sql = compiled(session.executed[0][0])
    assert "estimated_cost_usd" in sql
    assert "0.05" in sql


async def test_update_status_omits_cost_column_when_not_given() -> None:
    """A status change with no accompanying `run_meta` must never write
    `estimated_cost_usd` at all -- writing it as `NULL` would wipe out a
    figure a previous superstep already persisted."""
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.update_status("octo/repo#42", status=RunStatus.RESEARCHING)

    sql = compiled(session.executed[0][0])
    assert "estimated_cost_usd" not in sql


async def test_mark_failed_sets_cost_when_given() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.mark_failed("octo/repo#42", error_message="boom", estimated_cost_usd=0.3)

    sql = compiled(session.executed[0][0])
    assert "estimated_cost_usd" in sql
    assert "0.3" in sql


async def test_mark_terminal_sets_cost_when_given() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.mark_terminal(
        "octo/repo#42", status=RunStatus.APPROVED_AND_POSTED, estimated_cost_usd=0.42
    )

    sql = compiled(session.executed[0][0])
    assert "estimated_cost_usd" in sql
    assert "0.42" in sql


async def test_update_cost_writes_only_the_cost_column() -> None:
    session = _FakeAsyncSession()
    repo = make_repo(session)

    await repo.update_cost("octo/repo#42", estimated_cost_usd=0.07)

    assert session.committed
    sql = compiled(session.executed[0][0])
    assert "estimated_cost_usd" in sql
    assert "0.07" in sql


async def test_get_returns_none_when_no_row() -> None:
    session = _FakeAsyncSession(get_result=None)
    repo = make_repo(session)

    assert await repo.get("octo/repo#42") is None
    assert session.get_calls == [(TriageRun, "octo/repo#42")]


async def test_get_returns_record_when_row_exists() -> None:
    row = make_run()
    session = _FakeAsyncSession(get_result=row)
    repo = make_repo(session)

    result = await repo.get("octo/repo#42")

    assert result is row


async def test_claim_fresh_run_honors_configured_stale_run_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_claimable()` resolves `datetime.now(UTC) - stale_run_threshold` into
    an absolute timestamp before the statement is compiled, so this freezes
    `now` and asserts the exact literal that a distinctive threshold produces
    -- a plain substring check on "15"/"7" wouldn't observe anything, since
    the threshold itself never appears in the compiled SQL."""
    frozen_now = datetime(2026, 1, 1, tzinfo=UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # noqa: ARG003 -- must match datetime.now's signature
            return frozen_now

    monkeypatch.setattr(triage_run_repository_module, "datetime", _FrozenDatetime)
    session = _FakeAsyncSession(row=None)
    repo = make_repo(session, stale_run_threshold=timedelta(minutes=7))

    await repo.claim_fresh_run(make_issue(), run_id=uuid4(), dry_run=True)

    sql = compiled(session.executed[0][0])
    assert str(frozen_now - timedelta(minutes=7)) in sql


async def test_claim_fresh_run_resets_estimated_cost_to_null() -> None:
    """A fresh claim is a new triage attempt (webhook redelivery, or
    reclaiming a terminal/stale row) -- any cost from a previous attempt on
    this thread_id must not leak into the new one."""
    row = make_run()
    session = _FakeAsyncSession(row=row)
    repo = make_repo(session)

    await repo.claim_fresh_run(make_issue(), run_id=uuid4(), dry_run=True)

    sql = compiled(session.executed[0][0])
    assert "estimated_cost_usd" in sql


async def test_claim_retry_preserves_estimated_cost() -> None:
    """A retry must keep accumulating cost from the failed attempt, not
    reset it -- `estimated_cost_usd` is deliberately omitted from the
    UPDATE's `.values()` (the same 'omit rather than null' pattern
    `_with_cost` uses elsewhere in this module) so the column keeps
    whatever the failed attempt last persisted.

    Asserts on `"estimated_cost_usd="` (the SET-clause assignment form),
    not bare `"estimated_cost_usd"` -- `claim_retry`'s `.returning(TriageRun)`
    always lists every column, including `triage_runs.estimated_cost_usd`
    with no `=`, so the bare substring is present either way and wouldn't
    actually prove the column is excluded from `.values()`."""
    row = make_run(retry_count=2)
    session = _FakeAsyncSession(row=row)
    repo = make_repo(session)

    await repo.claim_retry("octo/repo#42", run_id=uuid4(), dry_run=False)

    sql = compiled(session.executed[0][0])
    assert "estimated_cost_usd=" not in sql


# --- list_runs / count_runs / count_by_status --------------------------------


async def test_list_runs_applies_status_repo_and_source_filters() -> None:
    session = _FakeAsyncSession(scalars_rows=[make_run()])
    repo = make_repo(session)

    await repo.list_runs(
        statuses=[RunStatus.FAILED, RunStatus.PENDING_APPROVAL],
        repo_full_name="octo/repo",
        source=IssueSource.WEBHOOK,
        started_after=None,
        offset=0,
        limit=20,
    )

    sql = compiled(session.executed[0][0])
    assert "failed" in sql
    assert "pending_approval" in sql
    assert "octo/repo" in sql
    assert "webhook" in sql
    assert "LIMIT 20" in sql


async def test_list_runs_with_no_filters_returns_all_rows() -> None:
    rows = [make_run(), make_run(thread_id="octo/repo#43")]
    session = _FakeAsyncSession(scalars_rows=rows)
    repo = make_repo(session)

    result = await repo.list_runs(
        statuses=None,
        repo_full_name=None,
        source=None,
        started_after=None,
        offset=0,
        limit=20,
    )

    assert result == rows


async def test_list_runs_applies_offset_for_pagination() -> None:
    session = _FakeAsyncSession(scalars_rows=[])
    repo = make_repo(session)

    await repo.list_runs(
        statuses=None,
        repo_full_name=None,
        source=None,
        started_after=None,
        offset=40,
        limit=20,
    )

    sql = compiled(session.executed[0][0])
    assert "OFFSET 40" in sql


async def test_list_runs_applies_started_after_filter_when_given() -> None:
    started_after = datetime(2026, 1, 1, tzinfo=UTC)
    session = _FakeAsyncSession(scalars_rows=[])
    repo = make_repo(session)

    await repo.list_runs(
        statuses=None,
        repo_full_name=None,
        source=None,
        started_after=started_after,
        offset=0,
        limit=20,
    )

    sql = compiled(session.executed[0][0])
    assert "triage_runs.started_at >=" in sql
    assert str(started_after) in sql


async def test_list_runs_omits_started_at_condition_when_started_after_is_none() -> None:
    session = _FakeAsyncSession(scalars_rows=[])
    repo = make_repo(session)

    await repo.list_runs(
        statuses=None,
        repo_full_name=None,
        source=None,
        started_after=None,
        offset=0,
        limit=20,
    )

    sql = compiled(session.executed[0][0])
    assert "started_at >=" not in sql


async def test_count_runs_applies_same_filters_as_list_runs() -> None:
    session = _FakeAsyncSession(scalar_result=7)
    repo = make_repo(session)

    result = await repo.count_runs(
        statuses=[RunStatus.FAILED],
        repo_full_name="octo/repo",
        source=None,
        started_after=None,
    )

    assert result == 7
    sql = compiled(session.executed[0][0])
    assert "failed" in sql
    assert "octo/repo" in sql


async def test_count_runs_applies_started_after_filter_when_given() -> None:
    started_after = datetime(2026, 1, 1, tzinfo=UTC)
    session = _FakeAsyncSession(scalar_result=3)
    repo = make_repo(session)

    result = await repo.count_runs(
        statuses=None,
        repo_full_name=None,
        source=None,
        started_after=started_after,
    )

    assert result == 3
    sql = compiled(session.executed[0][0])
    assert "triage_runs.started_at >=" in sql
    assert str(started_after) in sql


async def test_count_by_status_groups_by_status() -> None:
    session = _FakeAsyncSession(all_rows=[("failed", 3), ("pending_approval", 2)])
    repo = make_repo(session)

    result = await repo.count_by_status()

    assert result == {"failed": 3, "pending_approval": 2}


async def test_count_by_status_filters_by_repo_when_given() -> None:
    session = _FakeAsyncSession(all_rows=[])
    repo = make_repo(session)

    await repo.count_by_status(repo_full_name="octo/repo")

    sql = compiled(session.executed[0][0])
    assert "octo/repo" in sql
