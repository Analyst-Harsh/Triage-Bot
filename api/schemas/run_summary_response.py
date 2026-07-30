from graph.schemas import RunStatus
from graph.schemas.base import StrictBaseModel


class RunSummaryResponse(StrictBaseModel):
    """Response body for `GET /runs/summary`: status counts only, not cost
    totals -- cost lives per-run inside the LangGraph checkpoint until (if)
    it gets aggregated onto `triage_runs` itself, and scanning every
    checkpoint on every dashboard load doesn't scale. `counts_by_status` is
    zero-filled for every `RunStatus` value, not just the ones present in
    the table, so a frontend never has to guard against a missing key."""

    counts_by_status: dict[RunStatus, int]
    total_runs: int
