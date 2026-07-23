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
    LabelAction,
    PostOutcome,
    RiskAssessment,
    RiskLevel,
    RunStatus,
)
from graph.state import TriageState
from tests.graph.nodes.conftest import make_fake_auto_post_node


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
    node = make_fake_auto_post_node(action_executor)

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
    assert action_executor.execute.await_count == 2
    action_executor.execute.assert_any_await(
        triage_state["draft"].actions[0].action, issue, dry_run=False
    )
    action_executor.execute.assert_any_await(
        triage_state["draft"].actions[2].action, issue, dry_run=False
    )
    assert "status" in update
    assert update["status"] == RunStatus.AUTO_POSTED


async def test_non_low_risk_actions_never_reach_action_executor(
    triage_state: TriageState,
) -> None:
    triage_state["draft"] = _draft([_close_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.HIGH])
    action_executor = make_fake_action_executor()
    node = make_fake_auto_post_node(action_executor)

    update = await node.execute(triage_state)

    assert "post_results" in update
    post_results = update["post_results"]
    assert post_results is not None
    assert post_results.action_results == [ActionPostResult(outcome=PostOutcome.QUEUED)]
    action_executor.execute.assert_not_awaited()


async def test_raises_when_draft_or_risk_assessment_missing(triage_state: TriageState) -> None:
    node = make_fake_auto_post_node()

    with pytest.raises(ValueError, match="draft/risk_assessment"):
        await node.execute(triage_state)


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW])
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_auto_post_node(action_executor)

    update = await node(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.iteration_count == 1
