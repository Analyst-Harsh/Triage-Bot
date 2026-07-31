"""Tests for `observability.trace_reader.build_trace_summary` against
hand-built observation-dict fixtures using the real camelCase field names
Langfuse's SDK actually returns (confirmed against the installed package's
`ObservationV2` model -- see `observability/trace_reader.py`'s own
docstring) -- not a live Langfuse trace, which this environment has no
credentials to reach."""

from datetime import UTC, datetime

from pydantic import JsonValue

from observability.trace_reader import build_trace_summary


def _raw_observation(**overrides: JsonValue) -> dict[str, JsonValue]:
    defaults: dict[str, JsonValue] = {
        "id": "obs-1",
        "parentObservationId": None,
        "name": "triage_run",
        "type": "SPAN",
        "startTime": "2024-01-01T00:00:00Z",
        "endTime": "2024-01-01T00:00:05Z",
        "latency": 5.0,
        "totalCost": 0.01,
        "level": "DEFAULT",
    }
    defaults.update(overrides)
    return defaults


def test_build_trace_summary_maps_camel_case_fields() -> None:
    summary = build_trace_summary(
        "deadbeef", [_raw_observation()], langfuse_host="https://cloud.langfuse.com"
    )

    assert summary.trace_id == "deadbeef"
    assert summary.langfuse_url == "https://cloud.langfuse.com/trace/deadbeef"
    assert len(summary.observations) == 1
    observation = summary.observations[0]
    assert observation.observation_id == "obs-1"
    assert observation.parent_observation_id is None
    assert observation.name == "triage_run"
    assert observation.observation_type == "SPAN"
    assert observation.start_time == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert observation.end_time == datetime(2024, 1, 1, 0, 0, 5, tzinfo=UTC)
    assert observation.latency_seconds == 5.0
    assert observation.cost_usd == 0.01
    assert observation.level == "DEFAULT"


def test_build_trace_summary_renders_unrecognized_observation_types_verbatim() -> None:
    """This pipeline's own traces contain `CHAIN` observations (the
    top-level LangGraph invocation, each `AgentSubgraph` node) alongside
    Langfuse's own `SPAN`/`GENERATION`/`EVENT` -- `observation_type` must
    render whatever string comes back, not reject an unrecognized one."""
    summary = build_trace_summary(
        "deadbeef",
        [_raw_observation(type="CHAIN")],
        langfuse_host="https://cloud.langfuse.com",
    )
    assert summary.observations[0].observation_type == "CHAIN"


def test_build_trace_summary_handles_missing_optional_fields() -> None:
    raw = _raw_observation(
        parentObservationId=None, name=None, endTime=None, latency=None, totalCost=None, level=None
    )
    summary = build_trace_summary("deadbeef", [raw], langfuse_host="https://cloud.langfuse.com")

    observation = summary.observations[0]
    assert observation.end_time is None
    assert observation.latency_seconds is None
    assert observation.cost_usd is None
    assert observation.level is None


def test_build_trace_summary_total_latency_is_wall_clock_span_not_a_sum() -> None:
    """A parent span's latency already includes its children's time --
    summing every observation's own latency would double-count nested
    work. The total is the observed wall-clock span instead: latest
    end_time (or start_time, absent one) minus earliest start_time."""
    observations: list[JsonValue] = [
        _raw_observation(
            id="root", startTime="2024-01-01T00:00:00Z", endTime="2024-01-01T00:00:10Z"
        ),
        _raw_observation(
            id="child", startTime="2024-01-01T00:00:02Z", endTime="2024-01-01T00:00:04Z"
        ),
    ]
    summary = build_trace_summary(
        "deadbeef", observations, langfuse_host="https://cloud.langfuse.com"
    )
    assert summary.total_latency_seconds == 10.0


def test_build_trace_summary_total_latency_falls_back_to_start_time_without_an_end_time() -> None:
    observations: list[JsonValue] = [
        _raw_observation(id="a", startTime="2024-01-01T00:00:00Z", endTime=None),
        _raw_observation(id="b", startTime="2024-01-01T00:00:03Z", endTime=None),
    ]
    summary = build_trace_summary(
        "deadbeef", observations, langfuse_host="https://cloud.langfuse.com"
    )
    assert summary.total_latency_seconds == 3.0


def test_build_trace_summary_total_cost_sums_every_observation() -> None:
    """Unlike wall-clock time, per-observation cost isn't nested -- a
    parent span's cost doesn't double-count a child generation's spend --
    so summing every observation's cost is the correct total."""
    observations: list[JsonValue] = [
        _raw_observation(id="a", totalCost=0.01),
        _raw_observation(id="b", totalCost=0.02),
        _raw_observation(id="c", totalCost=None),
    ]
    summary = build_trace_summary(
        "deadbeef", observations, langfuse_host="https://cloud.langfuse.com"
    )
    assert summary.total_cost_usd == 0.03


def test_build_trace_summary_handles_empty_observations() -> None:
    summary = build_trace_summary("deadbeef", [], langfuse_host="https://cloud.langfuse.com")

    assert summary.observations == []
    assert summary.total_latency_seconds is None
    assert summary.total_cost_usd is None
