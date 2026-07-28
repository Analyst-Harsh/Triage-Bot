from pydantic import Field

from graph.schemas.base import StrictBaseModel


class ActionDecision(StrictBaseModel):
    """One human verdict on one queued action. `extra="forbid"` (inherited
    from `StrictBaseModel`) matters especially here: the resume value
    crosses a trust boundary (it's supplied by whatever external surface
    resumes the graph, not produced internally), so an unexpected field must
    be rejected rather than silently dropped."""

    index: int = Field(ge=0, description="Must match a `QueuedActionSummary.index` exactly.")
    approved: bool
    note: str | None = Field(
        default=None,
        description="Optional reviewer note; recorded as `ActionPostResult.detail` on rejection.",
    )


class ApprovalDecision(StrictBaseModel):
    """The `Command(resume=...)` payload `ApprovalQueueNode` expects: one
    `ActionDecision` per queued action, no more, no fewer -- validated by
    the node itself, not by this model (index-set membership needs the
    queued indices, which aren't in scope here)."""

    decisions: list[ActionDecision] = Field(min_length=1)
