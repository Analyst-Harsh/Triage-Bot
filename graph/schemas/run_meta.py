from datetime import UTC, datetime
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
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    max_iterations: int
    max_cost_usd: float
    errors: list[RunError] = []
    # When True (the safe default), AutoPostNode computes per-action post
    # outcomes but skips the actual GitHub write -- the replay pipeline runs
    # against real historical issues in real repos this bot doesn't own.
    dry_run: bool = True

    def with_usage(
        self,
        *,
        cost_usd: float = 0.0,
        tool_calls: int = 0,
        iterations: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> RunMeta:
        """Returns a copy with `estimated_cost_usd`/`tool_calls_made`/
        `iteration_count`/`cache_read_tokens`/`cache_creation_tokens` each
        incremented by the given amount (default 0, i.e. unchanged) -- the
        one place every node accumulates run-level usage onto `RunMeta`, so
        the accumulation arithmetic isn't hand-duplicated at each call
        site."""
        return self.model_copy(
            update={
                "estimated_cost_usd": self.estimated_cost_usd + cost_usd,
                "tool_calls_made": self.tool_calls_made + tool_calls,
                "iteration_count": self.iteration_count + iterations,
                "cache_read_tokens": self.cache_read_tokens + cache_read_tokens,
                "cache_creation_tokens": self.cache_creation_tokens + cache_creation_tokens,
            }
        )

    def with_error(self, *, node_name: str, error_message: str) -> RunMeta:
        """Returns a copy with one more `RunError` appended to `errors` --
        the same accumulation shape as `with_usage`, for nodes that catch
        and convert a real failure (e.g. a GitHub post) into data rather
        than letting it raise, so it still reaches the same place
        `handle_node_error` (`graph/builder.py`) writes to for an uncaught
        exception."""
        return self.model_copy(
            update={
                "errors": [
                    *self.errors,
                    RunError(
                        node_name=node_name,
                        error_message=error_message,
                        occurred_at=datetime.now(UTC),
                    ),
                ]
            }
        )
