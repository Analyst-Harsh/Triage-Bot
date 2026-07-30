"""ORM mapping for the `triage_runs` table -- a persistence-only concern.
This class never crosses into the service/API layers directly;
`services.triage_run_record.TriageRunRecord` is the Pydantic-validated
contract those layers actually pass around, built from this class via
`model_validate(orm_row, from_attributes=True)` at the repository boundary.

One row per `thread_id` (one row per issue) -- a live-status projection and
concurrency-claim table, not a run history log; historical detail lives in
Langfuse via `RunMeta.trace_id`. `resume_in_progress`/`retry_count` and the
staleness window baked into the claim queries
(`repositories.triage_run_repository`) are the sole concurrency guard for
the API -- see that module's docstring for the full rationale.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class TriageRun(Base):
    __tablename__ = "triage_runs"
    __table_args__ = (
        Index("triage_runs_status_idx", "status", "updated_at"),
        Index("triage_runs_repo_idx", "repo_full_name"),
    )

    thread_id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[UUID]
    repo_full_name: Mapped[str]
    issue_number: Mapped[int]
    issue_title: Mapped[str]
    issue_url: Mapped[str]
    source: Mapped[str]
    status: Mapped[str]
    resume_in_progress: Mapped[bool] = mapped_column(default=False)
    retry_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None]
    dry_run: Mapped[bool] = mapped_column(default=True)
    estimated_cost_usd: Mapped[float | None]
    started_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
