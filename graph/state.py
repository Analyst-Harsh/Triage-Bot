from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID, uuid4

from graph.schemas import (
    DraftOutput,
    EpisodicMemoryHit,
    IssuePayload,
    PlannerOutput,
    PostResults,
    ResearchFindings,
    RiskAssessment,
    RunMeta,
    RunStatus,
)


class TriageState(TypedDict):
    issue: IssuePayload
    planner_output: PlannerOutput | None
    research_findings: ResearchFindings | None
    draft: DraftOutput | None
    risk_assessment: RiskAssessment | None
    post_results: PostResults | None
    episodic_context: list[EpisodicMemoryHit]
    status: RunStatus
    run_meta: RunMeta


class TriageStateUpdate(TypedDict, total=False):
    """Partial-update contract returned by every `TriageNode`.

    Mirrors `TriageState` minus `issue`, which is immutable input that no
    node ever rewrites. `total=False` means a node only names the slots it
    actually writes.
    """

    planner_output: PlannerOutput | None
    research_findings: ResearchFindings | None
    draft: DraftOutput | None
    risk_assessment: RiskAssessment | None
    post_results: PostResults | None
    episodic_context: list[EpisodicMemoryHit]
    status: RunStatus
    run_meta: RunMeta


def thread_id_for(repo_full_name: str, issue_number: int) -> str:
    """Canonical `thread_id` format shared by the checkpointer, the
    `triage_runs` tracking table, and every API route that addresses a run
    by (owner, repo, issue_number) -- one source of truth for this exact
    string shape rather than the format re-typed at each call site."""
    return f"{repo_full_name}#{issue_number}"


def create_initial_state(
    issue: IssuePayload,
    *,
    max_iterations: int,
    max_cost_usd: float,
    dry_run: bool = True,
    trace_id: str | None = None,
    run_id: UUID | None = None,
    starting_cost_usd: float = 0.0,
) -> TriageState:
    """`run_id` lets a caller that already generated one (e.g.
    `services.triage_run_service.TriageRunService`, to keep
    `triage_runs.run_id` and `RunMeta.run_id` in sync) pass it in instead of
    getting a second, different random one. Omitting it (every existing
    call site) still generates a fresh `uuid4()`, unchanged from before.

    `starting_cost_usd` lets a caller seed `RunMeta.estimated_cost_usd`
    above zero -- `TriageRunService.run_fresh` passes the prior attempt's
    persisted cost here for a retry, so cost keeps accumulating across
    retries of the same thread_id rather than resetting. Every other call
    site (a genuine fresh run, `main.py`, the eval harness) omits it and
    gets today's unchanged `0.0` starting point."""
    thread_id = thread_id_for(issue.repo_full_name, issue.issue_number)
    return TriageState(
        issue=issue,
        planner_output=None,
        research_findings=None,
        draft=None,
        risk_assessment=None,
        post_results=None,
        episodic_context=[],
        status=RunStatus.RECEIVED,
        run_meta=RunMeta(
            run_id=run_id if run_id is not None else uuid4(),
            thread_id=thread_id,
            trace_id=trace_id,
            started_at=datetime.now(UTC),
            max_iterations=max_iterations,
            max_cost_usd=max_cost_usd,
            dry_run=dry_run,
            estimated_cost_usd=starting_cost_usd,
        ),
    )
