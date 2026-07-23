from datetime import datetime

from pydantic import BaseModel, Field

from graph.schemas.enums import RiskLevel


class ActionRiskAssessment(BaseModel):
    """Persisted risk verdict for one drafted action. Positional, not
    indexed: item i here always assesses `draft.actions[i]`, mirroring every
    other per-item list in this schema layer (e.g. `DraftOutput.actions`
    itself)."""

    level: RiskLevel
    risk_factors: list[str] = []
    reasoning: str


class RiskAssessment(BaseModel):
    """Persisted container -- the type of `TriageState.risk_assessment`.
    `action_assessments` must be the same length as `draft.actions`, in the
    same order."""

    action_assessments: list[ActionRiskAssessment] = Field(min_length=1)
    assessed_at: datetime


class ActionRiskJudgment(BaseModel):
    """LLM-facing: one judgment for one ambiguous (`comment`/`close`)
    action. Unlike `ActionRiskAssessment`, this carries an explicit index --
    the model is only shown the ambiguous subset of `draft.actions` (labels
    and code fixes are resolved by hardcoded policy, never sent to the
    model), so its output can't be positional the way the persisted,
    complete list is."""

    action_index: int = Field(description="Position in the drafted actions list this judges.")
    level: RiskLevel
    risk_factors: list[str] = Field(
        default=[],
        description=(
            "Specific concerns driving this level, e.g. 'unsupported claim', "
            "'assertive tone', 'irreversible close'. Empty only if level is low."
        ),
    )
    reasoning: str


class RiskJudgmentBatch(BaseModel):
    """LLM-facing container for the batched risk-judgment call: one
    judgment per ambiguous action shown this call."""

    judgments: list[ActionRiskJudgment] = Field(min_length=1)
