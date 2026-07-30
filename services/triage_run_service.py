"""`TriageRunService`: the single façade the API layer talks to. Composes
`TriageRunRepository` (persistence/claims) with per-run graph construction
-- `build_graph` does no I/O (see its own docstring) so it's cheap to call
fresh per run, and `tools.sandbox.sandbox_toolset` is inherently per-run
(repo-scoped: it fetches a specific repo into a sandbox), so it can't be
shared across runs the way the checkpointer/memory_store/researcher_tools
are. `main.py` is unaffected by this module -- it keeps its own SQLite
checkpointer and inline resume logic; sharing this service with the replay
pipeline is a follow-up, not done here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import structlog
from github import GithubException
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from config.settings import Settings
from graph.builder import build_graph
from graph.nodes.node_names import NodeName
from graph.schemas import ApprovalDecision, ApprovalRequest, IssuePayload, RunStatus
from graph.state import TriageState, TriageStateUpdate, create_initial_state, thread_id_for
from observability.tracing import build_callback_handler, create_trace_id, root_span
from repositories.triage_run_repository import TriageRunRepository
from services.errors import (
    DecisionMismatchError,
    IssueFetchError,
    RetryLimitExceededError,
    RunAlreadyInFlightError,
    RunNotFailedError,
    RunNotFoundError,
)
from services.triage_run_record import TriageRunRecord
from tools.sandbox import sandbox_toolset
from utils.episodic_memory_store import BaseEpisodicMemoryStore
from utils.github_client import GitHubClient

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

log = structlog.get_logger(__name__)

# Terminal statuses that need no special handling -- deliberately excludes
# FAILED, which routes through `mark_failed` instead to extract an error
# message (see `_drive`'s branching below). Derived from `RunStatus`'s own
# canonical terminal set rather than hand-copied.
_TERMINAL_STATUSES = RunStatus.terminal_statuses() - {RunStatus.FAILED}


def validate_decision_matches(request: ApprovalRequest, decision: ApprovalDecision) -> None:
    """API-layer pre-check, deliberately duplicating `ApprovalQueueNode`'s
    own server-side validation (`graph/nodes/approval_queue.py::_validate_decision`).
    Catching a mismatch here means a client mistake comes back as a
    same-request 400 with the run left untouched at `pending_approval` --
    the node's own check stays as a defense-in-depth backstop regardless,
    since the resume value crosses a trust boundary no matter which surface
    calls it."""
    decided_indices = [d.index for d in decision.decisions]
    queued_indices = [a.index for a in request.actions]
    if len(decided_indices) != len(set(decided_indices)) or set(decided_indices) != set(
        queued_indices
    ):
        raise DecisionMismatchError(decided_indices, queued_indices)


class TriageRunService:
    def __init__(
        self,
        *,
        settings: Settings,
        checkpointer: BaseCheckpointSaver[str],
        researcher_tools: list[BaseTool],
        memory_store: BaseEpisodicMemoryStore,
        github_client: GitHubClient,
        runs_repo: TriageRunRepository,
    ) -> None:
        self._settings = settings
        self._checkpointer = checkpointer
        self._researcher_tools = researcher_tools
        self._memory_store = memory_store
        self._github_client = github_client
        self._runs_repo = runs_repo

    async def claim_fresh_run(self, issue: IssuePayload, *, run_id: UUID, dry_run: bool) -> None:
        """`dry_run` has no default on purpose: a webhook-triggered run and
        a replay/test run need genuinely different values, and a silent
        default here previously meant a real webhook delivery could run in
        dry-run mode without anyone noticing. Every caller must state it."""
        thread_id = thread_id_for(issue.repo_full_name, issue.issue_number)
        record = await self._runs_repo.claim_fresh_run(issue, run_id=run_id, dry_run=dry_run)
        if record is None:
            raise RunAlreadyInFlightError(thread_id)

    async def _get_record(self, thread_id: str) -> TriageRunRecord | None:
        row = await self._runs_repo.get(thread_id)
        return TriageRunRecord.model_validate(row) if row is not None else None

    async def get_run(self, thread_id: str) -> TriageRunRecord | None:
        return await self._get_record(thread_id)

    async def get_pending_approval(self, thread_id: str) -> ApprovalRequest | None:
        """Reads the checkpointer directly -- the authoritative source for
        resume-vs-fresh, exactly as `main.py` does today (`graph.aget_state`,
        check `snapshot.next`). No sandbox tools needed for a pure read, so
        `build_graph` is called with no tools at all -- it does no I/O
        regardless."""
        graph = build_graph(checkpointer=self._checkpointer)
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        snapshot = await graph.aget_state(config)  # pyright: ignore[reportUnknownMemberType]
        if snapshot.next != (NodeName.APPROVAL_QUEUE,):
            return None
        return ApprovalRequest.model_validate(snapshot.interrupts[0].value)

    async def claim_resume(self, thread_id: str) -> None:
        record = await self._runs_repo.claim_resume(thread_id)
        if record is None:
            raise RunAlreadyInFlightError(thread_id)

    async def prepare_retry(
        self, thread_id: str, *, dry_run_override: bool | None
    ) -> tuple[IssuePayload, UUID]:
        """Validates in cheapest/least-destructive order, claims last: row
        exists -> status is failed -> retry limit not exceeded -> issue
        still fetchable on GitHub -> atomic claim. A rejection at any
        earlier step never touches `triage_runs` at all."""
        record = await self._get_record(thread_id)
        if record is None:
            raise RunNotFoundError(thread_id)
        if record.status != RunStatus.FAILED:
            raise RunNotFailedError(thread_id, record.status)
        if record.retry_count >= self._settings.guardrails.max_retry_attempts:
            raise RetryLimitExceededError(
                thread_id, record.retry_count, self._settings.guardrails.max_retry_attempts
            )

        try:
            issue = await asyncio.to_thread(
                self._github_client.fetch_issue, record.repo_full_name, record.issue_number
            )
        except GithubException as exc:
            raise IssueFetchError(thread_id, str(exc)) from exc

        run_id = uuid4()
        dry_run = dry_run_override if dry_run_override is not None else record.dry_run
        claimed = await self._runs_repo.claim_retry(thread_id, run_id=run_id, dry_run=dry_run)
        if claimed is None:
            raise RunAlreadyInFlightError(thread_id)
        return issue, run_id

    async def _drive(
        self,
        thread_id: str,
        graph: CompiledStateGraph[TriageState],
        config: RunnableConfig,
        stream_input: TriageState | Command[str],
    ) -> None:
        """Streams the graph via `stream_mode="updates"`, persisting
        `TriageState.status` into `triage_runs` after every superstep that
        actually carries one -- only `auto_post`/`approval_queue`/the
        graph-wide error handler set `status` today (Planner/Researcher/
        Drafter/RiskCheck don't), so this reflects exactly what
        `TriageState.status` is rather than inventing a finer-grained
        per-node projection the checkpointed state doesn't actually have.

        `graph.astream()`'s overloads resolve to a partially-Unknown type
        under strict pyright (the same library generics gap `main.py` and
        `tests/graph/test_builder.py` already work around with a `cast`) --
        the per-chunk dict is likewise typed loosely as
        `dict[str, TriageStateUpdate | tuple[object, ...]]` (the
        `"__interrupt__"` key's value is a tuple of `Interrupt` objects, not
        a `TriageStateUpdate`) and narrowed explicitly below rather than
        trusted at the type level.
        """
        async for chunk in graph.astream(  # pyright: ignore[reportUnknownMemberType]
            stream_input, config, stream_mode="updates"
        ):
            chunk_dict: dict[str, object] = chunk
            if "__interrupt__" in chunk_dict:
                continue
            for update in chunk_dict.values():
                if not isinstance(update, dict):
                    continue
                typed_update = cast(TriageStateUpdate, update)
                status = typed_update.get("status")
                if status is None:
                    continue
                if status == RunStatus.FAILED:
                    run_meta = typed_update.get("run_meta")
                    error_message = (
                        run_meta.errors[-1].error_message
                        if run_meta is not None and run_meta.errors
                        else "unknown error"
                    )
                    await self._runs_repo.mark_failed(thread_id, error_message=error_message)
                elif status in _TERMINAL_STATUSES:
                    await self._runs_repo.mark_terminal(thread_id, status=status)
                else:
                    await self._runs_repo.update_status(thread_id, status=status)

    async def _run_and_track(
        self,
        thread_id: str,
        build_stream_input: Callable[[TriageRunRecord, str], TriageState | Command[str]],
    ) -> None:
        """Shared entry point for both `run_fresh` and `run_resume` -- a
        retry is just a fresh run sourced from a different caller, and a
        resume is the same run continued. The try/except/finally wraps the
        *entire* body, not just the `astream` loop: a failure while fetching
        the record, entering `sandbox_toolset`, or building the graph is
        exactly as invisible to an HTTP caller as a failure mid-stream (this
        runs as a background task with nobody watching), so it needs the
        exact same `mark_failed`/`release_resume_lock` handling, not a
        narrower one that only covers the loop.

        `trace_id` is a pure deterministic hash of `thread_id` (no
        client/network involved, safe to compute unconditionally) -- a
        resume therefore re-derives the *same* trace_id the original
        `run_fresh` call produced, continuing one Langfuse trace across the
        interrupt/resume boundary with no lookup needed. `build_callback_handler`
        is called with no `trace_id` of its own on purpose: `root_span` below
        is already open by the time the graph fires its first callback, so
        the handler must nest under that ambient span -- passing `trace_id`
        to both produces two disconnected sibling root spans sharing a
        trace_id instead of one nested trace (see `build_callback_handler`'s
        own docstring and its `test_build_callback_handler_omits_trace_context_
        by_default` regression test)."""
        trace_id = create_trace_id(thread_id)
        try:
            record = await self._get_record(thread_id)
            if record is None:
                raise RunNotFoundError(thread_id)
            stream_input = build_stream_input(record, trace_id)
            callback_handler = build_callback_handler()
            config: RunnableConfig = {
                "configurable": {"thread_id": thread_id},
                "callbacks": [callback_handler] if callback_handler else [],
            }
            async with (
                root_span(
                    name="triage_run",
                    trace_id=trace_id,
                    session_id=thread_id,
                    metadata={
                        "repo_full_name": record.repo_full_name,
                        "issue_number": record.issue_number,
                    },
                ),
                sandbox_toolset(self._settings, self._github_client.raw, record.repo_full_name) as (
                    drafter_tools,
                    sandbox_handle,
                ),
            ):
                graph = build_graph(
                    checkpointer=self._checkpointer,
                    researcher_tools=self._researcher_tools,
                    drafter_tools=drafter_tools,
                    drafter_sandbox_handle=sandbox_handle,
                    memory_store=self._memory_store,
                )
                await self._drive(thread_id, graph, config, stream_input)
        except Exception as exc:
            log.error("run_service_failed", thread_id=thread_id, error=str(exc), exc_info=exc)
            # Persisted (and later served through the authenticated "not
            # pending" 404 body) copy is bounded/generic on purpose -- this
            # catch-all wraps the entire graph run, so `str(exc)` could carry
            # anything from an LLM provider error to a raw DB/network error
            # string. The full message still reaches the server-side log
            # above, unbounded, via `exc_info`.
            await self._runs_repo.mark_failed(
                thread_id, error_message=f"{type(exc).__name__}: {str(exc)[:200]}"
            )
        finally:
            await self._runs_repo.release_resume_lock(thread_id)

    async def run_fresh(self, issue: IssuePayload, run_id: UUID) -> None:
        """Background-task entry point for both the webhook and the retry
        path -- a retry is just a fresh run sourced from a different
        caller."""
        thread_id = thread_id_for(issue.repo_full_name, issue.issue_number)
        await self._run_and_track(
            thread_id,
            lambda record, trace_id: create_initial_state(
                issue,
                max_iterations=self._settings.guardrails.default_max_iterations,
                max_cost_usd=self._settings.guardrails.default_max_cost_usd,
                dry_run=record.dry_run,
                run_id=run_id,
                trace_id=trace_id,
            ),
        )

    async def run_resume(self, thread_id: str, decision: ApprovalDecision) -> None:
        await self._run_and_track(
            thread_id,
            lambda _record, _trace_id: Command(resume=decision.model_dump(mode="json")),
        )
