from datetime import UTC, datetime

from graph.schemas import IssuePayload, IssueSource, IssueType, PlannerOutput
from prompts.researcher import build_investigation_message, build_researcher_system_prompt


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
        "investigation_plan": ["search codebase for NoneType", "check startup sequence"],
        "reasoning": "Traceback matches a known startup failure pattern.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)  # pyright: ignore[reportArgumentType]


def test_build_researcher_system_prompt_lists_tool_names() -> None:
    prompt = build_researcher_system_prompt(["search_code", "web_search"])

    assert "search_code" in prompt
    assert "web_search" in prompt


def test_build_researcher_system_prompt_notes_no_tools_available() -> None:
    prompt = build_researcher_system_prompt([])

    assert "none available" in prompt


def test_build_investigation_message_includes_issue_and_plan() -> None:
    issue = _make_issue()
    planner_output = _make_planner_output()

    message = build_investigation_message(issue, planner_output)

    assert message.type == "human"
    content = str(message.content)
    assert "octo/repo" in content
    assert "search codebase for NoneType" in content
    assert "check startup sequence" in content
    assert "bug" in content
