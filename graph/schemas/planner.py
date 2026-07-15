from datetime import datetime

from pydantic import BaseModel

from graph.schemas.enums import IssueType


class PlannerOutput(BaseModel):
    issue_type: IssueType
    classification_confidence: float
    investigation_plan: list[str] = []
    reasoning: str
    classified_at: datetime
