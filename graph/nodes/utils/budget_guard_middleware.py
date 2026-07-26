from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

from graph.errors import BudgetExceededError
from graph.nodes.trajectory import estimate_trajectory_usage
from graph.schemas import RunMeta


class BudgetGuardState(AgentState):
    """`AgentState` plus `run_meta` -- not middleware-private state (unlike
    e.g. `ModelCallLimitMiddleware`'s own `ModelCallLimitState`), but a key
    already owned by the parent graph (`TriageState`/`AgentLoopState`).
    LangGraph's subgraph nesting matches state by key name: since
    `AgentSubgraph.build_agent()`'s compiled graph is itself registered as
    the `"agent"` node inside `AgentSubgraph.compile()`'s own
    `StateGraph(AgentLoopState)`, declaring `run_meta` here is what makes
    the *current* value flow in from the parent state on every model turn,
    not just once at subgraph entry -- verified empirically (see this
    middleware's own test file for the nested-subgraph spike that confirms
    this before relying on it in production)."""

    run_meta: RunMeta


class BudgetGuardMiddleware(AgentMiddleware[BudgetGuardState]):
    """Re-checks the run's cost budget before every in-loop model turn --
    `AgentSubgraph.prepare_node`'s own `check_budget` call
    (`graph/nodes/utils/budget_guard.py`) only runs once, at subgraph entry,
    so it can't catch a multi-call Researcher/Drafter loop blowing through
    budget partway through. Projects cost including the in-flight
    trajectory (`estimate_trajectory_usage`, recomputed fresh each turn --
    cheap, and avoids a second accumulator to keep checkpoint-synced with
    `RunMeta.estimated_cost_usd`) rather than waiting for the loop to finish
    and `assemble_node` to fold the real total back into `run_meta`.

    Raises `BudgetExceededError` directly (rather than `exit_behavior="end"`,
    `ToolCallLimitMiddleware`'s softer style) -- a cost overrun is the one
    guardrail category this codebase treats as a hard abort, not a
    graceful degrade (see `graph/errors.py`'s docstring for why that's still
    safe: it flows through the same `handle_node_error` path as any other
    node exception, not a new propagation mechanism).
    """

    state_schema = BudgetGuardState  # type: ignore[assignment]

    def __init__(self, *, node_name: str) -> None:
        super().__init__()
        self._node_name = node_name

    async def abefore_model(
        self,
        state: BudgetGuardState,
        runtime: Runtime[Any],  # noqa: ARG002
    ) -> dict[str, Any] | None:
        run_meta = state["run_meta"]
        trajectory = estimate_trajectory_usage(state["messages"])
        projected_cost = run_meta.estimated_cost_usd + trajectory.cost_usd
        if projected_cost >= run_meta.max_cost_usd:
            raise BudgetExceededError(
                node_name=self._node_name,
                dimension="cost_usd",
                current=projected_cost,
                limit=run_meta.max_cost_usd,
            )
        return None
