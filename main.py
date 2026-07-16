import asyncio
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig

from graph.builder import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.schemas import IssuePayload, IssueSource
from graph.state import create_initial_state


async def main() -> None:
    issue = IssuePayload(
        repo_full_name="octo/repo",
        issue_number=1,
        title="Sample issue",
        body="Demonstrates a checkpointed run.",
        author="octocat",
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/1",
        source=IssueSource.WEBHOOK,
    )
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
    config: RunnableConfig = {"configurable": {"thread_id": state["run_meta"].thread_id}}

    async with sqlite_checkpointer() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        # langgraph's ainvoke() overloads resolve to a partially-Unknown type
        # under strict pyright — a library generics gap, same as the
        # `.invoke()` ignore in tests/graph/test_builder.py, not ours.
        result = await graph.ainvoke(state, config=config)  # pyright: ignore[reportUnknownMemberType]
        print(f"thread_id={state['run_meta'].thread_id} status={result['status']}")


if __name__ == "__main__":
    asyncio.run(main())
