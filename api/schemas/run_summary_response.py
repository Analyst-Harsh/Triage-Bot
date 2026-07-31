from typing import Literal

from api.schemas.trend_point import TrendPoint
from graph.schemas import TimeRangePeriod
from graph.schemas.base import StrictBaseModel


class RunSummaryResponse(StrictBaseModel):
    """Response body for `GET /runs/summary` -- the one endpoint for both
    current totals and trend data, no separate `/runs/trend`. `points` is
    always at least one element: a request with no `period` degenerates to
    a single all-time bucket (`interval=None`), which is exactly today's
    flat totals wrapped in a one-element list instead of returned bare."""

    period: TimeRangePeriod | None
    interval: Literal["minute", "hour", "day"] | None
    points: list[TrendPoint]
