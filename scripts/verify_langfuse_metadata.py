"""Manual verification that a node span's `authoritative_*` metadata
(attached via `observability.tracing.node_span` in `TriageNode.__call__`/
`AgentSubgraph.assemble_node`) actually reached Langfuse's server, separate
from whether the dashboard's UI is rendering it. Queries Langfuse's own read
API (`client.api.observations.get_many`) directly rather than relying on the
dashboard, so a "yes/no data reached the server" answer doesn't depend on
which UI panel/tab happens to render metadata.

`fields="core,basic,metadata"` is passed explicitly -- `get_many`'s own docs
say it defaults to `core,basic` only when `fields` is omitted, and `metadata`
is a separate, opt-in field group. Omitting it silently returns
`metadata: None` for every observation regardless of what's actually stored
server-side -- confirmed the hard way once already; don't drop this
argument, or this script goes back to producing false negatives.

This is an empirical spot-check against a real, already-completed run, not
automated CI: it needs a real `trace_id` from a run that already happened
(e.g. from `results/{run_id}.json`'s `run_meta.trace_id`) and real Langfuse
credentials, resolved via `config.settings.get_settings()` (never
`os.environ` directly, per this repo's non-negotiable secrets rule).

Usage:
    uv run python scripts/verify_langfuse_metadata.py --trace-id <hex>
    uv run python scripts/verify_langfuse_metadata.py --trace-id <hex> --name researcher

Langfuse's own ingestion can lag 15-30+ seconds after a run finishes -- if
this prints "0 observations found" right after a run, wait a minute and
rerun before concluding anything is actually missing server-side.
"""

import argparse

from config.settings import get_settings
from observability.tracing import ensure_langfuse_client


def main(trace_id: str, name: str) -> None:
    settings = get_settings()
    if settings.langfuse_public_key is None or settings.langfuse_secret_key is None:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are not set (via Settings/.env) -- "
            "required for this live check."
        )
    ensure_langfuse_client(settings)

    from langfuse import get_client

    client = get_client()
    response = client.api.observations.get_many(
        trace_id=trace_id, name=name, fields="core,basic,metadata"
    )

    print(f"\n=== {len(response.data)} observation(s) named {name!r} in trace {trace_id} ===")
    if not response.data:
        print(
            "No observations found. This could mean: (a) ingestion hasn't caught up yet "
            "-- wait 30-60s and rerun, (b) tracing wasn't actually configured for that run "
            "(RunMeta.trace_id is always populated regardless of whether Langfuse was "
            "configured -- a real trace_id in a result file is not proof tracing was live), "
            "or (c) this trace_id/name genuinely has no such observation."
        )
        return

    for obs in response.data:
        print(f"\nid={obs.id} parent_observation_id={obs.parent_observation_id}")
        print(f"  metadata: {obs.metadata}")
        if obs.metadata and any(str(k).startswith("authoritative_") for k in obs.metadata):
            print("  -> authoritative_* fields ARE present server-side.")
        else:
            print(
                "  -> no authoritative_* fields in this observation's metadata as returned "
                "by the API. Double check `fields` includes 'metadata' before concluding "
                "this is a real data gap -- omitting it produces this exact false negative."
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-id", required=True, help="trace_id from a completed run")
    parser.add_argument("--name", default="planner", help="observation name to filter on")
    args = parser.parse_args()
    main(args.trace_id, args.name)
