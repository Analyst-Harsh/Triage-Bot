import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

import graph.builder as builder_module
import graph.checkpointer as checkpointer_module
from graph.builder import build_graph
from graph.checkpointer import postgres_checkpointer, sqlite_checkpointer
from graph.nodes.node_names import NodeName
from graph.nodes.risk_check import RiskCheckNode
from graph.schemas import (
    ActionRiskJudgment,
    IssuePayload,
    IssueSource,
    PostOutcome,
    RiskJudgmentBatch,
    RiskLevel,
    RunStatus,
)
from graph.state import create_initial_state
from tests.graph.nodes.conftest import (
    make_fake_approval_queue_node,
    make_fake_auto_post_node,
    make_fake_drafter_subgraph,
    make_fake_planner_node,
    make_fake_researcher_subgraph,
    make_fake_risk_check_node,
)
from tests.graph.test_state import make_fully_populated_state


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


async def test_state_survives_reopening_the_same_db_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property that actually matters: state persisted by one
    `AsyncSqliteSaver`/connection is still readable from an independent
    second connection against the same file. `MemorySaver` couldn't do this
    at all — it loses everything once the process/connection is gone."""
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    # ResearcherSubgraph's real __init__ builds a real OpenAI chat client via
    # Settings -- faked here so this test stays hermetic and doesn't depend
    # on the developer's local Settings/.env.
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    # DrafterSubgraph never short-circuits (drafting always happens, unlike
    # the Researcher's empty-investigation-plan skip) -- without this fake it
    # would make a real LLM call during this test.
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    # RiskCheckNode's real __init__ builds a real OpenAI chat client via
    # Settings too; AutoPostNode's real __init__ resolves the process-wide
    # GitHubClient singleton via Settings -- both faked for the same
    # hermeticity reason as ResearcherSubgraph/DrafterSubgraph above, since
    # `build_graph()` constructs every node unconditionally.
    monkeypatch.setattr(builder_module, "RiskCheckNode", make_fake_risk_check_node)
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    db_path = str(tmp_path / "checkpoints.db")
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
    config: RunnableConfig = {"configurable": {"thread_id": state["run_meta"].thread_id}}

    async with sqlite_checkpointer(db_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        await graph.ainvoke(state, config=config)  # pyright: ignore[reportUnknownMemberType]

    async with AsyncSqliteSaver.from_conn_string(db_path) as reopened_checkpointer:
        reopened_graph = build_graph(checkpointer=reopened_checkpointer)
        snapshot = await reopened_graph.aget_state(config)  # pyright: ignore[reportUnknownMemberType]

    # The fake RiskCheckNode judges the fake Drafter's single action LOW
    # risk, so `route_after_auto_post` (graph/nodes/routing.py) sends this run
    # straight to END after `auto_post` -- `approval_queue` never runs.
    assert snapshot.values["status"] == RunStatus.AUTO_POSTED
    assert snapshot.values["run_meta"].thread_id == state["run_meta"].thread_id


def _medium_risk_check_node() -> RiskCheckNode:
    return make_fake_risk_check_node(
        parsed_result=RiskJudgmentBatch(
            judgments=[
                ActionRiskJudgment(
                    action_index=0,
                    level=RiskLevel.MEDIUM,
                    risk_factors=[],
                    reasoning="Test double judgment.",
                )
            ]
        )
    )


async def test_interrupt_checkpoints_and_resumes_across_sqlite_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pause/resume property that matters in production: a run that
    interrupts under one process/connection must still be resumable after
    that connection is closed and a fresh one opens the same database
    file -- proves the interrupt itself, not just ordinary state, survives
    a full checkpointer round trip."""
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    monkeypatch.setattr(builder_module, "RiskCheckNode", _medium_risk_check_node)
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    monkeypatch.setattr(builder_module, "ApprovalQueueNode", make_fake_approval_queue_node)
    db_path = str(tmp_path / "checkpoints.db")
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
    config: RunnableConfig = {"configurable": {"thread_id": state["run_meta"].thread_id}}

    async with sqlite_checkpointer(db_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        paused = await graph.ainvoke(state, config=config)  # pyright: ignore[reportUnknownMemberType]
        assert "__interrupt__" in paused
        assert paused["status"] == RunStatus.PENDING_APPROVAL

    async with AsyncSqliteSaver.from_conn_string(db_path) as reopened_checkpointer:
        reopened_graph = build_graph(checkpointer=reopened_checkpointer)
        snapshot = await reopened_graph.aget_state(config)  # pyright: ignore[reportUnknownMemberType]
        assert snapshot.next == (NodeName.APPROVAL_QUEUE,)

        resumed = await reopened_graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            Command(resume={"decisions": [{"index": 0, "approved": True}]}), config
        )

    assert resumed["status"] == RunStatus.APPROVED_AND_POSTED
    post_results = resumed["post_results"]
    assert post_results is not None
    assert post_results.action_results[0].outcome == PostOutcome.POSTED


async def test_interrupt_resumes_as_rejected_across_sqlite_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    monkeypatch.setattr(builder_module, "RiskCheckNode", _medium_risk_check_node)
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    monkeypatch.setattr(builder_module, "ApprovalQueueNode", make_fake_approval_queue_node)
    db_path = str(tmp_path / "checkpoints.db")
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
    config: RunnableConfig = {"configurable": {"thread_id": state["run_meta"].thread_id}}

    async with sqlite_checkpointer(db_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        await graph.ainvoke(state, config=config)  # pyright: ignore[reportUnknownMemberType]

    async with AsyncSqliteSaver.from_conn_string(db_path) as reopened_checkpointer:
        reopened_graph = build_graph(checkpointer=reopened_checkpointer)
        resumed = await reopened_graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            Command(resume={"decisions": [{"index": 0, "approved": False, "note": "Not now."}]}),
            config,
        )

    assert resumed["status"] == RunStatus.REJECTED
    post_results = resumed["post_results"]
    assert post_results is not None
    assert post_results.action_results[0].outcome == PostOutcome.REJECTED
    assert post_results.action_results[0].detail == "Not now."


async def test_sqlite_checkpointer_serde_allows_full_schema_round_trip_without_warnings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`_build_checkpoint_serde`'s allow-list (derived from
    `graph.schemas.__all__`) must cover every schema type nested in
    `TriageState` — round-tripping a fully populated state must not trigger
    LangGraph's "unregistered type" warning (which otherwise fires on every
    custom type not explicitly allow-listed)."""
    db_path = str(tmp_path / "checkpoints.db")
    state = make_fully_populated_state()

    async with sqlite_checkpointer(db_path) as checkpointer:
        type_, payload = checkpointer.serde.dumps_typed(state)
        with caplog.at_level(logging.WARNING):
            restored = checkpointer.serde.loads_typed((type_, payload))

    assert restored == state
    assert "unregistered type" not in caplog.text.lower()


class _FakeAsyncPostgresSaver:
    """Duck-typed stand-in for `AsyncPostgresSaver`: `postgres_checkpointer`
    only ever constructs one (passing the pool and serde straight through)
    and awaits `.setup()` before yielding it."""

    def __init__(self, conn: object, *, serde: object = None) -> None:
        self.conn = conn
        self.serde = serde
        self.setup_called = False

    async def setup(self) -> None:
        self.setup_called = True


async def test_postgres_checkpointer_calls_setup_and_yields_saver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(checkpointer_module, "AsyncPostgresSaver", _FakeAsyncPostgresSaver)
    fake_pool = object()

    async with postgres_checkpointer(fake_pool) as saver:  # type: ignore[arg-type]
        assert isinstance(saver, _FakeAsyncPostgresSaver)
        assert saver.conn is fake_pool
        assert saver.setup_called
        assert saver.serde is not None
