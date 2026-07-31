from datetime import datetime

from graph.schemas.base import StrictBaseModel


class TraceObservation(StrictBaseModel):
    """One Langfuse observation (span/generation/event/chain) within a
    trace, normalized from the raw camelCase-aliased SDK fields
    `observability.langfuse_reader.fetch_observations` returns (confirmed
    against the installed `langfuse` package's `ObservationV2` model).

    `observation_type` is deliberately `str`, not a closed `Literal` --
    this pipeline's own traces contain `"CHAIN"` observations (the
    top-level LangGraph invocation, and each `AgentSubgraph` node) in
    addition to Langfuse's own `"SPAN"`/`"GENERATION"`/`"EVENT"` (see
    `evals/langfuse_fetch/reconstruct.py`'s own `"CHAIN"` matching) --
    render whatever string comes back rather than validating against an
    incomplete closed set.

    `level` is optional -- the real SDK model's `level` field is itself
    optional, and `ObservationLevel` has four values (including `DEBUG`),
    not three."""

    observation_id: str
    parent_observation_id: str | None
    name: str | None
    observation_type: str
    start_time: datetime
    end_time: datetime | None
    latency_seconds: float | None
    cost_usd: float | None
    level: str | None
