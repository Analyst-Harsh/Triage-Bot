from datetime import UTC, datetime

import pytest

from graph.nodes.node_names import NodeName
from graph.nodes.routing import route_after_auto_post, route_after_planner
from graph.schemas import (
    ActionPostResult,
    IssuePayload,
    IssueSource,
    IssueType,
    PlannerOutput,
    PostOutcome,
    PostResults,
)
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


def _planner_output(**overrides: object) -> PlannerOutput:
    defaults: dict[str, object] = {
        "issue_type": IssueType.BUG,
        "classification_confidence": 0.9,
        "investigation_plan": ["look into it"],
        "reasoning": "Looks like a real bug.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)  # type: ignore[arg-type]


def test_route_after_planner_routes_spam_to_spam_rejected() -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    state["planner_output"] = _planner_output(issue_type=IssueType.SPAM_OR_ABUSE)

    assert route_after_planner(state) == NodeName.SPAM_REJECTED


@pytest.mark.parametrize(
    "issue_type",
    [
        IssueType.BUG,
        IssueType.FEATURE_REQUEST,
        IssueType.QUESTION,
        IssueType.DOCUMENTATION,
        IssueType.DUPLICATE,
        IssueType.NEEDS_MORE_INFO,
        IssueType.OTHER,
    ],
)
def test_route_after_planner_routes_every_other_issue_type_to_researcher(
    issue_type: IssueType,
) -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    state["planner_output"] = _planner_output(issue_type=issue_type)

    assert route_after_planner(state) == NodeName.RESEARCHER


def test_route_after_planner_raises_without_planner_output() -> None:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)

    with pytest.raises(ValueError, match="planner_output"):
        route_after_planner(state)


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
