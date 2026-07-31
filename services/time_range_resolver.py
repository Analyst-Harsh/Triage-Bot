"""Converts a `TimeRangePeriod` query param into the concrete values the
persistence layer needs: `since()` for the WHERE-clause cutoff, `interval()`
for the bucket width `GET /runs/summary` groups its trend points by. Kept as
one class rather than two free functions because `/runs/summary` always
calls both together for the same `period`, constructing one
`TimeRangeResolver` instead of importing two unrelated functions.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

from graph.schemas import TimeRangePeriod

_SINCE_DELTAS: dict[TimeRangePeriod, timedelta] = {
    TimeRangePeriod.ONE_HOUR: timedelta(hours=1),
    TimeRangePeriod.TWENTY_FOUR_HOURS: timedelta(hours=24),
    TimeRangePeriod.SEVEN_DAYS: timedelta(days=7),
    TimeRangePeriod.THIRTY_DAYS: timedelta(days=30),
}

_INTERVALS: dict[TimeRangePeriod, Literal["minute", "hour", "day"]] = {
    TimeRangePeriod.ONE_HOUR: "minute",
    TimeRangePeriod.TWENTY_FOUR_HOURS: "hour",
    TimeRangePeriod.SEVEN_DAYS: "day",
    TimeRangePeriod.THIRTY_DAYS: "day",
}


class TimeRangeResolver:
    def since(self, period: TimeRangePeriod | None) -> datetime | None:
        """The earliest `started_at` a run must have to fall in `period`,
        anchored to "now" at call time. `None` in, `None` out -- the
        unfiltered case."""
        if period is None:
            return None
        return datetime.now(UTC) - _SINCE_DELTAS[period]

    def interval(self, period: TimeRangePeriod | None) -> Literal["minute", "hour", "day"] | None:
        """The `date_trunc` bucket width `/runs/summary` groups `period`'s
        trend points by. `None` in, `None` out -- a request with no `period`
        gets a single all-time bucket, not a bucketed series."""
        if period is None:
            return None
        return _INTERVALS[period]
