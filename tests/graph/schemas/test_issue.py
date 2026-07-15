from datetime import UTC, datetime
from typing import Any

from graph.schemas import IssuePayload, IssueSource


def make_issue(**overrides: Any) -> IssuePayload:
    defaults: dict[str, Any] = {
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "title": "Something broke",
        "body": "Here is what happened...",
        "author": "octocat",
        "author_association": "CONTRIBUTOR",
        "labels": ["bug"],
        "created_at": datetime.now(UTC),
        "url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK,
        "installation_id": 123,
    }
    defaults.update(overrides)
    return IssuePayload(**defaults)


def test_construction() -> None:
    issue = make_issue()
    assert issue.issue_number == 42
    assert issue.source is IssueSource.WEBHOOK


def test_defaults() -> None:
    issue = IssuePayload(
        repo_full_name="octo/repo",
        issue_number=1,
        title="t",
        body="b",
        author="a",
        created_at=datetime.now(UTC),
        url="https://example.com",
        source=IssueSource.REPLAY,
    )
    assert issue.labels == []
    assert issue.author_association is None
    assert issue.installation_id is None


def test_json_round_trip() -> None:
    issue = make_issue()
    restored = IssuePayload.model_validate_json(issue.model_dump_json())
    assert restored == issue
