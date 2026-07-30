from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import Table

from models.triage_run import TriageRun


def test_triage_run_constructs_with_every_column() -> None:
    now = datetime.now(UTC)
    run_id = uuid4()

    run = TriageRun(
        thread_id="octo/repo#42",
        run_id=run_id,
        repo_full_name="octo/repo",
        issue_number=42,
        issue_title="Crash on startup",
        issue_url="https://github.com/octo/repo/issues/42",
        source="webhook",
        status="received",
        resume_in_progress=False,
        retry_count=0,
        error_message=None,
        dry_run=True,
        estimated_cost_usd=None,
        started_at=now,
        updated_at=now,
        completed_at=None,
    )

    assert run.thread_id == "octo/repo#42"
    assert run.run_id == run_id
    assert run.status == "received"
    assert run.retry_count == 0
    assert run.estimated_cost_usd is None
    assert run.completed_at is None


def test_triage_run_table_name_and_indexes() -> None:
    assert TriageRun.__tablename__ == "triage_runs"
    table = cast(Table, TriageRun.__table__)
    index_names = {index.name for index in table.indexes}
    assert index_names == {"triage_runs_status_idx", "triage_runs_repo_idx"}
