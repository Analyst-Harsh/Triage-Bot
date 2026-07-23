from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from graph.schemas import RunError, RunMeta


def make_run_meta(**overrides: Any) -> RunMeta:
    defaults: dict[str, Any] = {
        "run_id": uuid4(),
        "thread_id": "octo/repo#42",
        "trace_id": "langfuse-trace-abc",
        "started_at": datetime.now(UTC),
        "max_iterations": 15,
        "max_cost_usd": 2.5,
    }
    defaults.update(overrides)
    return RunMeta(**defaults)


def test_construction_with_defaults() -> None:
    meta = make_run_meta()
    assert meta.iteration_count == 0
    assert meta.tool_calls_made == 0
    assert meta.estimated_cost_usd == 0.0
    assert meta.errors == []
    assert meta.dry_run is True


def test_dry_run_can_be_disabled() -> None:
    meta = make_run_meta(dry_run=False)
    assert meta.dry_run is False


def test_errors_list() -> None:
    meta = make_run_meta(
        errors=[
            RunError(
                node_name="researcher",
                error_message="Tavily API timed out",
                occurred_at=datetime.now(UTC),
            )
        ]
    )
    assert len(meta.errors) == 1
    assert meta.errors[0].node_name == "researcher"


def test_json_round_trip() -> None:
    meta = make_run_meta()
    restored = RunMeta.model_validate_json(meta.model_dump_json())
    assert restored == meta


def test_with_usage_accumulates_cost_tool_calls_and_iterations() -> None:
    meta = make_run_meta(estimated_cost_usd=1.0, tool_calls_made=2, iteration_count=3)

    updated = meta.with_usage(cost_usd=0.5, tool_calls=4, iterations=1)

    assert updated.estimated_cost_usd == 1.5
    assert updated.tool_calls_made == 6
    assert updated.iteration_count == 4
    # Original is untouched (model_copy semantics).
    assert meta.estimated_cost_usd == 1.0


def test_with_usage_defaults_to_no_change() -> None:
    meta = make_run_meta(estimated_cost_usd=2.0, tool_calls_made=1, iteration_count=1)

    updated = meta.with_usage()

    assert updated == meta
