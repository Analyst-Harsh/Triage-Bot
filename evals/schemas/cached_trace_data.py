from datetime import datetime

from pydantic import BaseModel, JsonValue


class CachedTraceData(BaseModel):
    """Local, gitignored cache of one Langfuse trace's raw observations --
    see `evals.cache_store.TraceCache`. Holds only the verbatim fetched API
    response; `ReconstructedRun`/`ReconstructedTrajectory` are derived fresh
    from `raw_observations` every time they're needed, never persisted --
    reconstruction is a pure, in-memory computation, so recomputing it costs
    nothing measurable, while the fetch itself is what's actually expensive
    to lose to Langfuse's free-tier ~2-month retention window."""

    trace_id: str
    fetched_at: datetime
    raw_observations: list[JsonValue]
