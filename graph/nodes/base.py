import time
from abc import ABC, abstractmethod
from typing import ClassVar

import structlog

from graph.nodes.node_names import NodeName
from graph.state import TriageState, TriageStateUpdate
from observability.tracing import node_span

log = structlog.get_logger(__name__)


class TriageNode(ABC):
    """Template-method contract every graph node implements.

    Concrete subclasses implement `execute()` with node-specific logic,
    constructing/validating the relevant Pydantic model(s) and writing it
    into the returned partial update (nodes construct/validate the Pydantic
    model, then write it into the TypedDict slot).

    `__call__` is the thin, uniform seam LangGraph actually invokes: it bumps
    the `run_meta.iteration_count` guardrail counter after a successful
    `execute()`, and wraps the call in a Langfuse span
    (`observability.tracing.node_span`) enriched with this node's own
    duration/cost accounting — the cross-cutting concerns every node needs,
    applied once here rather than per subclass. It also marks that span
    `level="ERROR"` whenever `execute()` returns a `run_meta` with new
    entries in `errors` (via `RunMeta.with_error`) — the soft-failure
    counterpart to `handle_node_error` below, for a node that catches and
    converts a real failure into data (e.g. `AutoPostNode`/`ApprovalQueueNode`
    on a GitHub post failure) instead of raising.

    Error handling for an uncaught exception is deliberately NOT done here.
    It's owned by LangGraph's native per-node `error_handler` hook, wired
    once, graph-wide, via `StateGraph.set_node_defaults(error_handler=...)`
    in `graph/builder.py` — that's LangGraph's own tested mechanism for
    "raise in execute() -> RunError + status=FAILED", so it isn't duplicated
    here.

    A future subgraph-backed node (e.g. Researcher's tool-calling loop) does
    NOT go through this class. It's registered as its own compiled
    `StateGraph(TriageState)` passed directly to `add_node()`, so LangGraph's
    automatic subgraph detection (checkpoint namespacing, nested streaming)
    applies — wrapping `.invoke()` inside `execute()` would silently defeat
    that detection, since it relies on inspecting closures/Pregel instances,
    not attribute access through `self`.
    """

    name: ClassVar[NodeName]
    """Canonical graph node name — used as the add_node() key and as
    RunError.node_name on failure."""

    async def __call__(self, state: TriageState) -> TriageStateUpdate:
        run_meta = state["run_meta"]
        with structlog.contextvars.bound_contextvars(
            run_id=str(run_meta.run_id),
            thread_id=run_meta.thread_id,
            trace_id=run_meta.trace_id,
        ):
            log.info("node_started", node=self.name)
            started_at = time.monotonic()
            async with node_span(self.name) as span:
                update = await self.execute(state)
                duration_ms = round((time.monotonic() - started_at) * 1000, 2)
                base_run_meta = update.get("run_meta", state["run_meta"])
                update["run_meta"] = base_run_meta.with_usage(iterations=1)
                if span is not None:
                    # A node can append a RunError without raising (e.g.
                    # AutoPostNode/ApprovalQueueNode on a real GitHub post
                    # failure -- see RunMeta.with_error) -- new_errors
                    # generalizes that signal into the span for any node
                    # using the same pattern, not just these two.
                    new_errors = update["run_meta"].errors[len(run_meta.errors) :]
                    span.update(
                        metadata={
                            "duration_ms": duration_ms,
                            "authoritative_cost_usd_delta": (
                                update["run_meta"].estimated_cost_usd - run_meta.estimated_cost_usd
                            ),
                            "authoritative_cache_read_tokens_delta": (
                                update["run_meta"].cache_read_tokens - run_meta.cache_read_tokens
                            ),
                            **({"new_error_count": len(new_errors)} if new_errors else {}),
                        },
                        level="ERROR" if new_errors else None,
                        status_message=(
                            "; ".join(e.error_message for e in new_errors) if new_errors else None
                        ),
                    )
            log.info("node_finished", node=self.name, duration_ms=duration_ms)

        return update

    @abstractmethod
    async def execute(self, state: TriageState) -> TriageStateUpdate:
        """Node-specific logic. Let exceptions propagate — do not catch
        broadly here; the graph-wide `error_handler` (see class docstring)
        converts them into a `RunError` + `status=FAILED` update."""
        raise NotImplementedError
