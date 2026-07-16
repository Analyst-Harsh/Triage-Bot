from datetime import UTC, datetime

from langgraph.errors import NodeError

from graph.builder import build_graph, handle_node_error
from graph.schemas import IssuePayload, IssueSource, RunStatus
from graph.state import create_initial_state


def make_issue() -> IssuePayload:
    return IssuePayload(
        repo_full_name="octo/repo",
        issue_number=42,
        title="Crash on startup",
        body="App crashes with a NoneType error.",
        author="octocat",
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/42",
        source=IssueSource.WEBHOOK,
    )


def test_build_graph_registers_all_six_nodes() -> None:
    graph = build_graph()

    node_names = set(graph.get_graph().nodes.keys())
    assert {
        "planner",
        "researcher",
        "drafter",
        "risk_check",
        "auto_post",
        "approval_queue",
    } <= node_names


def test_invoke_flows_through_all_nodes_to_auto_post() -> None:
    graph = build_graph()
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)

    # langgraph's CompiledStateGraph.invoke() overloads resolve to a
    # partially-Unknown type under strict pyright for the same reason as the
    # builder-method ignores in graph/builder.py — a library generics gap,
    # not ours.
    result = graph.invoke(state)  # pyright: ignore[reportUnknownMemberType]

    # Stub RiskCheckNode always reports LOW risk, so this run always takes
    # the auto_post branch — both branches of route_by_risk are proven
    # independently in tests/graph/nodes/test_routing.py.
    assert result["status"] == RunStatus.AUTO_POSTED
    assert result["planner_output"] is not None
    assert result["research_findings"] is not None
    assert result["draft"] is not None
    assert result["risk_assessment"] is not None
    assert len(result["messages"]) == 1
    assert result["run_meta"].iteration_count == 5


def test_handle_node_error_records_run_error_and_fails_run() -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    error = NodeError(node="planner", error=ValueError("boom"))

    update = handle_node_error(state, error)

    assert "status" in update
    assert update["status"] == RunStatus.FAILED
    assert "run_meta" in update
    assert update["run_meta"] is not None
    errors = update["run_meta"].errors
    assert len(errors) == 1
    assert errors[0].node_name == "planner"
    assert "boom" in errors[0].error_message
