from datetime import UTC, datetime

import pytest

from graph.schemas import IssuePayload, IssueSource
from graph.state import TriageState, create_initial_state


def make_issue() -> IssuePayload:
    return IssuePayload(
        repo_full_name="octo/repo",
        issue_number=42,
        title="Crash on startup",
        body="App crashes with a NoneType error.",
        author="octocat",
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/42",
        source=IssueSource.WEBHOOK,
    )


@pytest.fixture
def triage_state() -> TriageState:
    return create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
