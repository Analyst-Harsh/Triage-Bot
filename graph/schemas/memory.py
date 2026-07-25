from datetime import datetime

from pydantic import BaseModel, Field

from graph.schemas.enums import ActionType, PostOutcome, RunStatus


class EpisodicActionOutcome(BaseModel):
    """One past action plus what actually happened to it -- e.g. `comment`
    that was `posted`, or `code_fix` that was `rejected`. Positional
    correlation (action type <-> per-action outcome) is inherent here since
    each pair is built together, unlike `draft.actions`/`post_results.action_results`
    elsewhere in this codebase, which stay correlated by list index."""

    action_type: ActionType
    outcome: PostOutcome


class EpisodicMemoryHit(BaseModel):
    past_issue_number: int
    past_repo: str
    summary: str
    actions_taken: list[EpisodicActionOutcome]
    outcome: RunStatus
    similarity_score: float = Field(ge=0.0, le=1.0)
    retrieved_at: datetime
