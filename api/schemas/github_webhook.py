"""The GitHub `issues` webhook event payload, parsed just enough to build an
`IssuePayload` (api/routers/webhooks.py). Deliberately NOT `StrictBaseModel`:
a real GitHub webhook delivery carries dozens of fields this bot never reads
(sender, installation, changes, ...). `extra="forbid"` here would reject
every real delivery -- this parses an external, third-party-owned payload
shape we don't control, unlike every other schema in this codebase. The four
nested models below are kept in this one file deliberately: together they
describe one coherent external payload shape, not several unrelated
concerns.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GitHubWebhookUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    login: str


class GitHubWebhookLabel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str


class GitHubWebhookIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    number: int
    title: str
    body: str | None = None
    user: GitHubWebhookUser
    author_association: str | None = None
    labels: list[GitHubWebhookLabel] = []
    created_at: datetime
    html_url: str


class GitHubWebhookRepository(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: str


class GitHubIssuesEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: str
    issue: GitHubWebhookIssue
    repository: GitHubWebhookRepository
