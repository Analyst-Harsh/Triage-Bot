from api.schemas.trace_observation import TraceObservation
from graph.schemas.base import StrictBaseModel


class TraceSummaryResponse(StrictBaseModel):
    """Response body for `GET /runs/{owner}/{repo}/{issue_number}/trace` --
    an embedded per-node breakdown of one run's Langfuse trace, not a full
    interactive trace viewer (Langfuse's own hosted UI already does that
    far better than reproducing it here). `langfuse_url` is the escape
    hatch to that full UI."""

    trace_id: str
    langfuse_url: str
    total_latency_seconds: float | None
    total_cost_usd: float | None
    observations: list[TraceObservation]
