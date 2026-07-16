from datetime import datetime

from pydantic import BaseModel, Field

from graph.schemas.enums import IssueType


class PlannerClassification(BaseModel):
    """The LLM-facing contract: exactly what the Planner asks the model to
    produce. Field descriptions flow directly into the structured-output
    tool schema the model sees, so they double as the model's instructions
    for that field."""

    issue_type: IssueType = Field(description="The single best-fit category for this issue.")
    classification_confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in this classification, from 0.0 to 1.0."
    )
    investigation_plan: list[str] = Field(
        default=[],
        description=(
            "Concrete things a researcher should check next. Empty if no "
            "further investigation is warranted."
        ),
    )
    reasoning: str = Field(description="Brief explanation for why this category was chosen.")


class PlannerOutput(BaseModel):
    """`classified_at` is a system-derived fact, not something asked of the
    LLM (models hallucinate timestamps) — the node constructs this itself
    from a `PlannerClassification` plus `datetime.now(UTC)`."""

    issue_type: IssueType
    classification_confidence: float
    investigation_plan: list[str] = []
    reasoning: str
    classified_at: datetime
