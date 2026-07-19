from datetime import UTC, datetime

import structlog
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.nodes import (
    ApprovalQueueNode,
    AutoPostNode,
    DrafterSubgraph,
    PlannerNode,
    ResearcherSubgraph,
    RiskCheckNode,
    route_by_risk,
)
from graph.schemas import RunError, RunStatus
from graph.state import TriageState, TriageStateUpdate

log = structlog.get_logger(__name__)


def handle_node_error(state: TriageState, error: NodeError) -> TriageStateUpdate:
    """Graph-wide error handler (see `set_node_defaults` below): converts
    any node's uncaught exception into a `RunError` + `status=FAILED`
    update, rather than crashing the run."""
    run_error = RunError(
        node_name=error.node, error_message=str(error.error), occurred_at=datetime.now(UTC)
    )
    log.error(
        "node_failed",
        node=error.node,
        error=str(error.error),
        run_id=str(state["run_meta"].run_id),
        thread_id=state["run_meta"].thread_id,
        exc_info=error.error,
    )
    updated_run_meta = state["run_meta"].model_copy(
        update={"errors": [*state["run_meta"].errors, run_error]}
    )
    return TriageStateUpdate(status=RunStatus.FAILED, run_meta=updated_run_meta)


def build_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    *,
    researcher_tools: list[BaseTool] | None = None,
    drafter_tools: list[BaseTool] | None = None,
) -> CompiledStateGraph[TriageState]:
    """Wires the Planner -> Researcher -> Drafter -> Risk check ->
    (auto-post | approval queue) pipeline.

    Stays synchronous and does no I/O: `researcher_tools`/`drafter_tools`
    (MCP/Tavily tools, inherently async to load) are injected by the
    composition root (`main.py`, via `tools.mcp_clients.researcher_toolset()`)
    rather than loaded here — graph construction doing network calls would be
    an architecture smell, and this is also what keeps this function's own
    tests network-free. `None`/empty means a zero-tool node (still runs;
    for the Researcher that means low confidence, for the Drafter it's the
    normal case until the sandboxed code-fix path lands).

    Every simple node here is a `TriageNode` (see `graph/nodes/base.py`).
    The Researcher and the Drafter are `AgentSubgraph`s instead — their own
    compiled `StateGraph`s registered directly via
    `add_node(name, compiled_subgraph)`, bypassing `TriageNode` entirely so
    LangGraph's automatic subgraph detection (checkpoint namespacing, nested
    streaming) applies. They still get `handle_node_error` for free, since
    `set_node_defaults` applies to any node regardless of what its action is.
    """
    workflow = StateGraph(TriageState).set_node_defaults(  # pyright: ignore[reportUnknownMemberType]
        error_handler=handle_node_error,  # pyright: ignore[reportArgumentType]
    )

    # Nodes
    planner = PlannerNode()
    researcher = ResearcherSubgraph(researcher_tools or [])
    drafter = DrafterSubgraph(drafter_tools or [])
    risk_check = RiskCheckNode()
    auto_post = AutoPostNode()
    approval_queue = ApprovalQueueNode()

    # Add nodes and edges. The Researcher's and Drafter's compiled subgraphs
    # are what get registered under their names, not the `AgentSubgraph`
    # instances themselves.
    workflow.add_node(planner.name, planner)  # pyright: ignore[reportUnknownMemberType]
    workflow.add_node(researcher.name, researcher.compile())  # pyright: ignore[reportUnknownMemberType]
    workflow.add_node(drafter.name, drafter.compile())  # pyright: ignore[reportUnknownMemberType]
    for node in (risk_check, auto_post, approval_queue):
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

    return workflow.compile(checkpointer=checkpointer)  # pyright: ignore[reportUnknownMemberType]
