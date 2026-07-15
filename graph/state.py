from datetime import UTC, datetime
from typing import Annotated, TypedDict
from uuid import uuid4

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from graph.schemas import (
    DraftOutput,
    EpisodicMemoryHit,
    IssuePayload,
    PlannerOutput,
    ResearchFindings,
    RiskAssessment,
    RunMeta,
    RunStatus,
)


class TriageState(TypedDict):
    issue: IssuePayload
    messages: Annotated[list[BaseMessage], add_messages]
    planner_output: PlannerOutput | None
    research_findings: ResearchFindings | None
    draft: DraftOutput | None
    risk_assessment: RiskAssessment | None
    episodic_context: list[EpisodicMemoryHit]
    status: RunStatus
    run_meta: RunMeta


def create_initial_state(
    issue: IssuePayload,
    *,
    max_iterations: int,
    max_cost_usd: float,
) -> TriageState:
    thread_id = f"{issue.repo_full_name}#{issue.issue_number}"
    return TriageState(
        issue=issue,
        messages=[],
        planner_output=None,
        research_findings=None,
        draft=None,
        risk_assessment=None,
        episodic_context=[],
        status=RunStatus.RECEIVED,
        run_meta=RunMeta(
            run_id=uuid4(),
            thread_id=thread_id,
            trace_id=None,
            started_at=datetime.now(UTC),
            max_iterations=max_iterations,
            max_cost_usd=max_cost_usd,
        ),
    )
