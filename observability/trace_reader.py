"""Builds the dashboard API's embedded trace-summary response
(`TraceSummaryResponse`) from `langfuse_reader.fetch_observations`'s raw
observation dicts -- the one new piece Task 4 actually adds on top of the
fetch logic moved from `evals/langfuse_fetch/` in the prior task. Does not
reuse `evals/langfuse_fetch/reconstruct.py`'s chain-finding/state
reconstruction -- that logic exists to recover a full `TriageState` from
one specific top-level chain, which a duration/cost-per-observation summary
has no need for; every observation in the trace belongs in this summary,
not just the ones under the winning chain.
"""

from datetime import datetime

from pydantic import JsonValue

from api.schemas.trace_observation import TraceObservation
from api.schemas.trace_summary_response import TraceSummaryResponse


def _as_observation_dict(observation: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(observation, dict):
        raise ValueError(f"expected an observation dict, got {type(observation)}")
    return observation


def _to_observation(raw: dict[str, JsonValue]) -> TraceObservation:
    """Maps one raw Langfuse observation dict (camelCase-aliased SDK field
    names -- see `langfuse_reader.fetch_observations`'s docstring) onto
    `TraceObservation`'s snake_case fields via `model_validate`, which also
    handles the JSON-string -> `datetime` coercion for `startTime`/`endTime`
    (raw dicts here are `model_dump(mode="json")` output, so timestamps are
    ISO strings, not `datetime` objects, until Pydantic parses them here)."""
    return TraceObservation.model_validate(
        {
            "observation_id": raw["id"],
            "parent_observation_id": raw.get("parentObservationId"),
            "name": raw.get("name"),
            "observation_type": raw["type"],
            "start_time": raw["startTime"],
            "end_time": raw.get("endTime"),
            "latency_seconds": raw.get("latency"),
            "cost_usd": raw.get("totalCost"),
            "level": raw.get("level"),
        }
    )


def build_trace_summary(
    trace_id: str, observations: list[JsonValue], *, langfuse_host: str
) -> TraceSummaryResponse:
    """`total_latency_seconds` is the observed wall-clock span across every
    observation (`latest end_time or start_time` minus `earliest
    start_time`) -- a heuristic, not Langfuse's own root-span latency,
    deliberately: identifying "the" root observation would mean reusing
    `reconstruct.py`'s chain-finding logic for a summary view that doesn't
    otherwise need it. `total_cost_usd` is a real sum, not a heuristic --
    unlike wall-clock time, per-observation cost figures aren't nested
    (a parent span's cost doesn't double-count a child generation's spend),
    so summing every observation's `totalCost` is the correct total.

    Verified against a real 188-observation trace (24 `GENERATION`s among
    them): `totalCost`/`usageDetails`/`costDetails` are `None` on every
    observation regardless of `fields` group requested (`"core,basic"` vs.
    `"core,basic,model"` -- the latter surfaces `model`/`inputPrice`/
    `outputPrice`/`totalPrice`, none of which are a computed dollar cost
    without multiplying by token usage, which was equally absent). This
    project tracks cost authoritatively itself (`RunMeta.estimated_cost_usd`,
    already surfaced via `RunSummary`) rather than relying on Langfuse's own
    per-generation cost calculation -- `cost_usd`/`total_cost_usd` being
    `None` in practice for this deployment is expected, not a bug in this
    fetch; both fields stay in the schema since other Langfuse projects with
    cost tracking fully wired up would populate them."""
    parsed = [_to_observation(_as_observation_dict(obs)) for obs in observations]

    total_latency_seconds: float | None = None
    if parsed:
        start_times = [o.start_time for o in parsed]
        end_times = [o.end_time for o in parsed if o.end_time is not None]
        latest: datetime = max(end_times) if end_times else max(start_times)
        total_latency_seconds = (latest - min(start_times)).total_seconds()

    costs = [o.cost_usd for o in parsed if o.cost_usd is not None]
    total_cost_usd = sum(costs) if costs else None

    return TraceSummaryResponse(
        trace_id=trace_id,
        langfuse_url=f"{langfuse_host}/trace/{trace_id}",
        total_latency_seconds=total_latency_seconds,
        total_cost_usd=total_cost_usd,
        observations=parsed,
    )
