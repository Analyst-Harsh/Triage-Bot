import asyncio
from pathlib import Path
from typing import cast

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import TypeAdapter

from api.github_client import build_github_client, fetch_issue
from config.settings import get_settings
from graph.builder import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.state import TriageState, create_initial_state
from observability.logging_config import configure_logging
from tools.mcp_clients import researcher_toolset

REPO_FULL_NAME = "octocat/Spoon-Knife"
ISSUE_NUMBER = 40391
RESULTS_DIR = Path("results")

log = structlog.get_logger(__name__)

_state_adapter: TypeAdapter[TriageState] = TypeAdapter(TriageState)


def write_result_file(result: TriageState) -> Path:
    """Dumps the final `TriageState` to `results/{run_id}.json`.

    Uses `TypeAdapter(TriageState).dump_json` rather than a hand-rolled
    serializer: `TriageState`'s slots are all Pydantic models already, so
    this gets every model's own JSON encoding (UUIDs, datetimes, enums) for
    free and stays correct automatically as new schema fields are added.
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{result['run_meta'].run_id}.json"
    path.write_bytes(_state_adapter.dump_json(result, indent=2))
    return path


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
        # `.invoke()` ignore in tests/graph/test_builder.py. The runtime
        # value is always a `TriageState`, since that's the schema
        # `build_graph` compiled the graph against, hence the cast.
        result = cast(
            TriageState,
            await graph.ainvoke(state, config=config),  # pyright: ignore[reportUnknownMemberType]
        )
        result_path = write_result_file(result)
        log.info(
            "run_finished",
            thread_id=state["run_meta"].thread_id,
            result_path=str(result_path),
        )


if __name__ == "__main__":
    asyncio.run(main())
