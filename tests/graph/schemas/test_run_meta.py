from datetime import UTC, datetime
from uuid import uuid4

from graph.schemas import RunError, RunMeta


def make_run_meta(**overrides) -> RunMeta:
    defaults = dict(
        run_id=uuid4(),
        thread_id="octo/repo#42",
        trace_id="langfuse-trace-abc",
        started_at=datetime.now(UTC),
        max_iterations=15,
        max_cost_usd=2.5,
    )
    defaults.update(overrides)
    return RunMeta(**defaults)


def test_construction_with_defaults():
    meta = make_run_meta()
    assert meta.iteration_count == 0
    assert meta.tool_calls_made == 0
    assert meta.estimated_cost_usd == 0.0
    assert meta.errors == []


def test_errors_list():
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


def test_json_round_trip():
    meta = make_run_meta()
    restored = RunMeta.model_validate_json(meta.model_dump_json())
    assert restored == meta
