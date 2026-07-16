import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

import graph.builder as builder_module
from graph.builder import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.schemas import IssuePayload, IssueSource, RunStatus
from graph.state import create_initial_state
from tests.graph.nodes.conftest import make_fake_planner_node
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

    assert snapshot.values["status"] == RunStatus.AUTO_POSTED
    assert snapshot.values["run_meta"].thread_id == state["run_meta"].thread_id


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
