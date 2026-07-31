from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from github import GithubException
from langchain_core.runnables import RunnableConfig
from langfuse.api.core.api_error import ApiError
from langgraph.types import Command

import services.triage_run_service as service_module
from graph.nodes.node_names import NodeName
from graph.schemas import (
    ActionType,
    ApprovalDecision,
    ApprovalRequest,
    IssuePayload,
    IssueSource,
    RiskLevel,
    RunMeta,
    RunStatus,
    TimeRangePeriod,
)
from graph.schemas.approval_decision import ActionDecision
from graph.schemas.approval_request import QueuedActionSummary
from observability.tracing import create_trace_id
from services.errors import (
    DecisionMismatchError,
    IssueFetchError,
    LangfuseNotConfiguredError,
    RetryLimitExceededError,
    RunAlreadyInFlightError,
    RunNotFailedError,
    RunNotFoundError,
    TraceFetchError,
    TraceNotFoundError,
)
from services.time_range_resolver import TimeRangeResolver
from services.triage_run_record import TriageRunRecord
from services.triage_run_service import TriageRunService, validate_decision_matches
from utils.github_client import GitHubClient


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
        "status": RunStatus.FAILED,
        "resume_in_progress": False,
        "retry_count": 0,
        "error_message": "boom",
        "dry_run": True,
        "estimated_cost_usd": None,
        "started_at": now,
        "updated_at": now,
        "completed_at": now,
    }
    defaults.update(overrides)
    return TriageRunRecord(**defaults)


def make_run_meta(**overrides: Any) -> RunMeta:
    defaults: dict[str, Any] = {
        "run_id": uuid4(),
        "thread_id": "octo/repo#42",
        "started_at": datetime.now(UTC),
        "max_iterations": 10,
        "max_cost_usd": 1.0,
    }
    defaults.update(overrides)
    return RunMeta(**defaults)


def make_request(**overrides: Any) -> ApprovalRequest:
    defaults: dict[str, Any] = {
        "run_id": uuid4(),
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "issue_url": "https://github.com/octo/repo/issues/42",
        "actions": [
            QueuedActionSummary(
                index=0,
                action_type=ActionType.COMMENT,
                summary="s",
                rationale="r",
                risk_level=RiskLevel.MEDIUM,
                risk_reasoning="rr",
            )
        ],
        "requested_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ApprovalRequest(**defaults)


class _FakeRunsRepository:
    def __init__(
        self,
        *,
        claim_fresh_result: Any = "unset",
        claim_retry_result: Any = "unset",
        claim_resume_result: Any = "unset",
        get_result: Any = None,
        list_runs_result: list[Any] | None = None,
        count_runs_result: int = 0,
        status_breakdown_result: list[tuple[datetime | None, str, int, float]] | None = None,
    ) -> None:
        self._claim_fresh_result = claim_fresh_result
        self._claim_retry_result = claim_retry_result
        self._claim_resume_result = claim_resume_result
        self._get_result = get_result
        self._list_runs_result: list[Any] = list_runs_result or []
        self._count_runs_result = count_runs_result
        self._status_breakdown_result = status_breakdown_result or []
        self.claim_fresh_calls: list[dict[str, Any]] = []
        self.claim_retry_calls: list[dict[str, Any]] = []
        self.claim_resume_calls: list[str] = []
        self.release_resume_lock_calls: list[str] = []
        self.update_status_calls: list[tuple[str, RunStatus, float | None]] = []
        self.mark_failed_calls: list[tuple[str, str, float | None]] = []
        self.mark_terminal_calls: list[tuple[str, RunStatus, float | None]] = []
        self.update_cost_calls: list[tuple[str, float]] = []
        self.list_runs_calls: list[dict[str, Any]] = []
        self.count_runs_calls: list[dict[str, Any]] = []
        self.status_breakdown_calls: list[dict[str, Any]] = []

    async def claim_fresh_run(self, issue: IssuePayload, *, run_id: UUID, dry_run: bool) -> Any:
        self.claim_fresh_calls.append({"issue": issue, "run_id": run_id, "dry_run": dry_run})
        return None if self._claim_fresh_result == "unset" else self._claim_fresh_result

    async def claim_retry(self, thread_id: str, *, run_id: UUID, dry_run: bool) -> Any:
        self.claim_retry_calls.append(
            {"thread_id": thread_id, "run_id": run_id, "dry_run": dry_run}
        )
        return None if self._claim_retry_result == "unset" else self._claim_retry_result

    async def claim_resume(self, thread_id: str) -> Any:
        self.claim_resume_calls.append(thread_id)
        return None if self._claim_resume_result == "unset" else self._claim_resume_result

    async def release_resume_lock(self, thread_id: str) -> None:
        self.release_resume_lock_calls.append(thread_id)

    async def update_status(
        self, thread_id: str, *, status: RunStatus, estimated_cost_usd: float | None = None
    ) -> None:
        self.update_status_calls.append((thread_id, status, estimated_cost_usd))

    async def mark_failed(
        self, thread_id: str, *, error_message: str, estimated_cost_usd: float | None = None
    ) -> None:
        self.mark_failed_calls.append((thread_id, error_message, estimated_cost_usd))

    async def mark_terminal(
        self, thread_id: str, *, status: RunStatus, estimated_cost_usd: float | None = None
    ) -> None:
        self.mark_terminal_calls.append((thread_id, status, estimated_cost_usd))

    async def update_cost(self, thread_id: str, *, estimated_cost_usd: float) -> None:
        self.update_cost_calls.append((thread_id, estimated_cost_usd))

    async def get(self, thread_id: str) -> Any:  # noqa: ARG002
        return self._get_result

    async def list_runs(self, **kwargs: Any) -> list[Any]:
        self.list_runs_calls.append(kwargs)
        return self._list_runs_result

    async def count_runs(self, **kwargs: Any) -> int:
        self.count_runs_calls.append(kwargs)
        return self._count_runs_result

    async def get_status_breakdown(
        self,
        *,
        since: datetime | None,
        interval: str | None,
        repo_full_name: str | None,
    ) -> list[tuple[datetime | None, str, int, float]]:
        self.status_breakdown_calls.append(
            {"since": since, "interval": interval, "repo_full_name": repo_full_name}
        )
        return self._status_breakdown_result


class _FakeGitHubClient(GitHubClient):
    """Subclasses `GitHubClient` and overrides `__init__` rather than
    duck-typing a standalone class -- the convention `utils/github_client.py`
    itself documents and `tests/utils/test_github_client.py::_FakeGitHubClient`
    already follows. `self._github` is set to a harmless placeholder (never
    a real PyGithub client) so the inherited `raw` property still works
    without calling `super().__init__()`."""

    def __init__(
        self, *, issue: IssuePayload | None = None, error: Exception | None = None
    ) -> None:
        self._github = object()
        self._issue = issue
        self._error = error
        self.fetch_calls: list[tuple[str, int]] = []

    def fetch_issue(self, repo_full_name: str, issue_number: int) -> IssuePayload:
        self.fetch_calls.append((repo_full_name, issue_number))
        if self._error is not None:
            raise self._error
        assert self._issue is not None
        return self._issue


class _FakeGuardrails:
    max_retry_attempts = 3
    default_max_iterations = 10
    default_max_cost_usd = 1.0


class _FakeSettings:
    guardrails = _FakeGuardrails()
    langfuse_host = "https://cloud.langfuse.com"


class _FakeSnapshot:
    def __init__(
        self,
        next_: tuple[Any, ...],
        interrupt_value: object = None,
        values: dict[str, Any] | None = None,
    ) -> None:
        self.next = next_
        self.interrupts = [_FakeInterrupt(interrupt_value)] if interrupt_value is not None else []
        self.values = values or {}


class _FakeInterrupt:
    def __init__(self, value: object) -> None:
        self.value = value


class _FakeGraph:
    def __init__(
        self,
        *,
        snapshot: _FakeSnapshot | None = None,
        stream_chunks: list[dict[str, Any]] | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._stream_chunks = stream_chunks or []
        self._raise_error = raise_error
        self.astream_inputs: list[Any] = []

    async def aget_state(
        self,
        config: RunnableConfig,  # noqa: ARG002
    ) -> _FakeSnapshot:
        assert self._snapshot is not None
        return self._snapshot

    async def astream(
        self,
        input_: Any,
        config: RunnableConfig,  # noqa: ARG002
        stream_mode: str,  # noqa: ARG002
    ) -> Any:
        self.astream_inputs.append(input_)
        if self._raise_error is not None:
            raise self._raise_error
        for chunk in self._stream_chunks:
            yield chunk


def _graph_factory(fake_graph: _FakeGraph) -> Callable[..., _FakeGraph]:
    """A typed stand-in for `lambda **kwargs: fake_graph` -- lambdas can't
    carry a `**kwargs: object` annotation, which strict pyright otherwise
    flags as an untyped parameter."""

    def _build_graph(**_kwargs: object) -> _FakeGraph:
        return fake_graph

    return _build_graph


def make_service(
    *,
    repo: _FakeRunsRepository | None = None,
    github_client: Any = None,
    settings: Any = None,
) -> TriageRunService:
    return TriageRunService(
        settings=settings if settings is not None else _FakeSettings(),  # type: ignore[arg-type]
        checkpointer=object(),  # type: ignore[arg-type]
        researcher_tools=[],
        memory_store=object(),  # type: ignore[arg-type]
        github_client=(github_client if github_client is not None else _FakeGitHubClient()),
        runs_repo=repo if repo is not None else _FakeRunsRepository(),  # type: ignore[arg-type]
    )


# --- claim_fresh_run --------------------------------------------------------


async def test_claim_fresh_run_raises_when_repository_returns_none() -> None:
    repo = _FakeRunsRepository(claim_fresh_result=None)
    service = make_service(repo=repo)

    with pytest.raises(RunAlreadyInFlightError):
        await service.claim_fresh_run(make_issue(), run_id=uuid4(), dry_run=True)


async def test_claim_fresh_run_succeeds_and_passes_dry_run_through() -> None:
    repo = _FakeRunsRepository(claim_fresh_result=make_record())
    service = make_service(repo=repo)

    await service.claim_fresh_run(make_issue(), run_id=uuid4(), dry_run=False)

    assert len(repo.claim_fresh_calls) == 1
    assert repo.claim_fresh_calls[0]["dry_run"] is False


# --- get_run -----------------------------------------------------------------


async def test_get_run_converts_orm_row_to_record() -> None:
    row = make_record()
    repo = _FakeRunsRepository(get_result=row)
    service = make_service(repo=repo)

    result = await service.get_run("octo/repo#42")

    assert result == row


async def test_get_run_returns_none_when_no_row() -> None:
    repo = _FakeRunsRepository(get_result=None)
    service = make_service(repo=repo)

    assert await service.get_run("octo/repo#42") is None


# --- claim_resume ------------------------------------------------------------


async def test_claim_resume_raises_when_repository_returns_none() -> None:
    repo = _FakeRunsRepository(claim_resume_result=None)
    service = make_service(repo=repo)

    with pytest.raises(RunAlreadyInFlightError):
        await service.claim_resume("octo/repo#42")


async def test_claim_resume_succeeds_when_repository_returns_a_record() -> None:
    repo = _FakeRunsRepository(claim_resume_result=make_record(status=RunStatus.PENDING_APPROVAL))
    service = make_service(repo=repo)

    await service.claim_resume("octo/repo#42")

    assert repo.claim_resume_calls == ["octo/repo#42"]


# --- validate_decision_matches ------------------------------------------------


def test_validate_decision_matches_raises_on_mismatch() -> None:
    request = make_request()
    decision = ApprovalDecision(decisions=[ActionDecision(index=99, approved=True)])

    with pytest.raises(DecisionMismatchError):
        validate_decision_matches(request, decision)


def test_validate_decision_matches_passes_on_exact_match() -> None:
    request = make_request()
    decision = ApprovalDecision(decisions=[ActionDecision(index=0, approved=True)])

    validate_decision_matches(request, decision)  # must not raise


def test_validate_decision_matches_raises_on_duplicate_indices() -> None:
    request = make_request(
        actions=[
            QueuedActionSummary(
                index=0,
                action_type=ActionType.COMMENT,
                summary="s",
                rationale="r",
                risk_level=RiskLevel.MEDIUM,
                risk_reasoning="rr",
            ),
            QueuedActionSummary(
                index=1,
                action_type=ActionType.LABEL,
                summary="s2",
                rationale="r2",
                risk_level=RiskLevel.LOW,
                risk_reasoning="rr2",
            ),
        ]
    )
    decision = ApprovalDecision(
        decisions=[
            ActionDecision(index=0, approved=True),
            ActionDecision(index=0, approved=False),
        ]
    )

    with pytest.raises(DecisionMismatchError):
        validate_decision_matches(request, decision)


# --- prepare_retry -------------------------------------------------------------


async def test_prepare_retry_raises_when_no_run_found() -> None:
    repo = _FakeRunsRepository(get_result=None)
    service = make_service(repo=repo)

    with pytest.raises(RunNotFoundError):
        await service.prepare_retry("octo/repo#42", dry_run_override=None)


async def test_prepare_retry_raises_when_status_is_not_failed() -> None:
    repo = _FakeRunsRepository(get_result=make_record(status=RunStatus.PENDING_APPROVAL))
    service = make_service(repo=repo)

    with pytest.raises(RunNotFailedError) as excinfo:
        await service.prepare_retry("octo/repo#42", dry_run_override=None)
    assert excinfo.value.current_status == RunStatus.PENDING_APPROVAL


async def test_prepare_retry_raises_when_retry_limit_exceeded() -> None:
    repo = _FakeRunsRepository(get_result=make_record(retry_count=3))
    service = make_service(repo=repo)

    with pytest.raises(RetryLimitExceededError):
        await service.prepare_retry("octo/repo#42", dry_run_override=None)


async def test_prepare_retry_raises_issue_fetch_error_before_claiming() -> None:
    repo = _FakeRunsRepository(get_result=make_record(), claim_retry_result=make_record())
    github_client = _FakeGitHubClient(error=GithubException(404, {}, {}))
    service = make_service(repo=repo, github_client=github_client)

    with pytest.raises(IssueFetchError):
        await service.prepare_retry("octo/repo#42", dry_run_override=None)

    assert repo.claim_retry_calls == []  # never reached the claim step


async def test_prepare_retry_raises_when_claim_lost() -> None:
    repo = _FakeRunsRepository(get_result=make_record(), claim_retry_result=None)
    github_client = _FakeGitHubClient(issue=make_issue())
    service = make_service(repo=repo, github_client=github_client)

    with pytest.raises(RunAlreadyInFlightError):
        await service.prepare_retry("octo/repo#42", dry_run_override=None)


async def test_prepare_retry_succeeds_and_reuses_stored_dry_run_by_default() -> None:
    record = make_record(dry_run=False)
    repo = _FakeRunsRepository(get_result=record, claim_retry_result=record)
    issue = make_issue()
    github_client = _FakeGitHubClient(issue=issue)
    service = make_service(repo=repo, github_client=github_client)

    returned_issue, run_id = await service.prepare_retry("octo/repo#42", dry_run_override=None)

    assert returned_issue is issue
    assert isinstance(run_id, UUID)
    assert repo.claim_retry_calls[0]["dry_run"] is False


async def test_prepare_retry_honors_explicit_dry_run_override() -> None:
    record = make_record(dry_run=False)
    repo = _FakeRunsRepository(get_result=record, claim_retry_result=record)
    github_client = _FakeGitHubClient(issue=make_issue())
    service = make_service(repo=repo, github_client=github_client)

    await service.prepare_retry("octo/repo#42", dry_run_override=True)

    assert repo.claim_retry_calls[0]["dry_run"] is True


# --- get_pending_approval ------------------------------------------------------


async def test_get_pending_approval_returns_none_when_not_paused(monkeypatch: Any) -> None:
    fake_graph = _FakeGraph(snapshot=_FakeSnapshot(next_=()))
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    service = make_service()

    assert await service.get_pending_approval("octo/repo#42") is None


async def test_get_pending_approval_returns_request_when_paused(monkeypatch: Any) -> None:
    payload = make_request().model_dump(mode="json")
    fake_graph = _FakeGraph(
        snapshot=_FakeSnapshot(next_=(NodeName.APPROVAL_QUEUE,), interrupt_value=payload)
    )
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    service = make_service()

    request = await service.get_pending_approval("octo/repo#42")

    assert request is not None
    assert request.repo_full_name == "octo/repo"


# --- run_fresh / run_resume (the graph-driving methods) ------------------------


@asynccontextmanager
async def _fake_sandbox_toolset(
    *_args: Any, **_kwargs: Any
) -> AsyncGenerator[tuple[list[Any], None]]:
    yield [], None


async def test_run_fresh_streams_status_updates_and_releases_lock(monkeypatch: Any) -> None:
    chunks: list[dict[str, Any]] = [
        {"planner": {}},
        {"auto_post": {"status": RunStatus.PENDING_APPROVAL}},
        {"__interrupt__": ()},
    ]
    fake_graph = _FakeGraph(stream_chunks=chunks)
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    assert repo.update_status_calls == [("octo/repo#42", RunStatus.PENDING_APPROVAL, None)]
    assert repo.release_resume_lock_calls == ["octo/repo#42"]
    assert repo.mark_failed_calls == []


async def test_run_fresh_passes_a_deterministic_trace_id_to_create_initial_state(
    monkeypatch: Any,
) -> None:
    fake_graph = _FakeGraph(stream_chunks=[])
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    expected_trace_id = service_module.create_trace_id("octo/repo#42")
    state = fake_graph.astream_inputs[0]
    assert state["run_meta"].trace_id == expected_trace_id


async def test_run_fresh_seeds_starting_cost_from_the_record(monkeypatch: Any) -> None:
    """A retried run must carry forward whatever the failed attempt already
    spent -- `claim_retry` (repositories/triage_run_repository.py) no
    longer nulls `estimated_cost_usd`, so the record `run_fresh` re-fetches
    right after the claim already has the prior figure on it."""
    fake_graph = _FakeGraph(stream_chunks=[])
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record(estimated_cost_usd=0.37))
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    state = fake_graph.astream_inputs[0]
    assert state["run_meta"].estimated_cost_usd == 0.37


async def test_run_fresh_defaults_starting_cost_to_zero_when_record_has_none(
    monkeypatch: Any,
) -> None:
    """A genuinely fresh run's record has `estimated_cost_usd=None`
    (`claim_fresh_run` still nulls it) -- must seed `0.0`, not `None` or a
    crash."""
    fake_graph = _FakeGraph(stream_chunks=[])
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record(estimated_cost_usd=None))
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    state = fake_graph.astream_inputs[0]
    assert state["run_meta"].estimated_cost_usd == 0.0


async def test_run_and_track_calls_build_callback_handler_with_no_trace_id(
    monkeypatch: Any,
) -> None:
    """`root_span` is already open by the time the graph fires its first
    callback, so `build_callback_handler` must nest under that ambient span
    -- passing `trace_id` to both would produce two disconnected sibling
    root spans sharing a trace_id instead of one nested trace (see
    `observability.tracing.build_callback_handler`'s own docstring)."""
    fake_graph = _FakeGraph(stream_chunks=[])
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def _fake_build_callback_handler(*args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr(service_module, "build_callback_handler", _fake_build_callback_handler)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    assert calls == [((), {})]


async def test_run_fresh_marks_terminal_on_final_status(monkeypatch: Any) -> None:
    chunks = [{"approval_queue": {"status": RunStatus.APPROVED_AND_POSTED}}]
    fake_graph = _FakeGraph(stream_chunks=chunks)
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    assert repo.mark_terminal_calls == [("octo/repo#42", RunStatus.APPROVED_AND_POSTED, None)]
    assert repo.release_resume_lock_calls == ["octo/repo#42"]


async def test_run_fresh_marks_failed_on_unexpected_exception_mid_stream(monkeypatch: Any) -> None:
    fake_graph = _FakeGraph(raise_error=RuntimeError("boom"))
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())  # must not raise

    assert repo.mark_failed_calls == [("octo/repo#42", "RuntimeError: boom", None)]
    assert repo.release_resume_lock_calls == ["octo/repo#42"]


async def test_run_fresh_marks_failed_when_record_missing_before_streaming(
    monkeypatch: Any,
) -> None:
    """The try/except wraps setup (record lookup, sandbox entry, graph
    build), not just the astream loop -- a failure here must be exactly as
    visible as a failure mid-stream, since nobody is watching a background
    task either way."""
    fake_graph = _FakeGraph(stream_chunks=[])
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=None)
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())  # must not raise

    assert len(repo.mark_failed_calls) == 1
    assert repo.mark_failed_calls[0][0] == "octo/repo#42"
    assert repo.release_resume_lock_calls == ["octo/repo#42"]
    assert fake_graph.astream_inputs == []  # never got far enough to stream


async def test_run_resume_passes_command_resume_to_astream(monkeypatch: Any) -> None:
    chunks = [{"approval_queue": {"status": RunStatus.REJECTED}}]
    fake_graph = _FakeGraph(stream_chunks=chunks)
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)
    decision = ApprovalDecision(decisions=[ActionDecision(index=0, approved=False)])

    await service.run_resume("octo/repo#42", decision)

    assert isinstance(fake_graph.astream_inputs[0], Command)
    assert repo.mark_terminal_calls == [("octo/repo#42", RunStatus.REJECTED, None)]
    assert repo.release_resume_lock_calls == ["octo/repo#42"]


async def test_run_resume_marks_failed_when_record_missing(monkeypatch: Any) -> None:
    fake_graph = _FakeGraph(stream_chunks=[])
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=None)
    service = make_service(repo=repo)
    decision = ApprovalDecision(decisions=[ActionDecision(index=0, approved=True)])

    await service.run_resume("octo/repo#42", decision)  # must not raise

    assert len(repo.mark_failed_calls) == 1
    assert repo.release_resume_lock_calls == ["octo/repo#42"]


# --- _drive cost persistence --------------------------------------------------


async def test_run_fresh_persists_cost_without_a_status_change(monkeypatch: Any) -> None:
    """A chunk carrying `run_meta` but no `status` (e.g. a Researcher tool
    call) must still persist cost -- `update_cost` is the only repository
    call that can do that, since `update_status`/`mark_terminal`/`mark_failed`
    all require a status change to fire at all."""
    run_meta = make_run_meta().with_usage(cost_usd=0.05)
    chunks: list[dict[str, Any]] = [{"researcher": {"run_meta": run_meta}}]
    fake_graph = _FakeGraph(stream_chunks=chunks)
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    assert repo.update_cost_calls == [("octo/repo#42", 0.05)]
    assert repo.update_status_calls == []
    assert repo.mark_terminal_calls == []
    assert repo.mark_failed_calls == []


async def test_run_fresh_persists_cost_alongside_a_status_change(monkeypatch: Any) -> None:
    """A chunk carrying both `run_meta` and `status` must pass the cost
    through to the status-bearing repository call rather than also (or
    instead) calling `update_cost` -- one write per superstep, not two."""
    run_meta = make_run_meta().with_usage(cost_usd=0.12)
    chunks: list[dict[str, Any]] = [
        {"auto_post": {"status": RunStatus.PENDING_APPROVAL, "run_meta": run_meta}}
    ]
    fake_graph = _FakeGraph(stream_chunks=chunks)
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    monkeypatch.setattr(service_module, "sandbox_toolset", _fake_sandbox_toolset)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    await service.run_fresh(make_issue(), uuid4())

    assert repo.update_status_calls == [("octo/repo#42", RunStatus.PENDING_APPROVAL, 0.12)]
    assert repo.update_cost_calls == []


# --- get_run_detail ------------------------------------------------------------


async def test_get_run_detail_returns_none_when_no_run() -> None:
    repo = _FakeRunsRepository(get_result=None)
    service = make_service(repo=repo)

    assert await service.get_run_detail("octo/repo#42") is None


async def test_get_run_detail_combines_record_and_checkpoint_state(monkeypatch: Any) -> None:
    record = make_record(status=RunStatus.DRAFTING, error_message=None)
    run_meta = make_run_meta().with_usage(cost_usd=0.2)
    fake_graph = _FakeGraph(
        snapshot=_FakeSnapshot(next_=(), values={"run_meta": run_meta, "episodic_context": []})
    )
    monkeypatch.setattr(service_module, "build_graph", _graph_factory(fake_graph))
    repo = _FakeRunsRepository(get_result=record)
    service = make_service(repo=repo)

    detail = await service.get_run_detail("octo/repo#42")

    assert detail is not None
    assert detail.run.thread_id == "octo/repo#42"
    assert detail.run_meta is run_meta
    assert detail.planner_output is None
    assert detail.episodic_context == []


# --- get_trace_summary -----------------------------------------------------------


def _fake_ensure_configured(settings: Any) -> Any:
    return settings


def _fake_fetch_returns_nothing(_trace_id: str, **_kwargs: Any) -> list[Any]:
    return []


async def test_get_trace_summary_raises_when_no_run_found() -> None:
    repo = _FakeRunsRepository(get_result=None)
    service = make_service(repo=repo)

    with pytest.raises(RunNotFoundError):
        await service.get_trace_summary("octo/repo#42")


async def test_get_trace_summary_raises_when_langfuse_not_configured(monkeypatch: Any) -> None:
    def _raise_unconfigured(_settings: Any) -> Any:
        raise RuntimeError("LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are not set")

    monkeypatch.setattr(service_module, "ensure_configured", _raise_unconfigured)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    with pytest.raises(LangfuseNotConfiguredError):
        await service.get_trace_summary("octo/repo#42")


async def test_get_trace_summary_raises_when_no_observations_found(monkeypatch: Any) -> None:
    monkeypatch.setattr(service_module, "ensure_configured", _fake_ensure_configured)
    monkeypatch.setattr(service_module, "fetch_observations", _fake_fetch_returns_nothing)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    with pytest.raises(TraceNotFoundError):
        await service.get_trace_summary("octo/repo#42")


async def test_get_trace_summary_raises_on_fetch_api_error(monkeypatch: Any) -> None:
    def _raise_api_error(_trace_id: str, **_kwargs: Any) -> Any:
        raise ApiError(status_code=500, body="boom")

    monkeypatch.setattr(service_module, "ensure_configured", _fake_ensure_configured)
    monkeypatch.setattr(service_module, "fetch_observations", _raise_api_error)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    with pytest.raises(TraceFetchError):
        await service.get_trace_summary("octo/repo#42")


async def test_get_trace_summary_derives_trace_id_and_requests_light_fields(
    monkeypatch: Any,
) -> None:
    """`trace_id` is re-derived from `thread_id` via `create_trace_id`, never
    read off a checkpoint -- and the lighter `"core,basic"` field group is
    requested, not eval's full `"core,basic,io,metadata"`."""
    captured: dict[str, Any] = {}

    def _fake_fetch(trace_id: str, **kwargs: Any) -> list[Any]:
        captured["trace_id"] = trace_id
        captured["fields"] = kwargs.get("fields")
        return [
            {
                "id": "obs-1",
                "parentObservationId": None,
                "name": "triage_run",
                "type": "SPAN",
                "startTime": "2024-01-01T00:00:00Z",
                "endTime": "2024-01-01T00:00:05Z",
                "latency": 5.0,
                "totalCost": 0.01,
                "level": "DEFAULT",
            }
        ]

    monkeypatch.setattr(service_module, "ensure_configured", _fake_ensure_configured)
    monkeypatch.setattr(service_module, "fetch_observations", _fake_fetch)
    repo = _FakeRunsRepository(get_result=make_record())
    service = make_service(repo=repo)

    summary = await service.get_trace_summary("octo/repo#42")

    expected_trace_id = create_trace_id("octo/repo#42")
    assert captured["trace_id"] == expected_trace_id
    assert captured["fields"] == "core,basic"
    assert summary.trace_id == expected_trace_id
    assert summary.langfuse_url == f"https://cloud.langfuse.com/trace/{expected_trace_id}"
    assert len(summary.observations) == 1
    assert summary.observations[0].observation_id == "obs-1"
    assert summary.total_cost_usd == 0.01
    assert summary.total_latency_seconds == 5.0


# --- list_runs -----------------------------------------------------------------


async def test_list_runs_computes_offset_and_total_pages() -> None:
    repo = _FakeRunsRepository(
        list_runs_result=[make_record(), make_record()], count_runs_result=45
    )
    service = make_service(repo=repo)

    response = await service.list_runs(
        page=3, page_size=20, statuses=None, repo_full_name=None, source=None, period=None
    )

    assert repo.list_runs_calls == [
        {
            "statuses": None,
            "repo_full_name": None,
            "source": None,
            "started_after": None,
            "offset": 40,
            "limit": 20,
        }
    ]
    assert response.total == 45
    assert response.page == 3
    assert response.page_size == 20
    assert response.total_pages == 3
    assert len(response.items) == 2


async def test_list_runs_returns_zero_total_pages_when_empty() -> None:
    repo = _FakeRunsRepository(list_runs_result=[], count_runs_result=0)
    service = make_service(repo=repo)

    response = await service.list_runs(
        page=1, page_size=20, statuses=None, repo_full_name=None, source=None, period=None
    )

    assert response.total_pages == 0
    assert response.items == []


async def test_list_runs_converts_period_to_started_after_via_time_range_resolver(
    monkeypatch: Any,
) -> None:
    """`period` must be resolved through `TimeRangeResolver.since` and the
    result threaded down as `started_after` -- not passed to the repository
    as-is, and not resolved by some ad-hoc inline computation."""
    frozen_since = datetime(2026, 1, 1, tzinfo=UTC)

    def _fake_since(_self: TimeRangeResolver, _period: TimeRangePeriod | None) -> datetime:
        return frozen_since

    monkeypatch.setattr(service_module.TimeRangeResolver, "since", _fake_since)
    repo = _FakeRunsRepository(list_runs_result=[], count_runs_result=0)
    service = make_service(repo=repo)

    await service.list_runs(
        page=1,
        page_size=20,
        statuses=None,
        repo_full_name=None,
        source=None,
        period=TimeRangePeriod.ONE_HOUR,
    )

    assert repo.list_runs_calls[0]["started_after"] == frozen_since
    assert repo.count_runs_calls[0]["started_after"] == frozen_since


# --- get_status_summary ---------------------------------------------------------


async def test_get_status_summary_zero_fills_every_status_in_single_bucket() -> None:
    """`period=None` -- a single all-time bucket, zero-filled the same way
    the old flat `RunSummaryResponse.counts_by_status` used to be."""
    repo = _FakeRunsRepository(
        status_breakdown_result=[(None, "failed", 3, 1.5), (None, "pending_approval", 2, 0.0)]
    )
    service = make_service(repo=repo)

    response = await service.get_status_summary()

    assert response.period is None
    assert response.interval is None
    assert len(response.points) == 1
    point = response.points[0]
    assert point.bucket_start is None
    assert point.counts_by_status[RunStatus.FAILED] == 3
    assert point.counts_by_status[RunStatus.PENDING_APPROVAL] == 2
    assert point.counts_by_status[RunStatus.RECEIVED] == 0
    assert set(point.counts_by_status) == set(RunStatus)
    assert point.run_count == 5
    assert point.total_cost_usd == 1.5


async def test_get_status_summary_with_no_matching_runs_still_returns_one_zero_bucket() -> None:
    repo = _FakeRunsRepository(status_breakdown_result=[])
    service = make_service(repo=repo)

    response = await service.get_status_summary()

    assert len(response.points) == 1
    point = response.points[0]
    assert point.run_count == 0
    assert point.total_cost_usd == 0.0
    assert all(count == 0 for count in point.counts_by_status.values())


async def test_get_status_summary_zero_fills_every_status_across_multiple_buckets() -> None:
    bucket_one = datetime(2026, 1, 1, tzinfo=UTC)
    bucket_two = datetime(2026, 1, 2, tzinfo=UTC)
    repo = _FakeRunsRepository(
        status_breakdown_result=[
            (bucket_one, "failed", 1, 0.5),
            (bucket_two, "auto_posted", 4, 2.0),
        ]
    )
    service = make_service(repo=repo)

    response = await service.get_status_summary(period=TimeRangePeriod.SEVEN_DAYS)

    assert response.period == TimeRangePeriod.SEVEN_DAYS
    assert response.interval == "day"
    assert [point.bucket_start for point in response.points] == [bucket_one, bucket_two]
    first, second = response.points
    assert first.counts_by_status[RunStatus.FAILED] == 1
    assert first.counts_by_status[RunStatus.AUTO_POSTED] == 0
    assert first.run_count == 1
    assert first.total_cost_usd == 0.5
    assert second.counts_by_status[RunStatus.AUTO_POSTED] == 4
    assert second.counts_by_status[RunStatus.FAILED] == 0
    assert second.run_count == 4
    assert second.total_cost_usd == 2.0
    assert set(first.counts_by_status) == set(RunStatus)
    assert set(second.counts_by_status) == set(RunStatus)


async def test_get_status_summary_resolves_since_and_interval_via_time_range_resolver(
    monkeypatch: Any,
) -> None:
    frozen_since = datetime(2026, 1, 1, tzinfo=UTC)

    def _fake_since(_self: TimeRangeResolver, _period: TimeRangePeriod | None) -> datetime:
        return frozen_since

    def _fake_interval(_self: TimeRangeResolver, _period: TimeRangePeriod | None) -> str:
        return "hour"

    monkeypatch.setattr(service_module.TimeRangeResolver, "since", _fake_since)
    monkeypatch.setattr(service_module.TimeRangeResolver, "interval", _fake_interval)
    repo = _FakeRunsRepository(status_breakdown_result=[])
    service = make_service(repo=repo)

    await service.get_status_summary(
        repo_full_name="octo/repo", period=TimeRangePeriod.TWENTY_FOUR_HOURS
    )

    assert repo.status_breakdown_calls == [
        {"since": frozen_since, "interval": "hour", "repo_full_name": "octo/repo"}
    ]
