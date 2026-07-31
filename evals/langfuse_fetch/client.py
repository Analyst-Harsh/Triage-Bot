from evals.schemas import GoldenCase
from graph.state import thread_id_for
from observability.langfuse_reader import ensure_configured
from observability.tracing import create_trace_id

__all__ = ["ensure_configured", "resolve_trace_id"]


def resolve_trace_id(golden_case: GoldenCase) -> str:
    """Re-derives the deterministic trace_id for a golden case exactly the
    way `graph.state.create_initial_state` derives it for a real run --
    `thread_id = thread_id_for(repo, issue_number)`, `trace_id = create_trace_id(thread_id)`.
    No run_id/trace_id is ever stored on `GoldenCase` itself."""
    thread_id = thread_id_for(golden_case.repo_full_name, golden_case.issue_number)
    return create_trace_id(thread_id)


# `ensure_configured` now lives in `observability/langfuse_reader.py` -- a
# second consumer (the dashboard API's trace-summary endpoint) needed it
# outside the eval harness. Re-exported here so `evals/cli.py`'s existing
# `from evals.langfuse_fetch.client import ensure_configured` keeps working
# unmodified.
