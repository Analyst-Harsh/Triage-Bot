from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RunError(BaseModel):
    node_name: str
    error_message: str
    occurred_at: datetime


class RunMeta(BaseModel):
    run_id: UUID
    thread_id: str
    trace_id: str | None = None
    started_at: datetime
    iteration_count: int = 0
    tool_calls_made: int = 0
    estimated_cost_usd: float = 0.0
    max_iterations: int
    max_cost_usd: float
    errors: list[RunError] = []
