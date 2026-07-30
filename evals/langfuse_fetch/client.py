from config.settings import Settings, get_settings
from evals.schemas import GoldenCase
from graph.state import thread_id_for
from observability.tracing import create_trace_id, ensure_langfuse_client


def resolve_trace_id(golden_case: GoldenCase) -> str:
    """Re-derives the deterministic trace_id for a golden case exactly the
    way `graph.state.create_initial_state` derives it for a real run --
    `thread_id = thread_id_for(repo, issue_number)`, `trace_id = create_trace_id(thread_id)`.
    No run_id/trace_id is ever stored on `GoldenCase` itself."""
    thread_id = thread_id_for(golden_case.repo_full_name, golden_case.issue_number)
    return create_trace_id(thread_id)


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
            "required to fetch trace data for evals."
        )
    ensure_langfuse_client(resolved)
    return resolved
