from datetime import datetime

from pydantic import BaseModel, Field

from graph.schemas.enums import PostOutcome


class ActionPostResult(BaseModel):
    """Persisted post-attempt outcome for one drafted action. Positional,
    not indexed: item i here always corresponds to `draft.actions[i]`,
    mirroring `ActionRiskAssessment`."""

    outcome: PostOutcome
    detail: str | None = Field(
        default=None,
        description=(
            "GitHub comment URL when a comment was actually POSTED; the "
            "created PR's URL when a POSTED code_fix became a pull request; "
            "the error message when FAILED; the reviewer's note (or None) "
            "when REJECTED; unused (None) for QUEUED or for a successful "
            "label/close (nothing distinct to point at)."
        ),
    )


class PostResults(BaseModel):
    """Persisted container -- the type of `TriageState.post_results`.
    `action_results` must be the same length as `draft.actions`, in the
    same order."""

    action_results: list[ActionPostResult] = Field(min_length=1)
    evaluated_at: datetime
