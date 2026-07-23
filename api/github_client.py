"""GitHub API boundary: a single `GitHubClient` wrapping PyGithub for both
reading (the replay pipeline's issue fetch) and writing (AutoPostNode's
comment/label/close actions).

Houses the first slice of the "replay" pipeline (see AGENTS.md) — pulling a
single historical issue and mapping it onto our own `IssuePayload` contract
— plus the write-side GitHub calls AutoPostNode makes for low-risk actions.
Named `github_client.py`, not `github.py`, so this submodule's dotted path
(`api.github_client`) is never visually confused with the installed `github`
(PyGithub) top-level package imported below.
"""

from functools import lru_cache

from github import Auth, Github
from github.Issue import Issue

from config.settings import get_settings
from graph.schemas import IssuePayload, IssueSource


class GitHubClient:
    """OO wrapper around PyGithub's `Github` -- the single boundary through
    which the app reads and writes GitHub issues. Builds its own `Github`
    from `Settings` (see `_build_raw_client`) -- real production
    construction, not something a caller hands in. Constructed once as a
    process-wide singleton via `get_github_client()` below, not
    re-instantiated per call site. Tests that need a fake subclass this
    class and override `__init__` (see `tests/api/test_github_client.py`'s
    `_FakeGitHubClient`) rather than this constructor taking an injectable
    parameter.
    """

    def __init__(self) -> None:
        self._github = _build_raw_client()

    @property
    def raw(self) -> Github:
        """The underlying PyGithub client, for call sites (e.g.
        `tools.sandbox.sandbox_toolset`) that need the raw `Github` object
        rather than this wrapper."""
        return self._github

    def fetch_issue(self, repo_full_name: str, issue_number: int) -> IssuePayload:
        """Fetch one historical issue via PyGithub and map it onto `IssuePayload`.

        `source` is always `IssueSource.REPLAY`: this pulls a historical issue
        by number, not a live webhook delivery. `installation_id` stays `None`
        — it only applies to GitHub App auth, not the PAT/anonymous auth this
        client supports.
        """
        issue = self._get_issue(repo_full_name, issue_number)
        return IssuePayload(
            repo_full_name=repo_full_name,
            issue_number=issue.number,
            title=issue.title,
            body=issue.body or "",  # GitHub's API returns `null` for issues
            # with no description; IssuePayload.body is a required str.
            author=issue.user.login,
            author_association=issue.author_association,
            labels=[label.name for label in issue.labels],
            created_at=issue.created_at,
            url=issue.html_url,
            source=IssueSource.REPLAY,
            installation_id=None,
        )

    def post_comment(self, repo_full_name: str, issue_number: int, body: str) -> str:
        """Posts a comment on the issue, returning its URL."""
        issue = self._get_issue(repo_full_name, issue_number)
        comment = issue.create_comment(body)
        return comment.html_url

    def apply_labels(
        self,
        repo_full_name: str,
        issue_number: int,
        labels_to_add: list[str],
        labels_to_remove: list[str],
    ) -> None:
        issue = self._get_issue(repo_full_name, issue_number)
        if labels_to_add:
            issue.add_to_labels(*labels_to_add)
        for label in labels_to_remove:
            issue.remove_from_labels(label)

    def close_issue(
        self, repo_full_name: str, issue_number: int, close_comment: str | None
    ) -> None:
        """Closes the issue, posting `close_comment` first if given. Doesn't
        attempt to map the drafted close reason onto GitHub's own
        `state_reason` enum (`completed`/`not_planned`) -- left unset,
        GitHub defaults it sensibly."""
        issue = self._get_issue(repo_full_name, issue_number)
        if close_comment:
            issue.create_comment(close_comment)
        issue.edit(state="closed")

    def _get_issue(self, repo_full_name: str, issue_number: int) -> Issue:
        return self._github.get_repo(repo_full_name).get_issue(issue_number)


def _build_raw_client() -> Github:
    """Anonymous by default (unauthenticated, GitHub's public 60 req/hr
    limit). Authenticates as a PAT when `Settings.github_token` is set --
    the only source of truth for this secret, never `os.environ` directly.
    """
    token = get_settings().github_token
    if token is not None:
        return Github(auth=Auth.Token(token.get_secret_value()))
    return Github()


@lru_cache
def get_github_client() -> GitHubClient:
    """Process-wide singleton (mirrors `config.settings.get_settings()`).
    Tests that vary `Settings.github_token` must call
    `get_github_client.cache_clear()` first.
    """
    return GitHubClient()
