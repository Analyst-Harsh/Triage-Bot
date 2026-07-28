from pydantic import BaseModel

from graph.schemas import (
    DraftOutput,
    IssuePayload,
    PlannerOutput,
    PostResults,
    ResearchFindings,
    RiskAssessment,
    RunMeta,
    RunStatus,
)


class ReconstructedRun(BaseModel):
    """The final-state view of one run attempt, reconstructed from the
    latest top-level `LangGraph` CHAIN observation (parent = the
    `triage_run` root span) in a trace -- see
    `evals.langfuse_fetch.reconstruct`. Every field validates directly
    against the real `graph.schemas` objects: that CHAIN's own `output` is
    the complete final `TriageState` dict (confirmed empirically against a
    real trace), not a partial or hand-rolled projection. `issue` is
    included (unlike the other narrower reconstructed schemas) because the
    LLM judges need the original issue text as grading context, and it's
    already present in that same state dict at no extra fetch cost."""

    issue: IssuePayload
    planner_output: PlannerOutput | None
    research_findings: ResearchFindings | None
    draft: DraftOutput | None
    risk_assessment: RiskAssessment | None
    post_results: PostResults | None
    run_meta: RunMeta
    status: RunStatus
