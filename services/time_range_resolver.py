"""Converts a `TimeRangePeriod` query param into the concrete values the
persistence layer needs. Kept as its own class (rather than a free
function) because a second method -- `interval()`, resolving a period to
the bucket width a later time-series endpoint groups by -- is a planned
sibling that will always be called alongside `since()` for that endpoint;
grouping them here now means that endpoint constructs one `TimeRangeResolver`
instead of importing two unrelated functions.
"""

from datetime import UTC, datetime, timedelta

from graph.schemas import TimeRangePeriod

_SINCE_DELTAS: dict[TimeRangePeriod, timedelta] = {
    TimeRangePeriod.ONE_HOUR: timedelta(hours=1),
    TimeRangePeriod.TWENTY_FOUR_HOURS: timedelta(hours=24),
    TimeRangePeriod.SEVEN_DAYS: timedelta(days=7),
    TimeRangePeriod.THIRTY_DAYS: timedelta(days=30),
}


class TimeRangeResolver:
    def since(self, period: TimeRangePeriod | None) -> datetime | None:
        """The earliest `started_at` a run must have to fall in `period`,
        anchored to "now" at call time. `None` in, `None` out -- the
        unfiltered case."""
        if period is None:
            return None
        return datetime.now(UTC) - _SINCE_DELTAS[period]
