from langfuse import get_client
from pydantic import JsonValue


def fetch_all_observations(trace_id: str) -> list[JsonValue]:
    """Fetches every observation for `trace_id`, paginated via Langfuse's
    cursor-based `observations.get_many` -- confirmed empirically:
    `ObservationsV2Meta` has no `page`/`limit`/`total_items`, only `cursor`;
    loop while `meta.cursor` is truthy, passing it back as `cursor=...`.

    Requests `fields="core,basic,io,metadata"` explicitly -- omitting `"io"`/
    `"metadata"` silently returns `None` for those fields regardless of what's
    actually stored server-side (the same trap
    `scripts/verify_langfuse_metadata.py` documents for `"metadata"` alone).

    Does NOT pass `parse_io_as_json` -- confirmed via a live 400 response
    that the v2 observations endpoint no longer supports it ("Input/output
    fields are always returned as raw strings"). Every `input`/`output` on
    the returned observations is a JSON-encoded string; `evals.langfuse_fetch
    .reconstruct` is responsible for `json.loads`-ing them, not this
    function.

    Assumes the caller already ran `evals.langfuse_fetch.client
    .ensure_configured()` -- this function does not construct the Langfuse
    client itself.

    Each observation is returned via `model_dump(mode="json")`, which -- for
    this SDK's Fern-generated models -- serializes using field *aliases*
    (confirmed empirically: `parentObservationId`, `startTime`, `traceId`,
    not the snake_case Python field names), because of a custom
    `model_serializer` these models define for JSON mode. `reconstruct.py`
    keys into these dicts by their camelCase alias names for exactly this
    reason.
    """
    client = get_client()
    observations: list[JsonValue] = []
    cursor: str | None = None
    while True:
        response = client.api.observations.get_many(
            trace_id=trace_id,
            fields="core,basic,io,metadata",
            limit=100,
            cursor=cursor,
        )
        observations.extend(obs.model_dump(mode="json") for obs in response.data)
        if not response.meta.cursor:
            break
        cursor = response.meta.cursor
    return observations
