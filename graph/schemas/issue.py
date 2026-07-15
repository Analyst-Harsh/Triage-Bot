from datetime import datetime

from pydantic import BaseModel

from graph.schemas.enums import IssueSource


class IssuePayload(BaseModel):
    repo_full_name: str
    issue_number: int
    title: str
    body: str
    author: str
    author_association: str | None = None
    labels: list[str] = []
    created_at: datetime
    url: str
    source: IssueSource
    installation_id: int | None = None
