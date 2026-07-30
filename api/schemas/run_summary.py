from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from graph.schemas import IssueSource, RunStatus
from graph.schemas.base import StrictBaseModel

if TYPE_CHECKING:
    # Deferred to a type-checking-only import: `services/__init__.py` eagerly
    # imports `TriageRunService`, which in turn constructs `RunSummary`/
    # `RunListResponse`/`RunDetailResponse` directly (see that module's
    # docstring) -- a module-level import here would close a real import
    # cycle (`api.schemas.run_summary` -> `services` package init ->
    # `services.triage_run_service` -> `api.schemas.run_detail_response` ->
    # `api.schemas.run_summary`, which is still mid-import). `from __future__
    # import annotations` above means this annotation is never evaluated at
    # runtime, so the type stays precise without paying for the cycle.
    from services.triage_run_record import TriageRunRecord


class RunSummary(StrictBaseModel):
    """API-facing projection of a triage run -- deliberately decoupled from
    `TriageRunRecord` (the internal service/DB-mirroring DTO), so the public
    contract doesn't shift if an internal-only column is added, and internal
    fields (e.g. the `resume_in_progress` concurrency lock) never reach a
    client just because they exist on the ORM row."""

    thread_id: str
    run_id: UUID
    repo_full_name: str
    issue_number: int
    issue_title: str
    issue_url: str
    source: IssueSource
    status: RunStatus
    retry_count: int
    error_message: str | None
    dry_run: bool
    estimated_cost_usd: float | None
    duration_seconds: float
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_record(cls, record: TriageRunRecord) -> RunSummary:
        duration = (record.completed_at or datetime.now(UTC)) - record.started_at
        return cls(
            thread_id=record.thread_id,
            run_id=record.run_id,
            repo_full_name=record.repo_full_name,
            issue_number=record.issue_number,
            issue_title=record.issue_title,
            issue_url=record.issue_url,
            source=record.source,
            status=record.status,
            retry_count=record.retry_count,
            error_message=record.error_message,
            dry_run=record.dry_run,
            estimated_cost_usd=record.estimated_cost_usd,
            duration_seconds=duration.total_seconds(),
            started_at=record.started_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )
