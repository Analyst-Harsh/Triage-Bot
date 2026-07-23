import time
from abc import ABC, abstractmethod
from typing import ClassVar

import structlog

from graph.nodes.node_names import NodeName
from graph.state import TriageState, TriageStateUpdate

log = structlog.get_logger(__name__)


class TriageNode(ABC):
    """Template-method contract every graph node implements.

    Concrete subclasses implement `execute()` with node-specific logic,
    constructing/validating the relevant Pydantic model(s) and writing it
    into the returned partial update (nodes construct/validate the Pydantic
    model, then write it into the TypedDict slot).

    `__call__` is the thin, uniform seam LangGraph actually invokes. Today
    it only bumps the `run_meta.iteration_count` guardrail counter after a
    successful `execute()` — this is also where a future cross-cutting
    concern that must wrap every node body (e.g. an OpenTelemetry span) gets
    added later, without touching any subclass.

    Error handling is deliberately NOT done here. It's owned by LangGraph's
    native per-node `error_handler` hook, wired once, graph-wide, via
    `StateGraph.set_node_defaults(error_handler=...)` in `graph/builder.py`
    — that's LangGraph's own tested mechanism for "raise in execute() ->
    RunError + status=FAILED", so it isn't duplicated here.

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
            update = await self.execute(state)
            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            log.info("node_finished", node=self.name, duration_ms=duration_ms)

        base_run_meta = update.get("run_meta", state["run_meta"])
        update["run_meta"] = base_run_meta.with_usage(iterations=1)
        return update

    @abstractmethod
    async def execute(self, state: TriageState) -> TriageStateUpdate:
        """Node-specific logic. Let exceptions propagate — do not catch
        broadly here; the graph-wide `error_handler` (see class docstring)
        converts them into a `RunError` + `status=FAILED` update."""
        raise NotImplementedError
