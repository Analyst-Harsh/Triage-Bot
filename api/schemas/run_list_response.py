from api.schemas.run_summary import RunSummary
from graph.schemas.base import StrictBaseModel


class RunListResponse(StrictBaseModel):
    """Page of `GET /runs`. `total`/`total_pages` are computed from the same
    filters as `items` (see `TriageRunRepository._list_filters`), so a
    frontend pager built from this response can never disagree with the
    rows it's paging over."""

    items: list[RunSummary]
    total: int
    page: int
    page_size: int
    total_pages: int
