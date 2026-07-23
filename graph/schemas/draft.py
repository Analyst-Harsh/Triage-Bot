from datetime import datetime

from pydantic import BaseModel, Field

from graph.schemas.actions import DraftAction, DraftIntent

# `ProposedAction`/`DraftProposal` are the LLM-facing contract sent via
# with_structured_output(..., method="function_calling") -- their docstrings
# and Field(description=...)s are surfaced to the model as the tool's schema
# description, so they're kept model-facing only; implementation notes live
# in comments instead.
#
# `ProposedAction.action` is typed `DraftIntent`, not `DraftAction`: a
# `CodeFixAction` carries a real `SandboxResult`, which only the sandbox
# itself can produce, so the model cannot type its way into fabricating one
# -- it can only signal intent via `CodeFixIntent`.


class ProposedAction(BaseModel):
    """One proposed action, plus why. For a code fix, propose CodeFixIntent
    -- you cannot supply a diff, target_files, or sandbox_result directly."""

    action: DraftIntent
    rationale: str = Field(
        description=(
            "Why this specific action is being proposed. Required for every "
            "action, including ones proposed near the end of a long "
            "tool-calling run."
        )
    )


class DraftProposal(BaseModel):
    """Propose one or more actions for this issue, each with its own
    rationale, plus one overall rationale tying them together."""

    actions: list[ProposedAction] = Field(
        min_length=1,
        description="One or more actions to take, e.g. a label plus a comment.",
    )
    overall_rationale: str = Field(
        description="The overall judgment call tying the proposed actions together."
    )


class DraftedAction(BaseModel):
    """A persisted proposed action plus its rationale. `action` is typed as
    the full `DraftAction` union (including `CodeFixAction`) rather than
    `DraftIntent`, so this shape doesn't need to change when the sandbox
    code-fix path lands — it'll just start populating the `code_fix`
    variant that was always a valid member of this type."""

    action: DraftAction
    rationale: str


class DraftOutput(BaseModel):
    """`unsupported_claims` comes from a second, independent LLM call (the
    grounding self-check, `DrafterSubgraph.grounding_check_node`) — never the
    same call that produced the draft, since a model grading its own
    unverified claims in the same breath it wrote them is a much weaker check
    than a second, independent pass over the finished draft plus the
    evidence."""

    actions: list[DraftedAction] = Field(min_length=1)
    overall_rationale: str
    unsupported_claims: list[str] = []
    drafted_at: datetime
