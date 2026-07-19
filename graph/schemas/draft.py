from datetime import datetime

from pydantic import BaseModel, Field

from graph.schemas.actions import DraftAction, NonCodeDraftAction


class ProposedAction(BaseModel):
    """One proposed action + why, as asked of the LLM. Restricted to
    `NonCodeDraftAction` — the sandbox to verify a `CodeFixAction` doesn't
    exist yet, so the model cannot type its way into proposing one."""

    action: NonCodeDraftAction
    rationale: str = Field(description="Why this specific action is being proposed.")


class DraftProposal(BaseModel):
    """The LLM-facing contract: what the Drafter asks the model to produce.
    This is `DrafterSubgraph.summary_schema`. Field `description=`s double as
    the model's instructions, same as `PlannerClassification`/`ResearchSummary`."""

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
    `NonCodeDraftAction`, so this shape doesn't need to change when the
    sandbox code-fix path lands — it'll just start populating the `code_fix`
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
