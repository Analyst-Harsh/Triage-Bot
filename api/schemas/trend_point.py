from datetime import datetime

from graph.schemas import RunStatus
from graph.schemas.base import StrictBaseModel


class TrendPoint(StrictBaseModel):
    """One bucket of `GET /runs/summary`'s time series. `bucket_start` is
    `None` only for the single all-time bucket a request with no `period`
    degenerates to; otherwise it's the start of an `interval`-width window.
    `counts_by_status` is zero-filled for every `RunStatus` value, same
    convention `RunSummaryResponse` used before this endpoint grew buckets,
    so a frontend never has to guard against a missing key."""

    bucket_start: datetime | None
    counts_by_status: dict[RunStatus, int]
    run_count: int
    total_cost_usd: float
