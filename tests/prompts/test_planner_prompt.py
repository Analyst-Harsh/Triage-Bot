from datetime import UTC, datetime

from graph.schemas import IssuePayload, IssueSource
from prompts.planner import PLANNER_PROMPT, format_issue_for_prompt


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


def test_format_issue_for_prompt_includes_core_fields() -> None:
    issue = _make_issue()
    formatted = format_issue_for_prompt(issue)

    assert "octo/repo" in formatted
    assert "42" in formatted
    assert "Crash on startup" in formatted
    assert "octocat" in formatted
    assert "App crashes with a NoneType error." in formatted


def test_format_issue_for_prompt_without_labels() -> None:
    issue = _make_issue(labels=[])
    formatted = format_issue_for_prompt(issue)

    assert "Existing labels: (none)" in formatted


def test_format_issue_for_prompt_with_labels() -> None:
    issue = _make_issue(labels=["bug", "needs-triage"])
    formatted = format_issue_for_prompt(issue)

    assert "Existing labels: bug, needs-triage" in formatted


def test_format_issue_for_prompt_without_author_association() -> None:
    issue = _make_issue(author_association=None)
    formatted = format_issue_for_prompt(issue)

    assert "association: NONE" in formatted


def test_planner_prompt_renders_issue_text() -> None:
    issue = _make_issue()
    messages = PLANNER_PROMPT.format_messages(issue_text=format_issue_for_prompt(issue))

    assert len(messages) == 2
    assert messages[0].type == "system"
    assert messages[1].type == "human"
    assert "octo/repo" in messages[1].content
