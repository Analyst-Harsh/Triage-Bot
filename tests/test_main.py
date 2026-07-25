from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, create_autospec
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

import graph.builder as builder_module
from graph.builder import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.nodes.node_names import NodeName
from graph.schemas import (
    ActionRiskJudgment,
    ApprovalRequest,
    IssuePayload,
    IssueSource,
    PostOutcome,
    QueuedActionSummary,
    RiskJudgmentBatch,
    RiskLevel,
    RunStatus,
)
from graph.state import TriageState, create_initial_state
from main import collect_approval_decisions, prompt_decision_for_action, resume_paused_run
from tests.graph.nodes.conftest import (
    make_fake_auto_post_node,
    make_fake_drafter_subgraph,
    make_fake_planner_node,
    make_fake_researcher_subgraph,
    make_fake_risk_check_node,
)


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


def make_queued_action_summary(**overrides: Any) -> QueuedActionSummary:
    defaults: dict[str, Any] = {
        "index": 0,
        "action_type": "comment",
        "summary": "Could you share a reproduction?",
        "rationale": "Not enough information to act yet.",
        "risk_level": RiskLevel.MEDIUM,
        "risk_reasoning": "Makes a claim not fully backed by evidence.",
        "risk_factors": ["assertive tone"],
    }
    defaults.update(overrides)
    return QueuedActionSummary(**defaults)


def make_approval_request(**overrides: Any) -> ApprovalRequest:
    defaults: dict[str, Any] = {
        "run_id": uuid4(),
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "issue_url": "https://github.com/octo/repo/issues/42",
        "actions": [make_queued_action_summary()],
        "requested_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ApprovalRequest(**defaults)


def _queued_input(answers: list[str]) -> Callable[[str], str]:
    """A `builtins.input` replacement that returns each of `answers` in
    order, one per call -- lets a test script a whole prompt sequence
    (approve/reject + optional note, possibly with invalid retries) without
    real terminal interaction."""
    remaining = iter(answers)

    def fake_input(_prompt: str) -> str:
        return next(remaining)

    return fake_input


def _medium_risk_check_node() -> Any:
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


# --- prompt_decision_for_action / collect_approval_decisions ----------------


def test_prompt_decision_for_action_approves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", _queued_input(["y"]))

    decision = prompt_decision_for_action(make_queued_action_summary(index=2))

    assert decision.index == 2
    assert decision.approved is True
    assert decision.note is None


def test_prompt_decision_for_action_rejects_with_note(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", _queued_input(["n", "Too risky right now."]))

    decision = prompt_decision_for_action(make_queued_action_summary(index=1))

    assert decision.approved is False
    assert decision.note == "Too risky right now."


def test_prompt_decision_for_action_empty_rejection_note_becomes_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", _queued_input(["n", "   "]))

    decision = prompt_decision_for_action(make_queued_action_summary())

    assert decision.approved is False
    assert decision.note is None


def test_prompt_decision_for_action_reprompts_on_unrecognized_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", _queued_input(["maybe", "later", "yes"]))

    decision = prompt_decision_for_action(make_queued_action_summary())

    assert decision.approved is True


def test_collect_approval_decisions_prompts_each_action_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", _queued_input(["y", "n", "not now"]))
    request = make_approval_request(
        actions=[make_queued_action_summary(index=0), make_queued_action_summary(index=5)]
    )

    decision = collect_approval_decisions(request)

    assert [d.index for d in decision.decisions] == [0, 5]
    assert decision.decisions[0].approved is True
    assert decision.decisions[1].approved is False
    assert decision.decisions[1].note == "not now"


# --- resume_paused_run (unit, fake graph double) -----------------------------


def _make_state(status: RunStatus) -> TriageState:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    state["status"] = status
    return state


async def test_resume_paused_run_sends_command_resume_and_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", _queued_input(["y"]))
    request = make_approval_request(actions=[make_queued_action_summary(index=0)])
    final_state = _make_state(RunStatus.APPROVED_AND_POSTED)

    fake_graph = create_autospec(CompiledStateGraph, instance=True)
    fake_graph.ainvoke = AsyncMock(return_value=final_state)
    config: RunnableConfig = {"configurable": {"thread_id": "octo/repo#42"}}

    result = await resume_paused_run(fake_graph, config, request.model_dump(mode="json"))

    assert result is final_state
    fake_graph.ainvoke.assert_awaited_once()
    sent_command, sent_config = fake_graph.ainvoke.call_args.args
    assert isinstance(sent_command, Command)
    assert sent_command.resume == {"decisions": [{"index": 0, "approved": True, "note": None}]}
    assert sent_config == config


async def test_resume_paused_run_carries_rejection_note_into_resume_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("builtins.input", _queued_input(["n", "Needs more evidence."]))
    request = make_approval_request(actions=[make_queued_action_summary(index=3)])

    fake_graph = create_autospec(CompiledStateGraph, instance=True)
    fake_graph.ainvoke = AsyncMock(return_value=_make_state(RunStatus.REJECTED))
    config: RunnableConfig = {"configurable": {"thread_id": "octo/repo#42"}}

    await resume_paused_run(fake_graph, config, request.model_dump(mode="json"))

    sent_command = fake_graph.ainvoke.call_args.args[0]
    assert sent_command.resume == {
        "decisions": [{"index": 3, "approved": False, "note": "Needs more evidence."}]
    }


# --- integration: real pause + real interrupt payload + resume_paused_run ---


async def test_full_pause_then_resume_via_main_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercises `resume_paused_run`/`collect_approval_decisions` against
    the *real* `snapshot.interrupts[0].value` produced by a real
    `ApprovalQueueNode` interrupt -- not a hand-built payload -- proving the
    exact round trip `main.py` depends on: `Interrupt.value` -> typed
    `ApprovalRequest` -> prompts -> `Command(resume=...)` -> a terminal
    status. `ApprovalQueueNode` is deliberately left real (not monkeypatched
    like the other nodes here)."""
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    monkeypatch.setattr(builder_module, "RiskCheckNode", _medium_risk_check_node)
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    db_path = str(tmp_path / "checkpoints.db")
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
    config: RunnableConfig = {"configurable": {"thread_id": state["run_meta"].thread_id}}

    async with sqlite_checkpointer(db_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        paused = await graph.ainvoke(state, config=config)  # pyright: ignore[reportUnknownMemberType]
        assert "__interrupt__" in paused
        assert paused["status"] == RunStatus.PENDING_APPROVAL

        snapshot = await graph.aget_state(config)  # pyright: ignore[reportUnknownMemberType]
        assert snapshot.next == (NodeName.APPROVAL_QUEUE,)

        monkeypatch.setattr("builtins.input", _queued_input(["y"]))
        result = await resume_paused_run(graph, config, snapshot.interrupts[0].value)

    assert result["status"] == RunStatus.APPROVED_AND_POSTED
    post_results = result["post_results"]
    assert post_results is not None
    assert post_results.action_results[0].outcome == PostOutcome.POSTED


async def test_reinvoking_with_fresh_state_on_a_paused_thread_would_duplicate_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards the exact bug `main()`'s `aget_state` probe exists to
    prevent: without checking for a pending interrupt first, invoking with
    a brand-new initial state on the same (deterministic) thread_id starts
    an independent second run rather than resuming the first -- proven here
    by a different `run_id` and `auto_post` running twice."""
    monkeypatch.setattr(builder_module, "PlannerNode", make_fake_planner_node)
    monkeypatch.setattr(builder_module, "ResearcherSubgraph", make_fake_researcher_subgraph)
    monkeypatch.setattr(builder_module, "DrafterSubgraph", make_fake_drafter_subgraph)
    monkeypatch.setattr(builder_module, "RiskCheckNode", _medium_risk_check_node)
    monkeypatch.setattr(builder_module, "AutoPostNode", make_fake_auto_post_node)
    db_path = str(tmp_path / "checkpoints.db")
    issue = make_issue()
    first_state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
    config: RunnableConfig = {"configurable": {"thread_id": first_state["run_meta"].thread_id}}

    async with sqlite_checkpointer(db_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        first = await graph.ainvoke(first_state, config=config)  # pyright: ignore[reportUnknownMemberType]

        second_state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)
        second = await graph.ainvoke(second_state, config=config)  # pyright: ignore[reportUnknownMemberType]

    assert second["run_meta"].run_id != first["run_meta"].run_id
    assert second["status"] == RunStatus.PENDING_APPROVAL
    # This is exactly why main.py must call `aget_state` first: a snapshot
    # taken right after `first` paused (and before this test's unguarded
    # `second` call) would have reported `next == (NodeName.APPROVAL_QUEUE,)`,
    # which is the signal main.py branches on to resume instead of
    # re-invoking with fresh state.
