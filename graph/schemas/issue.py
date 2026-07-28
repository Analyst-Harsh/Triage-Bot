from datetime import datetime

from pydantic import Field

from graph.schemas.base import StrictBaseModel
from graph.schemas.enums import IssueSource


class IssuePayload(StrictBaseModel):
    repo_full_name: str
    issue_number: int
    title: str
    body: str
    author: str
    author_association: str | None = None
    labels: list[str] = Field(default_factory=list[str])
    created_at: datetime
    url: str
    source: IssueSource
    installation_id: int | None = None
