from datetime import UTC, datetime

import pytest
from github import Github
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import NodeError
from pydantic import SecretStr
from structlog.testing import capture_logs

import graph.builder as builder_module
from config.settings import Settings
from graph.builder import build_graph, handle_node_error
from graph.nodes.drafter import DrafterSubgraph
from graph.schemas import IssuePayload, IssueSource, PostOutcome, RunStatus
from graph.state import create_initial_state
from tests.graph.nodes.conftest import (
    make_fake_auto_post_node,
    make_fake_drafter_subgraph,
    make_fake_planner_node,
    make_fake_researcher_subgraph,
    make_fake_risk_check_node,
)
from tools.sandbox import SandboxHandle


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


def test_build_graph_registers_all_six_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    # AutoPostNode's real __init__ resolves the process-wide GitHubClient
    # singleton (via Settings) -- faked here so these tests stay hermetic
    # and don't depend on the developer's local Settings/.env, matching how
    # PlannerNode/RiskCheckNode/DrafterSubgraph/ResearcherSubgraph are faked
    # below.
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    # ResearcherSubgraph/DrafterSubgraph/RiskCheckNode's real __init__s all
    # build real OpenAI chat clients via Settings -- faked for the same
    # hermeticity reason as AutoPostNode above. `build_graph()` constructs
    # every node unconditionally, so even this purely-structural test (no
    # invocation) needs all of them faked, not just the ones it's asserting
    # on.
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    monkeypatch.setattr(builder_module, "RiskCheckNode", make_fake_risk_check_node)
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


async def test_invoke_flows_through_all_nodes_to_auto_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    # AutoPostNode's real __init__ resolves the process-wide GitHubClient
    # singleton (via Settings) -- faked here so these tests stay hermetic
    # and don't depend on the developer's local Settings/.env, matching how
    # PlannerNode/RiskCheckNode/DrafterSubgraph are faked below.
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    # ResearcherSubgraph's real __init__ builds a real OpenAI chat client via
    # Settings -- faked here so this test stays hermetic and doesn't depend
    # on the developer's local Settings/.env, matching AutoPostNode above.
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    # DrafterSubgraph never short-circuits (drafting always happens, unlike
    # the Researcher's empty-investigation-plan skip) -- without this fake it
    # would make a real LLM call during this test.
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    # The fake Drafter's output includes a CommentAction, which RiskCheckNode
    # now sends through a real LLM judgment call (labels/code fixes are
    # hardcoded, but comments/closes aren't) -- without this fake, this test
    # would make a real LLM call too.
    monkeypatch.setattr(builder_module, "RiskCheckNode", make_fake_risk_check_node)
    graph = build_graph()
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)

    # langgraph's CompiledStateGraph.ainvoke() overloads resolve to a
    # partially-Unknown type under strict pyright for the same reason as the
    # builder-method ignores in graph/builder.py — a library generics gap,
    # not ours.
    result = await graph.ainvoke(state)  # pyright: ignore[reportUnknownMemberType]

    # The graph is now strictly linear: risk_check -> auto_post ->
    # approval_queue -> END (no conditional routing). approval_queue is
    # still a no-op stub (out of scope for this change) that unconditionally
    # overwrites status to PENDING_APPROVAL, even though the fake
    # RiskCheckNode reports LOW risk and auto_post's own (dry-run, since
    # create_initial_state defaults dry_run=True) post_results show the one
    # drafted action as POSTED.
    assert result["status"] == RunStatus.PENDING_APPROVAL
    assert result["planner_output"] is not None
    assert result["research_findings"] is not None
    assert result["draft"] is not None
    assert result["risk_assessment"] is not None
    assert result["run_meta"].dry_run is True
    post_results = result["post_results"]
    assert post_results is not None
    assert [r.outcome for r in post_results.action_results] == [PostOutcome.POSTED]
    assert result["run_meta"].iteration_count == 6


def test_build_graph_threads_checkpointer_through_compile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    # AutoPostNode's real __init__ resolves the process-wide GitHubClient
    # singleton (via Settings) -- faked here so these tests stay hermetic
    # and don't depend on the developer's local Settings/.env, matching how
    # PlannerNode/RiskCheckNode/DrafterSubgraph are faked below.
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    # ResearcherSubgraph/DrafterSubgraph/RiskCheckNode's real __init__s all
    # build real OpenAI chat clients via Settings -- faked here for the same
    # hermeticity reason as AutoPostNode above; `build_graph()` constructs
    # every node unconditionally regardless of what this test asserts on.
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    monkeypatch.setattr(builder_module, "RiskCheckNode", make_fake_risk_check_node)
    checkpointer = InMemorySaver()

    graph = build_graph(checkpointer=checkpointer)

    # Same library generics gap as the ignores elsewhere in this file/builder.py.
    assert graph.checkpointer is checkpointer  # pyright: ignore[reportUnknownMemberType]


def test_build_graph_threads_sandbox_handle_into_drafter_subgraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    # AutoPostNode's real __init__ resolves the process-wide GitHubClient
    # singleton (via Settings) -- faked here so these tests stay hermetic
    # and don't depend on the developer's local Settings/.env, matching how
    # PlannerNode/RiskCheckNode/DrafterSubgraph are faked below.
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    # ResearcherSubgraph's real __init__ builds a real OpenAI chat client via
    # Settings -- faked here so this test stays hermetic and doesn't depend
    # on the developer's local Settings/.env, matching AutoPostNode above.
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    # RiskCheckNode's real __init__ builds a real OpenAI chat client via
    # Settings too -- faked for the same reason, since `build_graph()`
    # constructs it unconditionally regardless of what this test asserts on.
    monkeypatch.setattr(builder_module, "RiskCheckNode", make_fake_risk_check_node)
    # Spy that wraps the existing `_FakeDrafterSubgraph` test double (so no
    # real LLM call happens if the graph were ever invoked) while capturing
    # the constructed instance itself -- `build_graph()` doesn't return the
    # `DrafterSubgraph` it builds, so this is the only way to inspect what
    # it was constructed with, mirroring the `monkeypatch.setattr(...,
    # "PlannerNode"/"DrafterSubgraph", ...)` pattern already used elsewhere
    # in this file.
    constructed: list[DrafterSubgraph] = []

    def spy_drafter_subgraph(
        tools: list[BaseTool] | None = None, *, sandbox_handle: SandboxHandle | None = None
    ) -> DrafterSubgraph:
        subgraph = make_fake_drafter_subgraph(tools, sandbox_handle=sandbox_handle)
        constructed.append(subgraph)
        return subgraph

    monkeypatch.setattr(builder_module, "DrafterSubgraph", spy_drafter_subgraph)
    # A real `SandboxHandle` with dummy settings/client -- safe here since
    # `build_graph()` only threads it through construction, never calls
    # `ensure_ready()` or any other method that would touch E2B/GitHub.
    handle = SandboxHandle(
        settings=Settings(e2b_api_key=SecretStr("test-e2b-key")),
        github_client=Github(),
        repo_full_name="octo/repo",
        ref=None,
    )

    build_graph(drafter_sandbox_handle=handle)

    assert len(constructed) == 1
    # Inspecting the private attribute directly is the established pattern
    # for this kind of construction-threading check (see `_FakeDrafterSubgraph`
    # in tests/graph/nodes/conftest.py, which stores it the same way, and the
    # `reportPrivateUsage` ignore precedent in tests/graph/nodes/test_drafter.py).
    assert constructed[0]._sandbox_handle is handle  # pyright: ignore[reportPrivateUsage]


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


def test_handle_node_error_logs_structured_error() -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    error = NodeError(node="planner", error=ValueError("boom"))

    with capture_logs() as cap_logs:
        handle_node_error(state, error)

    assert len(cap_logs) == 1
    entry = cap_logs[0]
    assert entry["event"] == "node_failed"
    assert entry["log_level"] == "error"
    assert entry["node"] == "planner"
    assert entry["error"] == "boom"
    assert entry["run_id"] == str(state["run_meta"].run_id)
    assert isinstance(entry["exc_info"], ValueError)
