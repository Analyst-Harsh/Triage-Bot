"""GitHub API boundary: client construction and issue fetching/mapping.

Houses the first slice of the "replay" pipeline (see AGENTS.md) — pulling a
single historical issue and mapping it onto our own `IssuePayload` contract.
Named `github_client.py`, not `github.py`, so this submodule's dotted path
(`api.github_client`) is never visually confused with the installed `github`
(PyGithub) top-level package imported below.
"""

import os

from github import Auth, Github

from graph.schemas import IssuePayload, IssueSource


def build_github_client(token: str | None = None) -> Github:
    """Anonymous by default (unauthenticated, GitHub's public 60 req/hr
    limit). Pass `token` explicitly, or set `GITHUB_TOKEN` in the
    environment, to authenticate as a PAT instead — an explicit `token`
    argument wins over the environment variable.
    """
    resolved_token = token or os.environ.get("GITHUB_TOKEN")
    if resolved_token:
        return Github(auth=Auth.Token(resolved_token))
    return Github()


def fetch_issue(client: Github, repo_full_name: str, issue_number: int) -> IssuePayload:
    """Fetch one historical issue via PyGithub and map it onto `IssuePayload`.

    `source` is always `IssueSource.REPLAY`: this pulls a historical issue
    by number, not a live webhook delivery. `installation_id` stays `None`
    — it only applies to GitHub App auth, not the PAT/anonymous auth this
    client supports.
    """
    repo = client.get_repo(repo_full_name)
    issue = repo.get_issue(issue_number)
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
