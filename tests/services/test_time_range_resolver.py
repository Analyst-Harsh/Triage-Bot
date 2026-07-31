from datetime import UTC, datetime, timedelta

import pytest

import services.time_range_resolver as time_range_resolver_module
from graph.schemas import TimeRangePeriod
from services.time_range_resolver import TimeRangeResolver


def test_since_returns_none_when_period_is_none() -> None:
    assert TimeRangeResolver().since(None) is None


@pytest.mark.parametrize(
    ("period", "expected_delta"),
    [
        (TimeRangePeriod.ONE_HOUR, timedelta(hours=1)),
        (TimeRangePeriod.TWENTY_FOUR_HOURS, timedelta(hours=24)),
        (TimeRangePeriod.SEVEN_DAYS, timedelta(days=7)),
        (TimeRangePeriod.THIRTY_DAYS, timedelta(days=30)),
    ],
)
def test_since_subtracts_the_period_delta_from_now(
    monkeypatch: pytest.MonkeyPatch, period: TimeRangePeriod, expected_delta: timedelta
) -> None:
    frozen_now = datetime(2026, 1, 1, tzinfo=UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # noqa: ARG003 -- must match datetime.now's signature
            return frozen_now

    monkeypatch.setattr(time_range_resolver_module, "datetime", _FrozenDatetime)

    result = TimeRangeResolver().since(period)

    assert result == frozen_now - expected_delta


def test_interval_returns_none_when_period_is_none() -> None:
    assert TimeRangeResolver().interval(None) is None


@pytest.mark.parametrize(
    ("period", "expected_interval"),
    [
        (TimeRangePeriod.ONE_HOUR, "minute"),
        (TimeRangePeriod.TWENTY_FOUR_HOURS, "hour"),
        (TimeRangePeriod.SEVEN_DAYS, "day"),
        (TimeRangePeriod.THIRTY_DAYS, "day"),
    ],
)
def test_interval_maps_period_to_bucket_width(
    period: TimeRangePeriod, expected_interval: str
) -> None:
    assert TimeRangeResolver().interval(period) == expected_interval
