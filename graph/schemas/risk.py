from datetime import datetime

from pydantic import BaseModel

from graph.schemas.enums import RiskLevel


class RiskAssessment(BaseModel):
    level: RiskLevel
    score: float
    risk_factors: list[str] = []
    reasoning: str
    requires_human_approval: bool
    assessed_at: datetime
