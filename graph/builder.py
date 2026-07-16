from datetime import UTC, datetime

from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.nodes import (
    ApprovalQueueNode,
    AutoPostNode,
    DrafterNode,
    PlannerNode,
    ResearcherNode,
    RiskCheckNode,
    route_by_risk,
)
from graph.schemas import RunError, RunStatus
from graph.state import TriageState, TriageStateUpdate


def handle_node_error(state: TriageState, error: NodeError) -> TriageStateUpdate:
    """Graph-wide error handler (see `set_node_defaults` below): converts
    any node's uncaught exception into a `RunError` + `status=FAILED`
    update, rather than crashing the run."""
    run_error = RunError(
        node_name=error.node, error_message=str(error.error), occurred_at=datetime.now(UTC)
    )
    updated_run_meta = state["run_meta"].model_copy(
        update={"errors": [*state["run_meta"].errors, run_error]}
    )
    return TriageStateUpdate(status=RunStatus.FAILED, run_meta=updated_run_meta)


def build_graph() -> CompiledStateGraph[TriageState]:
    """Wires the Planner -> Researcher -> Drafter -> Risk check ->
    (auto-post | approval queue) pipeline.

    Every node here is a `TriageNode` (see `graph/nodes/base.py`). A future
    subgraph-backed node (e.g. Researcher's tool-calling loop) would instead
    be its own compiled `StateGraph(TriageState)` registered directly via
    `add_node(name, compiled_subgraph)` — bypassing `TriageNode` entirely so
    LangGraph's automatic subgraph detection (checkpoint namespacing, nested
    streaming) applies. It still gets `handle_node_error` for free, since
    `set_node_defaults` applies to any node regardless of what its action is.
    """
    workflow = StateGraph(TriageState).set_node_defaults(  # pyright: ignore[reportUnknownMemberType]
        error_handler=handle_node_error,  # pyright: ignore[reportArgumentType]
    )

    # Nodes
    planner = PlannerNode()
    researcher = ResearcherNode()
    drafter = DrafterNode()
    risk_check = RiskCheckNode()
    auto_post = AutoPostNode()
    approval_queue = ApprovalQueueNode()

    # Add Nodes and edges.
    for node in (planner, researcher, drafter, risk_check, auto_post, approval_queue):
        workflow.add_node(node.name, node)  # pyright: ignore[reportUnknownMemberType]

    workflow.add_edge(START, planner.name)
    workflow.add_edge(planner.name, researcher.name)
    workflow.add_edge(researcher.name, drafter.name)
    workflow.add_edge(drafter.name, risk_check.name)
    workflow.add_conditional_edges(
        risk_check.name,
        route_by_risk,
        {"auto_post": auto_post.name, "approval_queue": approval_queue.name},
    )
    workflow.add_edge(auto_post.name, END)
    workflow.add_edge(approval_queue.name, END)

    return workflow.compile()  # pyright: ignore[reportUnknownMemberType]
