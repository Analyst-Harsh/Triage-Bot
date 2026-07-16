"""Tests for `api.github_client`: GitHub client construction and the
PyGithub Issue -> IssuePayload mapping.

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
from github import Auth, Github
from github.Issue import Issue
from github.Label import Label
from github.NamedUser import NamedUser
from github.Repository import Repository

from api.github_client import build_github_client, fetch_issue
from graph.schemas import IssueSource


def make_fake_issue(**overrides: Any) -> Issue:
    fake_user = create_autospec(NamedUser, instance=True, spec_set=True)
    fake_user.login = "octocat"

    fake_label = create_autospec(Label, instance=True, spec_set=True)
    fake_label.name = "bug"

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
    return fake_issue


def make_fake_client(issue: Issue) -> Github:
    fake_repo = create_autospec(Repository, instance=True, spec_set=True)
    fake_repo.get_issue.return_value = issue

    fake_client = create_autospec(Github, instance=True, spec_set=True)
    fake_client.get_repo.return_value = fake_repo
    return fake_client


def test_fetch_issue_maps_core_fields() -> None:
    client = make_fake_client(make_fake_issue())

    payload = fetch_issue(client, "octocat/Hello-World", 1)

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
    client = make_fake_client(make_fake_issue())

    payload = fetch_issue(client, "octocat/Hello-World", 1)

    assert payload.source is IssueSource.REPLAY


def test_fetch_issue_leaves_installation_id_none() -> None:
    client = make_fake_client(make_fake_issue())

    payload = fetch_issue(client, "octocat/Hello-World", 1)

    assert payload.installation_id is None


def test_fetch_issue_coerces_none_body_to_empty_string() -> None:
    """GitHub's API can return `body: null`; IssuePayload.body is a required str."""
    client = make_fake_client(make_fake_issue(body=None))

    payload = fetch_issue(client, "octocat/Hello-World", 1)

    assert payload.body == ""


def test_fetch_issue_maps_multiple_labels_by_name() -> None:
    label_a = create_autospec(Label, instance=True, spec_set=True)
    label_a.name = "bug"
    label_b = create_autospec(Label, instance=True, spec_set=True)
    label_b.name = "help wanted"
    client = make_fake_client(make_fake_issue(labels=[label_a, label_b]))

    payload = fetch_issue(client, "octocat/Hello-World", 1)

    assert payload.labels == ["bug", "help wanted"]


def test_build_github_client_anonymous_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    client = build_github_client()

    assert client.requester.auth is None


def test_build_github_client_uses_github_token_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    client = build_github_client()

    auth = client.requester.auth
    assert isinstance(auth, Auth.Token)
    assert auth.token == "env-token"


def test_build_github_client_explicit_token_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    client = build_github_client(token="explicit-token")

    auth = client.requester.auth
    assert isinstance(auth, Auth.Token)
    assert auth.token == "explicit-token"
