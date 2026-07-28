from pydantic import BaseModel, Field


class JudgeRubricOutput(BaseModel):
    """LLM-facing contract for a rubric-scored judge call
    (`evals.judges.e2e_judge`/`researcher_judge`/`drafter_judge`). Field
    descriptions double as the model's instructions, same convention
    `graph.schemas`' LLM-facing models use (e.g. `PlannerClassification`)."""

    score: float = Field(
        ge=1.0, le=5.0, description="Overall quality score from 1 (poor) to 5 (excellent)."
    )
    rationale: str = Field(description="Brief explanation for the score.")
