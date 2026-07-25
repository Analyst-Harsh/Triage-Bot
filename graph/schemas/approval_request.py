from datetime import datetime
from typing import Final
from uuid import UUID

from pydantic import BaseModel, Field

from graph.schemas.enums import ActionType, RiskLevel

DIFF_PREVIEW_MAX_BYTES: Final[int] = 20_000


class QueuedActionSummary(BaseModel):
    """One queued (non-LOW-risk) drafted action, rendered for human review.
    `index` is `draft.actions[index]`'s position -- the slot an
    `ActionDecision` in the resume payload targets. Fields below
    `risk_factors` are populated only for `action_type == "code_fix"`; all
    others carry `None`/`[]`."""

    index: int
    action_type: ActionType
    summary: str = Field(description="One-line, human-readable description of the action.")
    rationale: str
    risk_level: RiskLevel
    risk_reasoning: str
    risk_factors: list[str] = []
    target_files: list[str] = []
    sandbox_passed: bool | None = None
    sandbox_test_command: str | None = None
    diff_preview: str | None = Field(
        default=None,
        description=(
            f"The unified diff, capped at {DIFF_PREVIEW_MAX_BYTES} UTF-8 bytes. "
            "The full diff is retained in run state regardless of truncation."
        ),
    )
    diff_truncated: bool = False


class ApprovalRequest(BaseModel):
    """The `interrupt()` payload `ApprovalQueueNode` surfaces -- one entry
    per queued action, requiring a matching `ActionDecision` on resume.
    Built by `ApprovalRequestBuilder`
    (`graph/nodes/utils/approval_request_builder.py`), not constructed
    directly by callers."""

    run_id: UUID
    repo_full_name: str
    issue_number: int
    issue_url: str
    actions: list[QueuedActionSummary] = Field(min_length=1)
    requested_at: datetime
