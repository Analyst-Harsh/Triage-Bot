from abc import ABC, abstractmethod
from typing import ClassVar

from graph.state import TriageState, TriageStateUpdate


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

    name: ClassVar[str]
    """Canonical graph node name — used as the add_node() key and as
    RunError.node_name on failure. Lowercase snake_case, e.g. "planner"."""

    def __call__(self, state: TriageState) -> TriageStateUpdate:
        update = self.execute(state)
        base_run_meta = update.get("run_meta", state["run_meta"])
        update["run_meta"] = base_run_meta.model_copy(
            update={"iteration_count": base_run_meta.iteration_count + 1}
        )
        return update

    @abstractmethod
    def execute(self, state: TriageState) -> TriageStateUpdate:
        """Node-specific logic. Let exceptions propagate — do not catch
        broadly here; the graph-wide `error_handler` (see class docstring)
        converts them into a `RunError` + `status=FAILED` update."""
        raise NotImplementedError
