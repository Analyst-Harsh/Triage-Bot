from datetime import UTC, datetime

import pytest

from graph.schemas import (
    ActionRiskJudgment,
    CloseAction,
    CodeFixAction,
    CommentAction,
    DraftedAction,
    DraftOutput,
    LabelAction,
    RiskJudgmentBatch,
    RiskLevel,
    RunStatus,
    SandboxResult,
)
from graph.state import TriageState
from tests.graph.nodes.conftest import make_fake_risk_check_node


def _draft(
    actions: list[DraftedAction], *, unsupported_claims: list[str] | None = None
) -> DraftOutput:
    return DraftOutput(
        actions=actions,
        overall_rationale="Test overall rationale.",
        unsupported_claims=unsupported_claims or [],
        drafted_at=datetime.now(UTC),
    )


def _label_action() -> DraftedAction:
    return DraftedAction(
        action=LabelAction(labels_to_add=["bug"], labels_to_remove=[]),
        rationale="Matches the bug pattern.",
    )


def _code_fix_action() -> DraftedAction:
    return DraftedAction(
        action=CodeFixAction(
            diff="--- a/foo.py\n+++ b/foo.py\n",
            target_files=["foo.py"],
            sandbox_result=SandboxResult(
                passed=True, logs="all green", test_command="pytest", duration_seconds=1.2
            ),
            base_commit_sha="abc123",
            base_ref="main",
        ),
        rationale="Reproduced and fixed in sandbox.",
    )


def _comment_action(body: str = "Thanks for the report, looking into it.") -> DraftedAction:
    return DraftedAction(action=CommentAction(comment_body=body), rationale="Acknowledge report.")


def _close_action() -> DraftedAction:
    return DraftedAction(
        action=CloseAction(reason="duplicate", close_comment="Duplicate of #10."),
        rationale="Matches a known duplicate pattern.",
    )


async def test_execute_hardcodes_label_as_low_with_no_llm_call(
    triage_state: TriageState,
) -> None:
    triage_state["draft"] = _draft([_label_action()])
    node = make_fake_risk_check_node()

    update = await node.execute(triage_state)

    assert "risk_assessment" in update
    risk_assessment = update["risk_assessment"]
    assert risk_assessment is not None
    assert len(risk_assessment.action_assessments) == 1
    assert risk_assessment.action_assessments[0].level == RiskLevel.LOW
    # No LLM call was needed -- run_meta is omitted entirely (no cost to add).
    assert "run_meta" not in update
    assert "status" in update
    assert update["status"] == RunStatus.RISK_CHECK


async def test_execute_hardcodes_code_fix_as_high_with_no_llm_call(
    triage_state: TriageState,
) -> None:
    triage_state["draft"] = _draft([_code_fix_action()])
    node = make_fake_risk_check_node()

    update = await node.execute(triage_state)

    assert "risk_assessment" in update
    risk_assessment = update["risk_assessment"]
    assert risk_assessment is not None
    assert risk_assessment.action_assessments[0].level == RiskLevel.HIGH
    assert "run_meta" not in update


async def test_execute_judges_comment_via_llm(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action()])
    node = make_fake_risk_check_node(
        parsed_result=RiskJudgmentBatch(
            judgments=[
                ActionRiskJudgment(
                    action_index=0,
                    level=RiskLevel.MEDIUM,
                    risk_factors=["assertive tone"],
                    reasoning="Makes a claim not fully backed by evidence.",
                )
            ]
        )
    )

    update = await node.execute(triage_state)

    assert "risk_assessment" in update
    risk_assessment = update["risk_assessment"]
    assert risk_assessment is not None
    assert risk_assessment.action_assessments[0].level == RiskLevel.MEDIUM
    assert risk_assessment.action_assessments[0].risk_factors == ["assertive tone"]
    # A real LLM call happened -- run_meta must be present with added cost.
    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.estimated_cost_usd > triage_state["run_meta"].estimated_cost_usd


async def test_unsupported_claims_bump_llm_verdict_to_at_least_medium(
    triage_state: TriageState,
) -> None:
    triage_state["draft"] = _draft(
        [_close_action()], unsupported_claims=["Claims the fix was already released."]
    )
    node = make_fake_risk_check_node(
        parsed_result=RiskJudgmentBatch(
            judgments=[
                ActionRiskJudgment(
                    action_index=0, level=RiskLevel.LOW, risk_factors=[], reasoning="Looks routine."
                )
            ]
        )
    )

    update = await node.execute(triage_state)

    assert "risk_assessment" in update
    risk_assessment = update["risk_assessment"]
    assert risk_assessment is not None
    assert risk_assessment.action_assessments[0].level == RiskLevel.MEDIUM


async def test_unsupported_claims_floor_never_downgrades_a_high_verdict(
    triage_state: TriageState,
) -> None:
    triage_state["draft"] = _draft(
        [_comment_action()], unsupported_claims=["Some unsupported claim."]
    )
    node = make_fake_risk_check_node(
        parsed_result=RiskJudgmentBatch(
            judgments=[
                ActionRiskJudgment(
                    action_index=0,
                    level=RiskLevel.HIGH,
                    risk_factors=["dismissive tone"],
                    reasoning="Reads as dismissive.",
                )
            ]
        )
    )

    update = await node.execute(triage_state)

    assert "risk_assessment" in update
    risk_assessment = update["risk_assessment"]
    assert risk_assessment is not None
    assert risk_assessment.action_assessments[0].level == RiskLevel.HIGH


async def test_raises_when_llm_omits_judgment_for_an_action(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_comment_action(), _close_action()])
    node = make_fake_risk_check_node(
        parsed_result=RiskJudgmentBatch(
            judgments=[
                ActionRiskJudgment(
                    action_index=0, level=RiskLevel.LOW, risk_factors=[], reasoning="Routine."
                )
            ]
        )
    )

    with pytest.raises(ValueError, match="action_index 1"):
        await node.execute(triage_state)


async def test_mixed_draft_exercises_all_three_paths(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_label_action(), _comment_action(), _code_fix_action()])
    node = make_fake_risk_check_node(
        parsed_result=RiskJudgmentBatch(
            judgments=[
                ActionRiskJudgment(
                    action_index=1,
                    level=RiskLevel.MEDIUM,
                    risk_factors=["substantive claim"],
                    reasoning="Substantive comment.",
                )
            ]
        )
    )

    update = await node.execute(triage_state)

    assert "risk_assessment" in update
    risk_assessment = update["risk_assessment"]
    assert risk_assessment is not None
    levels = [a.level for a in risk_assessment.action_assessments]
    assert levels == [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
    # Only the comment (index 1) needed an LLM call -- cost still gets folded in.
    assert "run_meta" in update


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    triage_state["draft"] = _draft([_label_action()])
    node = make_fake_risk_check_node()

    update = await node(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.iteration_count == 1
