"""GitHub API boundary: a single `GitHubClient` wrapping PyGithub for both
reading (the replay pipeline's issue fetch) and writing (AutoPostNode's
comment/label/close actions).

Houses the first slice of the "replay" pipeline (see AGENTS.md) — pulling a
single historical issue and mapping it onto our own `IssuePayload` contract
— plus the write-side GitHub calls AutoPostNode makes for low-risk actions.
Named `github_client.py`, not `github.py`, so this submodule's dotted path
(`utils.github_client`) is never visually confused with the installed
`github` (PyGithub) top-level package imported below.
"""

from functools import lru_cache

from github import Auth, Github, GithubException
from github.InputGitTreeElement import InputGitTreeElement
from github.Issue import Issue
from github.Repository import Repository

from config.settings import get_settings
from graph.schemas import IssuePayload, IssueSource
from utils.diff_applier import AppliedFile, DiffApplier, DiffApplyError


class GitHubClient:
    """OO wrapper around PyGithub's `Github` -- the single boundary through
    which the app reads and writes GitHub issues. Builds its own `Github`
    from `Settings` (see `_build_raw_client`) -- real production
    construction, not something a caller hands in. Constructed once as a
    process-wide singleton via `get_github_client()` below, not
    re-instantiated per call site. Tests that need a fake subclass this
    class and override `__init__` (see `tests/utils/test_github_client.py`'s
    `_FakeGitHubClient`) rather than this constructor taking an injectable
    parameter.
    """

    def __init__(self) -> None:
        self._github = _build_raw_client()
        self._diff_applier = DiffApplier()

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

    def create_pull_request_from_diff(
        self,
        repo_full_name: str,
        *,
        diff: str,
        target_files: list[str],
        base_commit_sha: str,
        base_branch: str,
        branch_name: str,
        title: str,
        body: str,
    ) -> str:
        """Applies `diff` strictly against `base_commit_sha` (via
        `self._diff_applier`) and opens a pull request from the result.
        Returns the created PR's URL.

        `target_files` is the full set of paths `diff` touches (adds,
        modifies, or deletes) -- each is fetched at `base_commit_sha` first;
        a 404 means the diff adds that path, so its base content is `None`.

        No blanket try/except, matching every other write method here:
        `GithubException` (any GitHub call) and `DiffApplyError` (the diff
        doesn't apply cleanly, or a fetched file isn't valid UTF-8)
        propagate to the caller (`ActionExecutor`).
        """
        repo = self._github.get_repo(repo_full_name)
        base_files = {
            path: self._fetch_base_content(repo, path, base_commit_sha) for path in target_files
        }
        applied_files = self._diff_applier.apply(diff, base_files)

        base_commit = repo.get_git_commit(base_commit_sha)
        tree_elements = [_tree_element(applied) for applied in applied_files]
        tree = repo.create_git_tree(tree_elements, base_tree=base_commit.tree)
        commit = repo.create_git_commit(message=title, tree=tree, parents=[base_commit])
        repo.create_git_ref(f"refs/heads/{branch_name}", commit.sha)
        pull_request = repo.create_pull(base=base_branch, head=branch_name, title=title, body=body)
        return pull_request.html_url

    def _fetch_base_content(self, repo: Repository, path: str, ref: str) -> str | None:
        try:
            content_file = repo.get_contents(path, ref=ref)
        except GithubException as exc:
            if exc.status == 404:
                return None
            raise
        if isinstance(content_file, list):
            raise DiffApplyError(f"{path!r} is a directory, not a file, at ref {ref!r}")
        try:
            return content_file.decoded_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DiffApplyError(f"{path!r} is not valid UTF-8 at ref {ref!r}") from exc

    def _get_issue(self, repo_full_name: str, issue_number: int) -> Issue:
        return self._github.get_repo(repo_full_name).get_issue(issue_number)


def _tree_element(applied: AppliedFile) -> InputGitTreeElement:
    """`content=` is passed inline rather than pre-creating a blob via
    `create_git_blob` -- the Git Data API's tree endpoint accepts raw
    (non-base64) content directly and creates the blob itself, so this
    skips one API round trip per changed file. `sha=None` is the Git Data
    API's own way of marking a tree entry for deletion."""
    if applied.content is None:
        return InputGitTreeElement(applied.path, "100644", "blob", sha=None)
    return InputGitTreeElement(applied.path, "100644", "blob", content=applied.content)


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
