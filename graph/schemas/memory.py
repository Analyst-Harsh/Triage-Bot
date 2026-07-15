from datetime import datetime

from pydantic import BaseModel

from graph.schemas.enums import ActionType


class EpisodicMemoryHit(BaseModel):
    past_issue_number: int
    past_repo: str
    summary: str
    action_taken: ActionType | None = None
    outcome: str
    similarity_score: float
    retrieved_at: datetime
