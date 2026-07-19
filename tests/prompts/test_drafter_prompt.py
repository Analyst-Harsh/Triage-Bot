from datetime import UTC, datetime

from graph.schemas import (
    CloseAction,
    CommentAction,
    DraftedAction,
    Evidence,
    IssuePayload,
    IssueSource,
    IssueType,
    LabelAction,
    PlannerOutput,
    ResearchFindings,
)
from prompts.drafter import (
    GROUNDING_CHECK_PROMPT,
    build_drafter_system_prompt,
    build_drafting_message,
    format_evidence_for_prompt,
    format_public_draft_text,
)


def _make_issue(**overrides: object) -> IssuePayload:
    defaults: dict[str, object] = {
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "title": "Crash on startup",
        "body": "App crashes with a NoneType error.",
        "author": "octocat",
        "created_at": datetime.now(UTC),
        "url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK,
    }
    defaults.update(overrides)
    return IssuePayload(**defaults)  # pyright: ignore[reportArgumentType]


def _make_planner_output(**overrides: object) -> PlannerOutput:
    defaults: dict[str, object] = {
        "issue_type": IssueType.BUG,
        "classification_confidence": 0.9,
        "investigation_plan": ["search codebase for NoneType"],
        "reasoning": "Traceback matches a known startup failure pattern.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)  # pyright: ignore[reportArgumentType]


def _make_findings(**overrides: object) -> ResearchFindings:
    defaults: dict[str, object] = {
        "summary": "Missing null check in the config loader.",
        "evidence": [
            Evidence(
                source_type="docmind",
                reference="src/config.py:12",
                snippet="config = load_config()",
                relevance=0.95,
                sha="deadbeef",
            )
        ],
        "focus_addressed": ["search codebase for NoneType"],
        "gaps": [],
        "confidence": 0.9,
        "researched_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ResearchFindings(**defaults)  # pyright: ignore[reportArgumentType]


def test_build_drafter_system_prompt_lists_tool_names() -> None:
    prompt = build_drafter_system_prompt(["apply_patch", "run_sandbox_tests"])

    assert "apply_patch" in prompt
    assert "run_sandbox_tests" in prompt


def test_build_drafter_system_prompt_notes_no_tools_available() -> None:
    prompt = build_drafter_system_prompt([])

    assert "none available" in prompt


def test_build_drafting_message_includes_issue_and_findings() -> None:
    issue = _make_issue()
    planner_output = _make_planner_output()
    findings = _make_findings()

    message = build_drafting_message(issue, planner_output, findings)

    assert message.type == "human"
    content = str(message.content)
    assert "octo/repo" in content
    assert "bug" in content
    assert "Missing null check in the config loader." in content
    assert "src/config.py:12" in content
    assert "search codebase for NoneType" in content


def test_build_drafting_message_notes_gaps() -> None:
    issue = _make_issue()
    planner_output = _make_planner_output()
    findings = _make_findings(gaps=["Could not confirm the fix on the latest release."])

    message = build_drafting_message(issue, planner_output, findings)

    content = str(message.content)
    assert "Could not confirm the fix on the latest release." in content


def test_format_evidence_for_prompt_includes_reference_and_snippet() -> None:
    evidence = [
        Evidence(
            source_type="docmind",
            reference="src/config.py:12",
            snippet="config = load_config()",
            relevance=0.95,
        )
    ]

    formatted = format_evidence_for_prompt(evidence)

    assert "src/config.py:12" in formatted
    assert "config = load_config()" in formatted


def test_format_evidence_for_prompt_notes_no_evidence() -> None:
    formatted = format_evidence_for_prompt([])

    assert "no evidence" in formatted.lower()


def test_format_public_draft_text_includes_comment_body() -> None:
    actions = [
        DraftedAction(
            action=CommentAction(comment_body="Could you share a reproduction?"),
            rationale="Not enough information to act yet.",
        )
    ]

    formatted = format_public_draft_text(actions)

    assert formatted is not None
    assert "Could you share a reproduction?" in formatted


def test_format_public_draft_text_excludes_rationale() -> None:
    """Regression test: rationale/overall_rationale is internal reasoning,
    never posted to GitHub, and is inherently a judgment call rather than a
    factual claim -- it must never be sent to the grounding self-check as
    part of "the draft", or the check will flag ordinary interpretive
    sentences (e.g. "this aligns with a feature request") as unsupported,
    since they're never literally restated in evidence."""
    actions = [
        DraftedAction(
            action=CommentAction(comment_body="Could you share a reproduction?"),
            rationale="This sentence must never appear in the grounding check input.",
        )
    ]

    formatted = format_public_draft_text(actions)

    assert formatted is not None
    assert "This sentence must never appear in the grounding check input." not in formatted


def test_format_public_draft_text_includes_close_reason_and_comment() -> None:
    actions = [
        DraftedAction(
            action=CloseAction(reason="duplicate", close_comment="Duplicate of #10"),
            rationale="Matches a known duplicate pattern.",
        )
    ]

    formatted = format_public_draft_text(actions)

    assert formatted is not None
    assert "duplicate" in formatted
    assert "Duplicate of #10" in formatted


def test_format_public_draft_text_returns_none_for_label_only_actions() -> None:
    """The bug this fixes: a label-only draft has no public-facing text at
    all, so there is nothing for the grounding self-check to fact-check --
    `None` signals the caller to skip the LLM call entirely rather than
    running it against rationale."""
    actions = [
        DraftedAction(
            action=LabelAction(labels_to_add=["feature_request"], labels_to_remove=[]),
            rationale="This is a feature request, matching the design-improvement pattern.",
        )
    ]

    formatted = format_public_draft_text(actions)

    assert formatted is None


def test_format_public_draft_text_returns_none_for_empty_actions() -> None:
    assert format_public_draft_text([]) is None


def test_grounding_check_prompt_formats_draft_text_and_evidence() -> None:
    messages = GROUNDING_CHECK_PROMPT.format_messages(
        draft_text="comment: Could you share a reproduction?",
        evidence="src/config.py:12: config = load_config()",
    )

    contents = [str(message.content) for message in messages]
    assert any("Could you share a reproduction?" in content for content in contents)
    assert any("src/config.py:12" in content for content in contents)
