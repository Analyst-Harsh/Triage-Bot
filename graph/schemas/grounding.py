from pydantic import BaseModel, Field


class GroundingCritique(BaseModel):
    """The LLM-facing contract for the Drafter's grounding self-check: an
    independent second call (never the same call that produced the draft)
    asked to list any claim in the draft that isn't backed by the supplied
    evidence. Empty list means the check found nothing ungrounded, not that
    the check didn't run."""

    unsupported_claims: list[str] = Field(
        default=[],
        description=(
            "Every factual claim made in the draft that is not directly "
            "supported by the provided evidence. Empty if every claim is "
            "grounded."
        ),
    )
