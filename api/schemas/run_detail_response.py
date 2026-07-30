from api.schemas.run_summary import RunSummary
from graph.schemas import (
    DraftOutput,
    EpisodicMemoryHit,
    PlannerOutput,
    PostResults,
    ResearchFindings,
    RiskAssessment,
    RunMeta,
)
from graph.schemas.base import StrictBaseModel


class RunDetailResponse(StrictBaseModel):
    """Full pipeline detail for a single run, backing `GET
    /runs/{owner}/{repo}/{issue_number}`. `run` is the same `RunSummary`
    projection the list endpoint uses; the pipeline fields below are
    `graph.schemas` domain models returned as-is (the same precedent the
    existing `/resume` route already sets for `ApprovalRequest`), and are
    `None` only in the narrow window between a webhook being accepted and
    the graph's first checkpoint superstep landing."""

    run: RunSummary
    planner_output: PlannerOutput | None
    research_findings: ResearchFindings | None
    draft: DraftOutput | None
    risk_assessment: RiskAssessment | None
    post_results: PostResults | None
    episodic_context: list[EpisodicMemoryHit]
    run_meta: RunMeta | None
