from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.schemas import (
    DetailResponse,
    ErrorDetail,
    GitHubIssuesEvent,
    RetryRequest,
    RunAcceptedResponse,
    RunDetailResponse,
    RunListResponse,
    RunSummary,
    RunSummaryResponse,
    TraceObservation,
    TraceSummaryResponse,
    TrendPoint,
)
from graph.schemas import IssueSource, RunStatus, TimeRangePeriod
from services.triage_run_record import TriageRunRecord


def make_record(**overrides: Any) -> TriageRunRecord:
    now = datetime.now(UTC)
    defaults: dict[str, Any] = {
        "thread_id": "octo/repo#42",
        "run_id": uuid4(),
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "issue_title": "Crash on startup",
        "issue_url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK,
        "status": RunStatus.RECEIVED,
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
    return TriageRunRecord(**defaults)


def test_retry_request_defaults_dry_run_to_none() -> None:
    assert RetryRequest().dry_run is None


def test_retry_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RetryRequest.model_validate({"unexpected_field": True})


def test_run_accepted_response_round_trips() -> None:
    response = RunAcceptedResponse(
        thread_id="octo/repo#42", run_id=uuid4(), status=RunStatus.RECEIVED
    )
    dumped = response.model_dump(mode="json")
    assert dumped["thread_id"] == "octo/repo#42"
    assert dumped["run_id"] is not None
    assert dumped["status"] == "received"


def test_run_accepted_response_allows_run_id_none_for_a_resume() -> None:
    # A resume continues an existing run rather than minting a new one, so
    # `run_id` is `None` for that caller (`api/routers/runs.py::resume_run`)
    # -- unlike a fresh webhook claim or a retry, both of which pass a real
    # `run_id`.
    response = RunAcceptedResponse(
        thread_id="octo/repo#42", run_id=None, status=RunStatus.PENDING_APPROVAL
    )
    dumped = response.model_dump(mode="json")
    assert dumped["run_id"] is None
    assert dumped["status"] == "pending_approval"


def test_run_accepted_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RunAcceptedResponse.model_validate(
            {
                "thread_id": "octo/repo#42",
                "run_id": str(uuid4()),
                "status": "received",
                "extra_field": "sneaky",
            }
        )


def test_detail_response_round_trips() -> None:
    response = DetailResponse(detail="already in progress")
    restored = DetailResponse.model_validate_json(response.model_dump_json())
    assert restored == response


def test_detail_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DetailResponse.model_validate({"detail": "ok", "extra_field": "sneaky"})


def test_error_detail_round_trips_with_only_detail() -> None:
    detail = ErrorDetail(detail="no run found for octo/repo#42")
    restored = ErrorDetail.model_validate_json(detail.model_dump_json())
    assert restored == detail


def test_error_detail_round_trips_with_status_and_error_message() -> None:
    detail = ErrorDetail(
        detail="nothing pending approval for octo/repo#42",
        status=RunStatus.FAILED,
        error_message="boom",
    )
    restored = ErrorDetail.model_validate_json(detail.model_dump_json())
    assert restored == detail


def test_error_detail_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail.model_validate({"detail": "ok", "extra_field": "sneaky"})


def test_github_issues_event_ignores_unknown_fields() -> None:
    payload = {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Crash on startup",
            "body": "App crashes.",
            "user": {"login": "octocat", "id": 999, "extra": "ignored"},
            "author_association": "NONE",
            "labels": [{"name": "bug", "color": "ff0000"}],
            "created_at": datetime.now(UTC).isoformat(),
            "html_url": "https://github.com/octo/repo/issues/42",
            "some_field_github_added_later": "ignored",
        },
        "repository": {"full_name": "octo/repo", "id": 123, "private": False},
        "sender": {"login": "someone-else"},
    }

    event = GitHubIssuesEvent.model_validate(payload)

    assert event.action == "opened"
    assert event.issue.number == 42
    assert event.issue.user.login == "octocat"
    assert event.issue.labels[0].name == "bug"
    assert event.repository.full_name == "octo/repo"


def test_run_summary_from_record_computes_duration_for_completed_run() -> None:
    now = datetime.now(UTC)
    record = make_record(started_at=now - timedelta(seconds=30), completed_at=now)

    summary = RunSummary.from_record(record)

    assert summary.duration_seconds == pytest.approx(30.0)
    assert summary.thread_id == "octo/repo#42"
    assert summary.estimated_cost_usd is None


def test_run_summary_from_record_computes_duration_for_still_running_run() -> None:
    record = make_record(started_at=datetime.now(UTC) - timedelta(seconds=10), completed_at=None)

    summary = RunSummary.from_record(record)

    assert summary.duration_seconds >= 10.0


def test_run_summary_field_set_excludes_resume_in_progress() -> None:
    # `resume_in_progress` is a pure concurrency-lock implementation detail
    # on `TriageRunRecord` -- `RunSummary` is the deliberate boundary that
    # keeps it from ever reaching a client.
    assert "resume_in_progress" not in RunSummary.model_fields


def test_run_summary_round_trips() -> None:
    summary = RunSummary.from_record(make_record())
    restored = RunSummary.model_validate_json(summary.model_dump_json())
    assert restored == summary


def test_run_list_response_round_trips() -> None:
    response = RunListResponse(
        items=[RunSummary.from_record(make_record())],
        total=1,
        page=1,
        page_size=20,
        total_pages=1,
    )
    restored = RunListResponse.model_validate_json(response.model_dump_json())
    assert restored == response


def test_run_detail_response_round_trips_with_no_pipeline_data() -> None:
    response = RunDetailResponse(
        run=RunSummary.from_record(make_record()),
        planner_output=None,
        research_findings=None,
        draft=None,
        risk_assessment=None,
        post_results=None,
        episodic_context=[],
        run_meta=None,
    )
    restored = RunDetailResponse.model_validate_json(response.model_dump_json())
    assert restored == response


def test_trend_point_round_trips() -> None:
    point = TrendPoint(
        bucket_start=datetime.now(UTC),
        counts_by_status=dict.fromkeys(RunStatus, 0),
        run_count=0,
        total_cost_usd=0.0,
    )
    restored = TrendPoint.model_validate_json(point.model_dump_json())
    assert restored == point
    assert set(restored.counts_by_status) == set(RunStatus)


def test_trend_point_allows_bucket_start_none_for_the_all_time_bucket() -> None:
    point = TrendPoint(
        bucket_start=None,
        counts_by_status=dict.fromkeys(RunStatus, 0),
        run_count=0,
        total_cost_usd=0.0,
    )
    restored = TrendPoint.model_validate_json(point.model_dump_json())
    assert restored.bucket_start is None


def test_trend_point_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TrendPoint.model_validate(
            {
                "bucket_start": None,
                "counts_by_status": dict.fromkeys(RunStatus, 0),
                "run_count": 0,
                "total_cost_usd": 0.0,
                "extra_field": "sneaky",
            }
        )


def test_run_summary_response_round_trips_as_a_single_all_time_bucket() -> None:
    response = RunSummaryResponse(
        period=None,
        interval=None,
        points=[
            TrendPoint(
                bucket_start=None,
                counts_by_status=dict.fromkeys(RunStatus, 0),
                run_count=0,
                total_cost_usd=0.0,
            )
        ],
    )
    restored = RunSummaryResponse.model_validate_json(response.model_dump_json())
    assert restored == response
    assert len(restored.points) == 1
    assert set(restored.points[0].counts_by_status) == set(RunStatus)


def test_run_summary_response_round_trips_with_multiple_buckets() -> None:
    response = RunSummaryResponse(
        period=TimeRangePeriod.SEVEN_DAYS,
        interval="day",
        points=[
            TrendPoint(
                bucket_start=datetime.now(UTC),
                counts_by_status=dict.fromkeys(RunStatus, 0),
                run_count=0,
                total_cost_usd=0.0,
            ),
            TrendPoint(
                bucket_start=datetime.now(UTC),
                counts_by_status={**dict.fromkeys(RunStatus, 0), RunStatus.FAILED: 2},
                run_count=2,
                total_cost_usd=1.25,
            ),
        ],
    )
    restored = RunSummaryResponse.model_validate_json(response.model_dump_json())
    assert restored == response
    assert len(restored.points) == 2


def test_trace_observation_round_trips() -> None:
    observation = TraceObservation(
        observation_id="obs-1",
        parent_observation_id=None,
        name="triage_run",
        observation_type="SPAN",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(seconds=5),
        latency_seconds=5.0,
        cost_usd=0.01,
        level="DEFAULT",
    )
    restored = TraceObservation.model_validate_json(observation.model_dump_json())
    assert restored == observation


def test_trace_observation_allows_null_optional_fields() -> None:
    observation = TraceObservation(
        observation_id="obs-1",
        parent_observation_id=None,
        name=None,
        observation_type="CHAIN",
        start_time=datetime.now(UTC),
        end_time=None,
        latency_seconds=None,
        cost_usd=None,
        level=None,
    )
    restored = TraceObservation.model_validate_json(observation.model_dump_json())
    assert restored == observation


def test_trace_observation_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TraceObservation.model_validate(
            {
                "observation_id": "obs-1",
                "parent_observation_id": None,
                "name": None,
                "observation_type": "SPAN",
                "start_time": datetime.now(UTC),
                "end_time": None,
                "latency_seconds": None,
                "cost_usd": None,
                "level": None,
                "extra_field": "sneaky",
            }
        )


def test_trace_summary_response_round_trips() -> None:
    response = TraceSummaryResponse(
        trace_id="deadbeef",
        langfuse_url="https://cloud.langfuse.com/trace/deadbeef",
        total_latency_seconds=5.0,
        total_cost_usd=0.01,
        observations=[
            TraceObservation(
                observation_id="obs-1",
                parent_observation_id=None,
                name="triage_run",
                observation_type="SPAN",
                start_time=datetime.now(UTC),
                end_time=None,
                latency_seconds=None,
                cost_usd=None,
                level=None,
            )
        ],
    )
    restored = TraceSummaryResponse.model_validate_json(response.model_dump_json())
    assert restored == response
    assert len(restored.observations) == 1


def test_github_issues_event_defaults_body_and_labels() -> None:
    payload = {
        "action": "reopened",
        "issue": {
            "number": 7,
            "title": "No body issue",
            "user": {"login": "someone"},
            "created_at": datetime.now(UTC).isoformat(),
            "html_url": "https://github.com/octo/repo/issues/7",
        },
        "repository": {"full_name": "octo/repo"},
    }

    event = GitHubIssuesEvent.model_validate(payload)

    assert event.issue.body is None
    assert event.issue.labels == []
    assert event.issue.author_association is None
