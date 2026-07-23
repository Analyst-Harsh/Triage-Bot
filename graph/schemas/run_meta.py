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

    def with_usage(
        self, *, cost_usd: float = 0.0, tool_calls: int = 0, iterations: int = 0
    ) -> RunMeta:
        """Returns a copy with `estimated_cost_usd`/`tool_calls_made`/
        `iteration_count` each incremented by the given amount (default 0,
        i.e. unchanged) -- the one place every node accumulates run-level
        usage onto `RunMeta`, so the accumulation arithmetic isn't
        hand-duplicated at each call site."""
        return self.model_copy(
            update={
                "estimated_cost_usd": self.estimated_cost_usd + cost_usd,
                "tool_calls_made": self.tool_calls_made + tool_calls,
                "iteration_count": self.iteration_count + iterations,
            }
        )
