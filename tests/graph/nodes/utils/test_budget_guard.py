import pytest

from graph.errors import BudgetExceededError
from graph.nodes.utils.budget_guard import check_budget
from tests.graph.schemas.test_run_meta import make_run_meta


def test_check_budget_passes_when_well_under_both_ceilings() -> None:
    run_meta = make_run_meta(
        estimated_cost_usd=0.1, max_cost_usd=1.0, iteration_count=1, max_iterations=10
    )

    check_budget(run_meta, node_name="planner")  # must not raise


def test_check_budget_raises_when_cost_at_ceiling() -> None:
    run_meta = make_run_meta(estimated_cost_usd=1.0, max_cost_usd=1.0)

    with pytest.raises(BudgetExceededError) as exc_info:
        check_budget(run_meta, node_name="planner")

    assert exc_info.value.node_name == "planner"
    assert exc_info.value.dimension == "cost_usd"
    assert exc_info.value.current == 1.0
    assert exc_info.value.limit == 1.0


def test_check_budget_raises_when_cost_over_ceiling() -> None:
    run_meta = make_run_meta(estimated_cost_usd=1.5, max_cost_usd=1.0)

    with pytest.raises(BudgetExceededError) as exc_info:
        check_budget(run_meta, node_name="drafter")

    assert exc_info.value.dimension == "cost_usd"


def test_check_budget_raises_when_iterations_at_ceiling() -> None:
    run_meta = make_run_meta(
        estimated_cost_usd=0.0, max_cost_usd=1.0, iteration_count=10, max_iterations=10
    )

    with pytest.raises(BudgetExceededError) as exc_info:
        check_budget(run_meta, node_name="researcher")

    assert exc_info.value.dimension == "iterations"
    assert exc_info.value.current == 10
    assert exc_info.value.limit == 10


def test_check_budget_checks_cost_before_iterations() -> None:
    """Both ceilings are simultaneously breached -- the cost dimension is
    reported, matching `check_budget`'s own top-to-bottom check order."""
    run_meta = make_run_meta(
        estimated_cost_usd=2.0, max_cost_usd=1.0, iteration_count=10, max_iterations=10
    )

    with pytest.raises(BudgetExceededError) as exc_info:
        check_budget(run_meta, node_name="risk_check")

    assert exc_info.value.dimension == "cost_usd"
