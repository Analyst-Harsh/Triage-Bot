from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

import pytest
from pydantic import ValidationError

import graph.nodes.approval_queue as approval_queue_module
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
    PostResults,
    RiskAssessment,
    RiskLevel,
    RunStatus,
)
from graph.state import TriageState
from tests.graph.nodes.conftest import make_fake_approval_queue_node


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


def _post_results(outcomes: list[PostOutcome]) -> PostResults:
    return PostResults(
        action_results=[ActionPostResult(outcome=outcome) for outcome in outcomes],
        evaluated_at=datetime.now(UTC),
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
    return create_autospec(ActionExecutor, instance=True, spec_set=True)


def _set_up_queued_state(
    triage_state: TriageState,
    *,
    actions: list[DraftedAction],
    risk_levels: list[RiskLevel],
    outcomes: list[PostOutcome],
) -> TriageState:
    triage_state["draft"] = _draft(actions)
    triage_state["risk_assessment"] = _risk(risk_levels)
    triage_state["post_results"] = _post_results(outcomes)
    return triage_state


def _stub_interrupt_returning(
    monkeypatch: pytest.MonkeyPatch, resume_value: dict[str, Any]
) -> None:
    def _fake_interrupt(_payload: dict[str, Any]) -> dict[str, Any]:
        return resume_value

    monkeypatch.setattr(approval_queue_module, "interrupt", _fake_interrupt)


async def test_raises_when_draft_missing(triage_state: TriageState) -> None:
    triage_state["risk_assessment"] = _risk([RiskLevel.MEDIUM])
    triage_state["post_results"] = _post_results([PostOutcome.QUEUED])
    node = make_fake_approval_queue_node()

    with pytest.raises(ValueError, match="draft/risk_assessment/post_results"):
        await node.execute(triage_state)


async def test_raises_when_risk_assessment_missing(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["post_results"] = _post_results([PostOutcome.QUEUED])
    node = make_fake_approval_queue_node()

    with pytest.raises(ValueError, match="draft/risk_assessment/post_results"):
        await node.execute(triage_state)


async def test_raises_when_post_results_missing(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.MEDIUM])
    node = make_fake_approval_queue_node()

    with pytest.raises(ValueError, match="draft/risk_assessment/post_results"):
        await node.execute(triage_state)


async def test_raises_when_no_actions_queued(triage_state: TriageState) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action()],
        risk_levels=[RiskLevel.LOW],
        outcomes=[PostOutcome.POSTED],
    )
    node = make_fake_approval_queue_node()

    with pytest.raises(ValueError, match="no queued actions"):
        await node.execute(triage_state)


async def test_interrupt_payload_lists_each_queued_action(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action(), _label_action(), _close_action()],
        risk_levels=[RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH],
        outcomes=[PostOutcome.POSTED, PostOutcome.QUEUED, PostOutcome.QUEUED],
    )
    captured_payload: dict[str, Any] = {}

    def _capture_interrupt(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payload.update(payload)
        return {"decisions": [{"index": 1, "approved": True}, {"index": 2, "approved": False}]}

    monkeypatch.setattr(approval_queue_module, "interrupt", _capture_interrupt)
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_approval_queue_node(action_executor)

    await node.execute(triage_state)

    assert [a["index"] for a in captured_payload["actions"]] == [1, 2]
    assert captured_payload["actions"][0]["action_type"] == "label"
    assert captured_payload["actions"][0]["risk_level"] == "medium"
    assert captured_payload["actions"][1]["action_type"] == "close"
    assert captured_payload["actions"][1]["risk_level"] == "high"
    assert captured_payload["issue_number"] == triage_state["issue"].issue_number


async def test_no_side_effects_before_interrupt(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action()],
        risk_levels=[RiskLevel.MEDIUM],
        outcomes=[PostOutcome.QUEUED],
    )

    class _SentinelPauseError(Exception):
        pass

    def _raising_interrupt(_payload: dict[str, Any]) -> Any:
        raise _SentinelPauseError("pausing")

    monkeypatch.setattr(approval_queue_module, "interrupt", _raising_interrupt)
    action_executor = make_fake_action_executor()
    node = make_fake_approval_queue_node(action_executor)

    with pytest.raises(_SentinelPauseError):
        await node.execute(triage_state)

    action_executor.execute.assert_not_awaited()


async def test_approved_action_is_posted_and_overwrites_queued_slot(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action()],
        risk_levels=[RiskLevel.MEDIUM],
        outcomes=[PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(monkeypatch, {"decisions": [{"index": 0, "approved": True}]})
    action_executor = make_fake_action_executor()
    posted_result = ActionPostResult(outcome=PostOutcome.POSTED, detail="comment-url")
    action_executor.execute.return_value = posted_result
    node = make_fake_approval_queue_node(action_executor)

    update = await node.execute(triage_state)

    assert "post_results" in update
    post_results = update["post_results"]
    assert post_results is not None
    assert post_results.action_results == [posted_result]
    action_executor.execute.assert_awaited_once()


async def test_rejected_action_recorded_as_rejected_and_not_posted(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action()],
        risk_levels=[RiskLevel.MEDIUM],
        outcomes=[PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(
        monkeypatch,
        {"decisions": [{"index": 0, "approved": False, "note": "Too risky right now."}]},
    )
    action_executor = make_fake_action_executor()
    node = make_fake_approval_queue_node(action_executor)

    update = await node.execute(triage_state)

    assert "post_results" in update
    post_results = update["post_results"]
    assert post_results is not None
    assert post_results.action_results == [
        ActionPostResult(outcome=PostOutcome.REJECTED, detail="Too risky right now.")
    ]
    action_executor.execute.assert_not_awaited()


async def test_prior_auto_posted_slots_are_untouched(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    auto_posted_result = ActionPostResult(outcome=PostOutcome.POSTED, detail="already-posted-url")
    triage_state["draft"] = _draft([_label_action(), _comment_action()])
    triage_state["risk_assessment"] = _risk([RiskLevel.LOW, RiskLevel.MEDIUM])
    triage_state["post_results"] = PostResults(
        action_results=[auto_posted_result, ActionPostResult(outcome=PostOutcome.QUEUED)],
        evaluated_at=datetime.now(UTC),
    )
    _stub_interrupt_returning(monkeypatch, {"decisions": [{"index": 1, "approved": True}]})
    action_executor = make_fake_action_executor()
    approved_result = ActionPostResult(outcome=PostOutcome.POSTED, detail="new-url")
    action_executor.execute.return_value = approved_result
    node = make_fake_approval_queue_node(action_executor)

    update = await node.execute(triage_state)

    assert "post_results" in update
    post_results = update["post_results"]
    assert post_results is not None
    assert post_results.action_results == [auto_posted_result, approved_result]


async def test_all_rejected_sets_status_rejected(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action(), _label_action()],
        risk_levels=[RiskLevel.MEDIUM, RiskLevel.HIGH],
        outcomes=[PostOutcome.QUEUED, PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(
        monkeypatch,
        {
            "decisions": [
                {"index": 0, "approved": False},
                {"index": 1, "approved": False},
            ]
        },
    )
    node = make_fake_approval_queue_node()

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.REJECTED


async def test_mixed_decisions_set_status_approved_and_posted(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action(), _label_action()],
        risk_levels=[RiskLevel.MEDIUM, RiskLevel.HIGH],
        outcomes=[PostOutcome.QUEUED, PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(
        monkeypatch,
        {
            "decisions": [
                {"index": 0, "approved": True},
                {"index": 1, "approved": False},
            ]
        },
    )
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_approval_queue_node(action_executor)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.APPROVED_AND_POSTED


async def test_dry_run_and_run_id_are_passed_to_executor(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafted_action = _comment_action()
    _set_up_queued_state(
        triage_state,
        actions=[drafted_action],
        risk_levels=[RiskLevel.MEDIUM],
        outcomes=[PostOutcome.QUEUED],
    )
    triage_state["run_meta"] = triage_state["run_meta"].model_copy(update={"dry_run": False})
    _stub_interrupt_returning(monkeypatch, {"decisions": [{"index": 0, "approved": True}]})
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_approval_queue_node(action_executor)

    await node.execute(triage_state)

    action_executor.execute.assert_awaited_once_with(
        drafted_action,
        triage_state["issue"],
        dry_run=False,
        run_id=triage_state["run_meta"].run_id,
    )


async def test_resume_with_wrong_index_set_raises(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action()],
        risk_levels=[RiskLevel.MEDIUM],
        outcomes=[PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(monkeypatch, {"decisions": [{"index": 5, "approved": True}]})
    node = make_fake_approval_queue_node()

    with pytest.raises(ValueError, match="do not match"):
        await node.execute(triage_state)


async def test_resume_with_duplicate_indices_raises(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action(), _label_action()],
        risk_levels=[RiskLevel.MEDIUM, RiskLevel.HIGH],
        outcomes=[PostOutcome.QUEUED, PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(
        monkeypatch,
        {
            "decisions": [
                {"index": 0, "approved": True},
                {"index": 0, "approved": False},
            ]
        },
    )
    node = make_fake_approval_queue_node()

    with pytest.raises(ValueError, match="duplicate indices"):
        await node.execute(triage_state)


async def test_resume_with_extra_fields_raises(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action()],
        risk_levels=[RiskLevel.MEDIUM],
        outcomes=[PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(
        monkeypatch,
        {"decisions": [{"index": 0, "approved": True, "sneaky": "field"}]},
    )
    node = make_fake_approval_queue_node()

    with pytest.raises(ValidationError, match="sneaky"):
        await node.execute(triage_state)


async def test_call_bumps_iteration_count(
    triage_state: TriageState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_queued_state(
        triage_state,
        actions=[_comment_action()],
        risk_levels=[RiskLevel.MEDIUM],
        outcomes=[PostOutcome.QUEUED],
    )
    _stub_interrupt_returning(monkeypatch, {"decisions": [{"index": 0, "approved": True}]})
    action_executor = make_fake_action_executor()
    action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    node = make_fake_approval_queue_node(action_executor)

    update = await node(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.iteration_count == 1
