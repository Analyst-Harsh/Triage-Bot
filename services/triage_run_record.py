"""`TriageRunService`'s own output contract -- deliberately not
`models.TriageRun` (the ORM entity) itself, so persistence and the
service/API-facing shape stay decoupled and can diverge later without
touching each other. Built from a `TriageRun` row via
`TriageRunRecord.model_validate(orm_row)` (`from_attributes=True`), never
constructed directly by callers outside `TriageRunService`.
"""

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict

from graph.schemas import IssueSource, RunStatus
from graph.schemas.base import StrictBaseModel


class TriageRunRecord(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True)

    thread_id: str
    run_id: UUID
    repo_full_name: str
    issue_number: int
    issue_title: str
    issue_url: str
    source: IssueSource
    status: RunStatus
    resume_in_progress: bool
    retry_count: int
    error_message: str | None
    dry_run: bool
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
