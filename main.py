import asyncio

import structlog
from langchain_core.runnables import RunnableConfig

from api.github_client import build_github_client, fetch_issue
from config.settings import get_settings
from graph.builder import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.state import create_initial_state
from observability.logging_config import configure_logging
from tools.mcp_clients import researcher_toolset

REPO_FULL_NAME = "octocat/Hello-World"
ISSUE_NUMBER = 1

log = structlog.get_logger(__name__)


async def main() -> None:
    configure_logging()
    client = build_github_client()
    issue = fetch_issue(client, REPO_FULL_NAME, ISSUE_NUMBER)
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
    config: RunnableConfig = {"configurable": {"thread_id": state["run_meta"].thread_id}}
    log.info(
        "run_started",
        repo=REPO_FULL_NAME,
        issue_number=ISSUE_NUMBER,
        run_id=str(state["run_meta"].run_id),
    )

    async with (
        sqlite_checkpointer() as checkpointer,
        researcher_toolset(get_settings()) as tools,
    ):
        graph = build_graph(checkpointer=checkpointer, researcher_tools=tools)
        # langgraph's ainvoke() overloads resolve to a partially-Unknown type
        # under strict pyright — a library generics gap, same as the
        # `.invoke()` ignore in tests/graph/test_builder.py, not ours.
        result = await graph.ainvoke(state, config=config)  # pyright: ignore[reportUnknownMemberType]
        log.info(
            "run_finished",
            thread_id=state["run_meta"].thread_id,
            result=result,
        )


if __name__ == "__main__":
    asyncio.run(main())
