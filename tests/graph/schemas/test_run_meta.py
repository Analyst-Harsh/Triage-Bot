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
    assert meta.cache_read_tokens == 0
    assert meta.cache_creation_tokens == 0
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
    meta = make_run_meta(
        estimated_cost_usd=2.0,
        tool_calls_made=1,
        iteration_count=1,
        cache_read_tokens=10,
        cache_creation_tokens=2,
    )

    updated = meta.with_usage()

    assert updated == meta
    assert updated.cache_read_tokens == 10
    assert updated.cache_creation_tokens == 2


def test_with_usage_accumulates_cache_tokens() -> None:
    meta = make_run_meta(cache_read_tokens=100, cache_creation_tokens=10)

    updated = meta.with_usage(cache_read_tokens=50, cache_creation_tokens=5)

    assert updated.cache_read_tokens == 150
    assert updated.cache_creation_tokens == 15
    # Original is untouched (model_copy semantics).
    assert meta.cache_read_tokens == 100


def test_json_round_trip_with_cache_tokens() -> None:
    meta = make_run_meta(cache_read_tokens=7, cache_creation_tokens=3)
    restored = RunMeta.model_validate_json(meta.model_dump_json())
    assert restored == meta


def test_deserializes_without_cache_fields_for_backward_compatibility() -> None:
    """An old checkpoint written before cache_read_tokens/cache_creation_tokens
    existed must still deserialize -- both fields default to 0."""
    payload = make_run_meta().model_dump(mode="json")
    del payload["cache_read_tokens"]
    del payload["cache_creation_tokens"]

    restored = RunMeta.model_validate(payload)

    assert restored.cache_read_tokens == 0
    assert restored.cache_creation_tokens == 0


def test_with_error_appends_a_run_error() -> None:
    meta = make_run_meta()

    updated = meta.with_error(node_name="auto_post", error_message="GitHub API timed out")

    assert len(updated.errors) == 1
    assert updated.errors[0].node_name == "auto_post"
    assert updated.errors[0].error_message == "GitHub API timed out"
    # Original is untouched (model_copy semantics).
    assert meta.errors == []


def test_with_error_preserves_existing_errors() -> None:
    meta = make_run_meta(
        errors=[
            RunError(
                node_name="researcher",
                error_message="Tavily API timed out",
                occurred_at=datetime.now(UTC),
            )
        ]
    )

    updated = meta.with_error(node_name="auto_post", error_message="GitHub API timed out")

    assert len(updated.errors) == 2
    assert updated.errors[0].node_name == "researcher"
    assert updated.errors[1].node_name == "auto_post"
