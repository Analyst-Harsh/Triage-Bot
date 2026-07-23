from datetime import UTC, datetime

from graph.schemas import CloseAction, CommentAction, DraftedAction, DraftOutput, ResearchFindings
from prompts.risk_check import build_risk_judgment_messages, format_judged_actions_for_prompt


def _draft(
    actions: list[DraftedAction], *, unsupported_claims: list[str] | None = None
) -> DraftOutput:
    return DraftOutput(
        actions=actions,
        overall_rationale="Overall rationale for this draft.",
        unsupported_claims=unsupported_claims or [],
        drafted_at=datetime.now(UTC),
    )


def _research_findings(**overrides: object) -> ResearchFindings:
    defaults: dict[str, object] = {
        "summary": "Investigated the crash.",
        "confidence": 0.8,
        "researched_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ResearchFindings(**defaults)  # pyright: ignore[reportArgumentType]


def test_format_judged_actions_for_prompt_includes_action_index_and_text() -> None:
    draft = _draft(
        [DraftedAction(action=CommentAction(comment_body="Could you share logs?"), rationale="r")]
    )

    formatted = format_judged_actions_for_prompt(draft, [0])

    assert "[action_index=0]" in formatted
    assert "Could you share logs?" in formatted


def test_format_judged_actions_for_prompt_only_includes_given_indices() -> None:
    draft = _draft(
        [
            DraftedAction(action=CommentAction(comment_body="First comment."), rationale="r"),
            DraftedAction(
                action=CloseAction(reason="duplicate", close_comment="Duplicate of #10"),
                rationale="r",
            ),
        ]
    )

    formatted = format_judged_actions_for_prompt(draft, [1])

    assert "First comment." not in formatted
    assert "[action_index=1]" in formatted
    assert "Duplicate of #10" in formatted


def test_build_risk_judgment_messages_includes_overall_rationale_and_confidence() -> None:
    draft = _draft([DraftedAction(action=CommentAction(comment_body="Thanks!"), rationale="r")])
    messages = build_risk_judgment_messages(draft, _research_findings(confidence=0.42), [0])

    assert len(messages) == 2
    assert messages[0].type == "system"
    assert messages[1].type == "human"
    assert "Overall rationale for this draft." in messages[1].content
    assert "0.42" in messages[1].content


def test_build_risk_judgment_messages_notes_no_unsupported_claims() -> None:
    draft = _draft([DraftedAction(action=CommentAction(comment_body="Thanks!"), rationale="r")])
    messages = build_risk_judgment_messages(draft, _research_findings(), [0])

    assert "(none)" in messages[1].content


def test_build_risk_judgment_messages_includes_unsupported_claims() -> None:
    draft = _draft(
        [DraftedAction(action=CommentAction(comment_body="Thanks!"), rationale="r")],
        unsupported_claims=["Claims the fix already shipped."],
    )
    messages = build_risk_judgment_messages(draft, _research_findings(), [0])

    assert "Claims the fix already shipped." in messages[1].content


def test_build_risk_judgment_messages_handles_missing_research_findings() -> None:
    draft = _draft([DraftedAction(action=CommentAction(comment_body="Thanks!"), rationale="r")])
    messages = build_risk_judgment_messages(draft, None, [0])

    assert "no research findings" in messages[1].content
