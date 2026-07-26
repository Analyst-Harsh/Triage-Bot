from graph.errors import BudgetExceededError
from graph.schemas import RunMeta


def check_budget(run_meta: RunMeta, *, node_name: str) -> None:
    """Raises `BudgetExceededError` if `run_meta`'s own accumulated cost or
    iteration count already meets or exceeds its own ceiling.

    A plain module-level function, not a class: a single self-contained
    check with no shared state/config (same carve-out this repo already
    applies to `route_after_auto_post`). Called once per node entry --
    `TriageNode.__call__` (`graph/nodes/base.py`) for every simple node, and
    `AgentSubgraph.prepare_node` (`graph/nodes/agent_subgraph.py`) for the
    Researcher/Drafter's own node-entry equivalent. For a node that only
    ever makes one LLM call per `execute()`, this single check already *is*
    the pre-call check; a multi-call agent loop additionally re-checks
    before each in-loop model turn via `BudgetGuardMiddleware`
    (`graph/nodes/utils/budget_guard_middleware.py`), since a single
    Researcher/Drafter invocation can make several calls the one entry
    check can't see coming.
    """
    if run_meta.estimated_cost_usd >= run_meta.max_cost_usd:
        raise BudgetExceededError(
            node_name=node_name,
            dimension="cost_usd",
            current=run_meta.estimated_cost_usd,
            limit=run_meta.max_cost_usd,
        )
    if run_meta.iteration_count >= run_meta.max_iterations:
        raise BudgetExceededError(
            node_name=node_name,
            dimension="iterations",
            current=run_meta.iteration_count,
            limit=run_meta.max_iterations,
        )
