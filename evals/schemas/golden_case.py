from typing import Literal

from pydantic import BaseModel, Field

from graph.schemas import ActionType, IssueType, RiskLevel


class GoldenCase(BaseModel):
    """One hand-labeled golden case for the eval suite. Identity is just
    `repo_full_name` + `issue_number` -- `evals.langfuse_fetch.client.resolve_trace_id`
    re-derives the deterministic trace_id from these the same way
    `graph.state.create_initial_state` does, so no run_id/trace_id is ever
    stored here. `expected_*`/`forbidden_action_types` are all optional since
    one case can serve whichever eval types apply to it (e.g. a spam case
    has no `expected_researcher_tool_subset`)."""

    case_id: str
    repo_full_name: str
    issue_number: int
    issue_category: Literal["bug", "feature", "question", "spam", "prompt_injection"]
    notes: str = Field(
        description="Why this case was picked and why its expected_* fields are what they are."
    )

    expected_issue_type: IssueType | None = None
    expected_spam_short_circuit: bool = False
    expected_action_types: list[ActionType] = []
    forbidden_action_types: list[ActionType] = Field(
        default=[],
        description=(
            "Action types the run must NOT contain -- the must-not-comply "
            "assertion for prompt_injection cases."
        ),
    )
    expected_max_risk_level: RiskLevel | None = None
    expected_researcher_tool_subset: list[str] = []
    expected_code_fix: bool | None = None
