"""Reads trace data back out of Langfuse -- the read half of this package's
observability story, complementing `tracing.py`'s write-only span/trace
creation. Moved here from `evals/langfuse_fetch/` (still the eval harness's
own import path, re-exported from there) because a second consumer now
needs it: `trace_reader.py`'s embedded trace-summary panel, reached from the
dashboard API's `GET /runs/{owner}/{repo}/{issue_number}/trace` route. A
harness depending on core infra is the right direction; core infra
depending on a harness is not, hence the move rather than importing
`evals.langfuse_fetch` from here.
"""

from langfuse import get_client
from pydantic import JsonValue

from config.settings import Settings, get_settings
from observability.tracing import ensure_langfuse_client


def ensure_configured(settings: Settings | None = None) -> Settings:
    """Fails fast with a clear `RuntimeError` if Langfuse credentials are
    unset (mirrors `scripts/verify_langfuse_metadata.py`), before any
    cache-miss fetch is attempted, then ensures the process-wide Langfuse
    client singleton is constructed. Returns the resolved `Settings` so a
    caller that already needs it doesn't call `get_settings()` twice."""
    resolved = settings or get_settings()
    if resolved.langfuse_public_key is None or resolved.langfuse_secret_key is None:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are not set (via Settings/.env) -- "
            "required to fetch trace data."
        )
    ensure_langfuse_client(resolved)
    return resolved


def fetch_observations(trace_id: str, *, fields: str = "core,basic,io,metadata") -> list[JsonValue]:
    """Fetches every observation for `trace_id`, paginated via Langfuse's
    cursor-based `observations.get_many` -- confirmed empirically:
    `ObservationsV2Meta` has no `page`/`limit`/`total_items`, only `cursor`;
    loop while `meta.cursor` is truthy, passing it back as `cursor=...`.

    `fields` defaults to every group the eval harness's trace reconstruction
    needs (`evals/langfuse_fetch/reconstruct.py`) -- omitting `"io"`/
    `"metadata"` silently returns `None` for those fields regardless of what's
    actually stored server-side. A lighter caller that only needs timing/
    cost/name (e.g. the dashboard's trace-summary panel) can pass
    `fields="core,basic"` instead.

    Does NOT pass `parse_io_as_json` -- confirmed via a live 400 response
    that the v2 observations endpoint no longer supports it ("Input/output
    fields are always returned as raw strings"). Every `input`/`output` on
    a returned observation is a JSON-encoded string; it's the caller's job
    to `json.loads` them, not this function's.

    Assumes the caller already ran `ensure_configured()` above -- this
    function does not construct the Langfuse client itself.

    Each observation is returned via `model_dump(mode="json")`, which -- for
    this SDK's Fern-generated models -- serializes using field *aliases*
    (confirmed empirically: `parentObservationId`, `startTime`, `traceId`,
    not the snake_case Python field names), because of a custom
    `model_serializer` these models define for JSON mode. Callers keying
    into these dicts must use these camelCase alias names for exactly this
    reason.
    """
    client = get_client()
    observations: list[JsonValue] = []
    cursor: str | None = None
    while True:
        response = client.api.observations.get_many(
            trace_id=trace_id,
            fields=fields,
            limit=100,
            cursor=cursor,
        )
        observations.extend(obs.model_dump(mode="json") for obs in response.data)
        if not response.meta.cursor:
            break
        cursor = response.meta.cursor
    return observations
