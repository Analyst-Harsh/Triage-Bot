import asyncio
from pathlib import Path
from typing import cast

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import TypeAdapter

from config.settings import get_settings
from graph.builder import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.nodes.node_names import NodeName
from graph.schemas import (
    ActionDecision,
    ActionType,
    ApprovalDecision,
    ApprovalRequest,
    QueuedActionSummary,
)
from graph.state import TriageState, create_initial_state
from observability.logging_config import configure_logging
from tools.mcp_clients import researcher_toolset
from tools.sandbox import sandbox_toolset
from utils.github_client import get_github_client

REPO_FULL_NAME = "arrow-py/arrow"
ISSUE_NUMBER = 1278
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


def prompt_decision_for_action(summary: QueuedActionSummary) -> ActionDecision:
    """Prints one queued action's details and prompts for a y/n decision at
    the terminal, re-prompting until a recognized answer is given. This is
    the interim manual approval surface for `ApprovalQueueNode`'s
    `interrupt()` (see `docs/agent/architecture-conventions.md`) -- no
    dashboard/API exists yet."""
    print(f"\n[{summary.index}] {summary.action_type} -- {summary.summary}")
    print(f"    rationale: {summary.rationale}")
    print(f"    risk: {summary.risk_level} -- {summary.risk_reasoning}")
    if summary.risk_factors:
        print(f"    risk factors: {', '.join(summary.risk_factors)}")
    if summary.action_type == ActionType.CODE_FIX:
        print(f"    target files: {', '.join(summary.target_files)}")
        print(
            f"    sandbox: passed={summary.sandbox_passed} command={summary.sandbox_test_command!r}"
        )
        if summary.diff_preview is not None:
            marker = " (truncated)" if summary.diff_truncated else ""
            print(f"    diff{marker}:\n{summary.diff_preview}")

    while True:
        raw = input("    Approve? [y/n]: ").strip().lower()
        if raw in ("y", "yes"):
            return ActionDecision(index=summary.index, approved=True, note=None)
        if raw in ("n", "no"):
            note = input("    Reason (optional): ").strip()
            return ActionDecision(index=summary.index, approved=False, note=note or None)
        print("    Please answer 'y' or 'n'.")


def collect_approval_decisions(request: ApprovalRequest) -> ApprovalDecision:
    """Prompts for a decision on every queued action in `request`, in
    order, and assembles the typed `ApprovalDecision` `ApprovalQueueNode`
    expects as its resume payload."""
    print(f"\n=== Approval needed: {request.repo_full_name}#{request.issue_number} ===")
    print(f"    {request.issue_url}")
    print(f"    {len(request.actions)} action(s) awaiting review (run {request.run_id})")
    decisions = [prompt_decision_for_action(action) for action in request.actions]
    return ApprovalDecision(decisions=decisions)


async def resume_paused_run(
    graph: CompiledStateGraph[TriageState], config: RunnableConfig, interrupt_value: object
) -> TriageState:
    """Parses the raw `interrupt()` payload back into a typed
    `ApprovalRequest`, collects a human decision for each queued action,
    and resumes the graph with `Command(resume=...)`.

    Validates the decision locally (`ApprovalDecision`'s own model) before
    sending it -- `main.py` is itself now a boundary constructing the
    resume payload, not just a passthrough, even though `ApprovalQueueNode`
    revalidates it server-side as untrusted input regardless (see
    `docs/agent/architecture-conventions.md`).
    """
    request = ApprovalRequest.model_validate(interrupt_value)
    decision = collect_approval_decisions(request)
    # See main.py's `ainvoke` cast above for why this is a `cast`, not a
    # narrower annotation: langgraph's overloads resolve to a
    # partially-Unknown type under strict pyright.
    return cast(
        TriageState,
        await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            Command(resume=decision.model_dump(mode="json")), config
        ),
    )


async def main() -> None:
    configure_logging()
    github_client = get_github_client()
    thread_id = f"{REPO_FULL_NAME}#{ISSUE_NUMBER}"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    async with (
        sqlite_checkpointer() as checkpointer,
        researcher_toolset(get_settings()) as tools,
        # Reuses `github_client.raw` (the same underlying `Github` instance
        # `fetch_issue` uses below), not a second one — opened fresh for this
        # one run, exactly like `researcher_toolset` above.
        sandbox_toolset(get_settings(), github_client.raw, REPO_FULL_NAME) as (
            sandbox_tools,
            sandbox_handle,
        ),
    ):
        graph = build_graph(
            checkpointer=checkpointer,
            researcher_tools=tools,
            drafter_tools=sandbox_tools,
            drafter_sandbox_handle=sandbox_handle,
        )

        # Probe for an already-pending approval on this thread *before*
        # constructing a fresh initial state: `thread_id` is deterministic
        # (repo#issue_number), so invoking with a brand-new state while a
        # prior run is still paused would silently start an independent
        # second run on the same thread instead of resuming it -- including
        # re-running `auto_post` and double-posting every LOW-risk action.
        # Verified empirically that langgraph does exactly this if unguarded.
        snapshot = await graph.aget_state(config)  # pyright: ignore[reportUnknownMemberType]

        if snapshot.next == (NodeName.APPROVAL_QUEUE,):
            log.info("resuming_paused_run", thread_id=thread_id)
            result = await resume_paused_run(graph, config, snapshot.interrupts[0].value)
        else:
            issue = github_client.fetch_issue(REPO_FULL_NAME, ISSUE_NUMBER)
            state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
            log.info(
                "run_started",
                repo=REPO_FULL_NAME,
                issue_number=ISSUE_NUMBER,
                run_id=str(state["run_meta"].run_id),
            )
            # langgraph's ainvoke() overloads resolve to a partially-Unknown type
            # under strict pyright — a library generics gap, same as the
            # `.invoke()` ignore in tests/graph/test_builder.py. The runtime
            # value is always a `TriageState`, since that's the schema
            # `build_graph` compiled the graph against, hence the cast.
            result = cast(
                TriageState,
                await graph.ainvoke(state, config=config),  # pyright: ignore[reportUnknownMemberType]
            )
            if "__interrupt__" in result:
                result = await resume_paused_run(graph, config, result["__interrupt__"][0].value)

        result_path = write_result_file(result)
        log.info(
            "run_finished",
            thread_id=thread_id,
            status=str(result["status"]),
            result_path=str(result_path),
        )


if __name__ == "__main__":
    asyncio.run(main())
