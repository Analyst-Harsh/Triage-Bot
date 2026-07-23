"""Tests for `api.github_client`: `GitHubClient`'s read/write GitHub
operations and the `get_github_client()` singleton factory.

`GitHubClient.__init__` is real production construction (builds its own
`Github` from `Settings` -- no test-only constructor parameter). Tests that
need a fake substitute `_FakeGitHubClient`, a private subclass overriding
`__init__` to accept an already-faked `Github` directly, mirroring the
`_FakePlannerNode`/`_FakeRiskCheckNode`-style test doubles in
`tests/graph/nodes/conftest.py`.

Every PyGithub object below is a `create_autospec(..., spec_set=True)` fake
rather than a hand-rolled stand-in — this repo has no network access in
tests, and autospec fails loudly (AttributeError) if these fakes drift from
PyGithub's real attribute surface, while `create_autospec`'s `-> Any` return
type keeps strict pyright satisfied without a single `# pyright: ignore`.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

import pytest
from github import Auth, Github, GithubException
from github.Issue import Issue
from github.IssueComment import IssueComment
from github.Label import Label
from github.NamedUser import NamedUser
from github.Repository import Repository
from pydantic import SecretStr

from api.github_client import GitHubClient, get_github_client
from config.settings import Settings
from graph.schemas import IssueSource


@pytest.fixture(autouse=True)
def clear_github_client_singleton() -> None:
    """`get_github_client()` is `@lru_cache`d for real singleton behavior in
    production, but that means tests exercising different `Settings`
    combinations must each start from a clean cache, or they'd silently
    observe a stale instance from an earlier test."""
    get_github_client.cache_clear()


class _FakeGitHubClient(GitHubClient):
    """Test double: overrides `GitHubClient.__init__` (which otherwise
    builds a real `Github` from `Settings`) to accept an already-faked
    `Github` directly -- the real fetch/post/apply/close logic (inherited,
    not overridden) is what's actually under test."""

    def __init__(self, github: Github) -> None:
        self._github = github


def make_fake_issue(**overrides: Any) -> Any:
    """Returns `Any`, not `Issue`: callers need Mock-specific introspection
    (`.assert_called_once_with`/`.side_effect`) that a real `Issue`'s type
    stub doesn't expose -- the same deliberate `Any` exception AGENTS.md
    carves out for test-fixture helpers."""
    fake_user = create_autospec(NamedUser, instance=True, spec_set=True)
    fake_user.login = "octocat"

    fake_label = create_autospec(Label, instance=True, spec_set=True)
    fake_label.name = "bug"

    fake_comment = create_autospec(IssueComment, instance=True, spec_set=True)
    fake_comment.html_url = "https://github.com/octocat/Hello-World/issues/1#issuecomment-1"

    defaults: dict[str, Any] = {
        "number": 1,
        "title": "Found a bug",
        "body": "This is a bug report.",
        "user": fake_user,
        "author_association": "NONE",
        "labels": [fake_label],
        "created_at": datetime(2011, 4, 22, tzinfo=UTC),
        "html_url": "https://github.com/octocat/Hello-World/issues/1",
    }
    defaults.update(overrides)

    fake_issue = create_autospec(Issue, instance=True, spec_set=True)
    for attr, value in defaults.items():
        setattr(fake_issue, attr, value)
    fake_issue.create_comment.return_value = fake_comment
    return fake_issue


def make_fake_client(issue: Issue) -> Github:
    fake_repo = create_autospec(Repository, instance=True, spec_set=True)
    fake_repo.get_issue.return_value = issue

    fake_client = create_autospec(Github, instance=True, spec_set=True)
    fake_client.get_repo.return_value = fake_repo
    return fake_client


def make_client(issue: Issue) -> GitHubClient:
    return _FakeGitHubClient(make_fake_client(issue))


def test_fetch_issue_maps_core_fields() -> None:
    client = make_client(make_fake_issue())

    payload = client.fetch_issue("octocat/Hello-World", 1)

    assert payload.repo_full_name == "octocat/Hello-World"
    assert payload.issue_number == 1
    assert payload.title == "Found a bug"
    assert payload.body == "This is a bug report."
    assert payload.author == "octocat"
    assert payload.author_association == "NONE"
    assert payload.labels == ["bug"]
    assert payload.created_at == datetime(2011, 4, 22, tzinfo=UTC)
    assert payload.url == "https://github.com/octocat/Hello-World/issues/1"


def test_fetch_issue_sets_source_to_replay() -> None:
    client = make_client(make_fake_issue())

    payload = client.fetch_issue("octocat/Hello-World", 1)

    assert payload.source is IssueSource.REPLAY


def test_fetch_issue_leaves_installation_id_none() -> None:
    client = make_client(make_fake_issue())

    payload = client.fetch_issue("octocat/Hello-World", 1)

    assert payload.installation_id is None


def test_fetch_issue_coerces_none_body_to_empty_string() -> None:
    """GitHub's API can return `body: null`; IssuePayload.body is a required str."""
    client = make_client(make_fake_issue(body=None))

    payload = client.fetch_issue("octocat/Hello-World", 1)

    assert payload.body == ""


def test_fetch_issue_maps_multiple_labels_by_name() -> None:
    label_a = create_autospec(Label, instance=True, spec_set=True)
    label_a.name = "bug"
    label_b = create_autospec(Label, instance=True, spec_set=True)
    label_b.name = "help wanted"
    client = make_client(make_fake_issue(labels=[label_a, label_b]))

    payload = client.fetch_issue("octocat/Hello-World", 1)

    assert payload.labels == ["bug", "help wanted"]


def test_post_comment_creates_comment_and_returns_url() -> None:
    issue = make_fake_issue()
    client = make_client(issue)

    url = client.post_comment("octocat/Hello-World", 1, "Thanks for the report!")

    issue.create_comment.assert_called_once_with("Thanks for the report!")
    assert url == "https://github.com/octocat/Hello-World/issues/1#issuecomment-1"


def test_post_comment_propagates_github_exception() -> None:
    issue = make_fake_issue()
    issue.create_comment.side_effect = GithubException(500, {"message": "boom"}, None)
    client = make_client(issue)

    with pytest.raises(GithubException):
        client.post_comment("octocat/Hello-World", 1, "Thanks for the report!")


def test_apply_labels_adds_and_removes() -> None:
    issue = make_fake_issue()
    client = make_client(issue)

    client.apply_labels("octocat/Hello-World", 1, ["bug", "help wanted"], ["stale"])

    issue.add_to_labels.assert_called_once_with("bug", "help wanted")
    issue.remove_from_labels.assert_called_once_with("stale")


def test_apply_labels_skips_add_call_when_nothing_to_add() -> None:
    issue = make_fake_issue()
    client = make_client(issue)

    client.apply_labels("octocat/Hello-World", 1, [], ["stale"])

    issue.add_to_labels.assert_not_called()
    issue.remove_from_labels.assert_called_once_with("stale")


def test_apply_labels_propagates_github_exception() -> None:
    issue = make_fake_issue()
    issue.add_to_labels.side_effect = GithubException(500, {"message": "boom"}, None)
    client = make_client(issue)

    with pytest.raises(GithubException):
        client.apply_labels("octocat/Hello-World", 1, ["bug"], [])


def test_close_issue_posts_comment_then_closes() -> None:
    issue = make_fake_issue()
    client = make_client(issue)

    client.close_issue("octocat/Hello-World", 1, "Duplicate of #10.")

    issue.create_comment.assert_called_once_with("Duplicate of #10.")
    issue.edit.assert_called_once_with(state="closed")


def test_close_issue_without_comment_only_closes() -> None:
    issue = make_fake_issue()
    client = make_client(issue)

    client.close_issue("octocat/Hello-World", 1, None)

    issue.create_comment.assert_not_called()
    issue.edit.assert_called_once_with(state="closed")


def test_close_issue_propagates_github_exception() -> None:
    issue = make_fake_issue()
    issue.edit.side_effect = GithubException(500, {"message": "boom"}, None)
    client = make_client(issue)

    with pytest.raises(GithubException):
        client.close_issue("octocat/Hello-World", 1, None)


def test_get_github_client_anonymous_when_no_token_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.github_client.get_settings", lambda: Settings(github_token=None))

    client = get_github_client()

    assert client.raw.requester.auth is None


def test_get_github_client_authenticates_with_settings_github_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.github_client.get_settings",
        lambda: Settings(github_token=SecretStr("settings-token")),
    )

    client = get_github_client()

    auth = client.raw.requester.auth
    assert isinstance(auth, Auth.Token)
    assert auth.token == "settings-token"


def test_get_github_client_is_a_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.github_client.get_settings", lambda: Settings(github_token=None))

    first = get_github_client()
    second = get_github_client()

    assert first is second
