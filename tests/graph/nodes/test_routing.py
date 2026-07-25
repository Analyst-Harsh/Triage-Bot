from datetime import UTC, datetime

import pytest

from graph.nodes.node_names import NodeName
from graph.nodes.routing import route_after_auto_post
from graph.schemas import ActionPostResult, IssuePayload, IssueSource, PostOutcome, PostResults
from graph.state import create_initial_state


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


def _post_results(outcomes: list[PostOutcome]) -> PostResults:
    return PostResults(
        action_results=[ActionPostResult(outcome=outcome) for outcome in outcomes],
        evaluated_at=datetime.now(UTC),
    )


def test_route_after_auto_post_returns_end_when_nothing_queued() -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    state["post_results"] = _post_results([PostOutcome.POSTED])

    assert route_after_auto_post(state) == "__end__"


def test_route_after_auto_post_routes_to_approval_queue_when_queued() -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    state["post_results"] = _post_results([PostOutcome.POSTED, PostOutcome.QUEUED])

    assert route_after_auto_post(state) == NodeName.APPROVAL_QUEUE


def test_route_after_auto_post_raises_without_post_results() -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)

    with pytest.raises(ValueError, match="post_results"):
        route_after_auto_post(state)
