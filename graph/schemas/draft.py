from datetime import datetime

from pydantic import BaseModel

from graph.schemas.actions import DraftAction


class DraftOutput(BaseModel):
    action: DraftAction
    rationale: str
    drafted_at: datetime
