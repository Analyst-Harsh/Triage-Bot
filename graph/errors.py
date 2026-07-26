from typing import Literal


class BudgetExceededError(Exception):
    """Raised when a run's accumulated cost or iteration count has already
    met or exceeded its own `RunMeta.max_cost_usd`/`max_iterations` ceiling,
    checked before a node (or, inside an `AgentSubgraph`'s tool-calling loop,
    a single model turn) is allowed to start.

    Deliberately flows through the *same* `handle_node_error` path
    (`graph/builder.py`, wired via `StateGraph.set_node_defaults`) as any
    other node exception -- converted to a `RunError` + `status=FAILED`
    update rather than propagating past the graph boundary. `handle_node_error`
    special-cases this type only to log a distinct `budget_exceeded` event
    (so it's never confused with a real application bug in traces/logs);
    the state-update behavior itself is identical to the default path.
    """

    def __init__(
        self,
        *,
        node_name: str,
        dimension: Literal["cost_usd", "iterations"],
        current: float,
        limit: float,
    ) -> None:
        self.node_name = node_name
        self.dimension = dimension
        self.current = current
        self.limit = limit
        super().__init__(
            f"Run exceeded its {dimension} budget at node {node_name!r}: {current} >= {limit}"
        )
