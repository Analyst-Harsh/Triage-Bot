from datetime import UTC, datetime
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph.builder import build_graph
from graph.checkpointer import sqlite_checkpointer
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


async def test_state_survives_reopening_the_same_db_file(tmp_path: Path) -> None:
    """The property that actually matters: state persisted by one
    `AsyncSqliteSaver`/connection is still readable from an independent
    second connection against the same file. `MemorySaver` couldn't do this
    at all — it loses everything once the process/connection is gone."""
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
