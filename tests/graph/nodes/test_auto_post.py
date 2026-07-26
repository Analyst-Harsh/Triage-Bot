from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

import pytest

from graph.nodes.utils.action_executor import ActionExecutor
from graph.schemas import (
    ActionPostResult,
    ActionRiskAssessment,
    CloseAction,
    CommentAction,
    DraftedAction,
    DraftOutput,
    IssueType,
    LabelAction,
    PlannerOutput,
    PostOutcome,
    RiskAssessment,
    RiskLevel,
    RunStatus,
)
from graph.state import TriageState
from tests.graph.nodes.conftest import make_fake_auto_post_node
from utils.episodic_memory_store import BaseEpisodicMemoryStore, EpisodicMemoryUnavailableError


def _draft(actions: list[DraftedAction]) -> DraftOutput:
    return DraftOutput(
        actions=actions,
        overall_rationale="Test overall rationale.",
        unsupported_claims=[],
        drafted_at=datetime.now(UTC),
    )


def _risk(levels: list[RiskLevel]) -> RiskAssessment:
    return RiskAssessment(
        action_assessments=[
            ActionRiskAssessment(level=level, risk_factors=[], reasoning="Test.")
            for level in levels
        ],
        assessed_at=datetime.now(UTC),
    )


def _comment_action(body: str = "Thanks for the report!") -> DraftedAction:
    return DraftedAction(action=CommentAction(comment_body=body), rationale="Acknowledge report.")


def _label_action() -> DraftedAction:
    return DraftedAction(
        action=LabelAction(labels_to_add=["bug"], labels_to_remove=["stale"]),
        rationale="Matches the bug pattern.",
    )


def _close_action() -> DraftedAction:
    return DraftedAction(
        action=CloseAction(reason="duplicate", close_comment="Duplicate of #10."),
        rationale="Matches a known duplicate pattern.",
    )


def make_fake_action_executor() -> Any:
    """Returns `Any`, not `ActionExecutor`: callers need Mock-specific
    introspection (`.execute.assert_awaited_with`/`.execute.side_effect`)
    that the real class's type stub doesn't expose."""
    return create_autospec(ActionExecutor, instance=True, spec_set=True)


def make_planner_output(**overrides: Any) -> PlannerOutput:
    defaults: dict[str, Any] = {
        "issue_type": IssueType.BUG,
        "classification_confidence": 0.9,
        "investigation_plan": [],
        "reasoning": "Test reasoning.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)


def make_memory_store_stub() -> Any:
    return create_autospec(BaseEpisodicMemoryStore, instance=True, spec_set=True)


def _with_dry_run(state: TriageState, *, dry_run: bool) -> TriageState:
    state["run_meta"] = state["run_meta"].model_copy(update={"dry_run": dry_run})
    return state


async def test_low_risk_actions_are_routed_to_action_executor_in_order(
    triage_state: TriageState,
) -> None:
    """A draft mixing LOW and non-LOW actions: only the LOW ones are routed
    to `ActionExecutor.execute`, in order, and each call's returned
    `ActionPostResult` is used verbatim at that action's position."""
    triage_state["draft"] = _draft([_comment_action(), _close_action(), _label_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.LOW])
    _with_dry_run(triage_state, dry_run=False)
    action_executor = make_fake_action_executor()
    comment_result = ActionPostResult(outcome=PostOutcome.POSTED, detail="comment-url")
    label_result = ActionPostResult(outcome=PostOutcome.FAILED, detail="boom")
    action_executor.execute.side_effect = [comment_result, label_result]
    node = make_fake_auto_post_node(action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "post_results" in update
    post_results = update["post_results"]
    assert post_results is not None
    assert post_results.action_results == [
        comment_result,
        ActionPostResult(outcome=PostOutcome.QUEUED),
        label_result,
    ]

    issue = triage_state["issue"]
    run_id = triage_state["run_meta"].run_id
    assert action_executor.execute.await_count == 2
    action_executor.execute.assert_any_await(
        triage_state["draft"].actions[0], issue, dry_run=False, run_id=run_id
    )
    action_executor.execute.assert_any_await(
        triage_state["draft"].actions[2], issue, dry_run=False, run_id=run_id
    )
    assert "status" in update
    # One action (index 1) was queued as MEDIUM risk -- the run isn't done.
    assert update["status"] == RunStatus.PENDING_APPROVAL


async def test_non_low_risk_actions_never_reach_action_executor(
    triage_state: TriageState,
) -> None:
    triage_state["draft"] = _draft([_close_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.HIGH])
    action_executor = make_fake_action_executor()
    node = make_fake_auto_post_node(action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "post_results" in update
    post_results = update["post_results"]
    assert post_results is not None
    assert post_results.action_results == [ActionPostResult(outcome=PostOutcome.QUEUED)]
    action_executor.execute.assert_not_awaited()
    assert "status" in update
    assert update["status"] == RunStatus.PENDING_APPROVAL


async def test_all_low_risk_actions_set_status_auto_posted(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action(), _label_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW, RiskLevel.LOW])
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_auto_post_node(action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.AUTO_POSTED


async def test_failed_post_appends_a_run_error_without_changing_status(
    triage_state: TriageState,
) -> None:
    """A real GitHub-post failure (ActionExecutor.execute returning
    PostOutcome.FAILED, not raising) must not be silently swallowed: status
    still records the routing decision (documented, deliberate -- see
    docs/agent/architecture-conventions.md), but run_meta.errors gains the
    signal that reaches RunError/the node's Langfuse span."""
    triage_state["draft"] = _draft([_comment_action(), _label_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW, RiskLevel.LOW])
    action_executor = make_fake_action_executor()
    action_executor.execute.side_effect = [
        ActionPostResult(outcome=PostOutcome.POSTED, detail="comment-url"),
        ActionPostResult(outcome=PostOutcome.FAILED, detail="GitHub API timed out"),
    ]
    node = make_fake_auto_post_node(action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.AUTO_POSTED
    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert len(run_meta.errors) == 1
    assert run_meta.errors[0].node_name == node.name
    assert "GitHub API timed out" in run_meta.errors[0].error_message


async def test_no_failed_posts_leaves_run_meta_errors_empty(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW])
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_auto_post_node(action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.errors == []


async def test_raises_when_draft_or_risk_assessment_missing(triage_state: TriageState) -> None:
    node = make_fake_auto_post_node()

    with pytest.raises(ValueError, match="draft/risk_assessment"):
        await node.execute(triage_state)


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW])
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_auto_post_node(action_executor=action_executor)

    update = await node(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.iteration_count == 1


async def test_saves_episode_when_all_low_risk_and_not_dry_run(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW])
    triage_state["planner_output"] = make_planner_output()
    _with_dry_run(triage_state, dry_run=False)
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    memory_store = make_memory_store_stub()
    node = make_fake_auto_post_node(memory_store, action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.AUTO_POSTED
    memory_store.save_episode.assert_awaited_once()
    call_kwargs = memory_store.save_episode.await_args.kwargs
    assert call_kwargs["outcome"] == RunStatus.AUTO_POSTED
    assert call_kwargs["run_id"] == triage_state["run_meta"].run_id


async def test_does_not_save_episode_when_pending_approval(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action(), _close_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW, RiskLevel.MEDIUM])
    triage_state["planner_output"] = make_planner_output()
    _with_dry_run(triage_state, dry_run=False)
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    memory_store = make_memory_store_stub()
    node = make_fake_auto_post_node(memory_store, action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.PENDING_APPROVAL
    memory_store.save_episode.assert_not_awaited()


async def test_does_not_save_episode_when_dry_run(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW])
    triage_state["planner_output"] = make_planner_output()
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    memory_store = make_memory_store_stub()
    node = make_fake_auto_post_node(memory_store, action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.AUTO_POSTED
    memory_store.save_episode.assert_not_awaited()


async def test_memory_store_failure_does_not_fail_run(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW])
    triage_state["planner_output"] = make_planner_output()
    _with_dry_run(triage_state, dry_run=False)
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    memory_store = make_memory_store_stub()
    memory_store.save_episode.side_effect = EpisodicMemoryUnavailableError("connection refused")
    node = make_fake_auto_post_node(memory_store, action_executor=action_executor)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.AUTO_POSTED
