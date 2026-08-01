"""Collection-level `/runs` routes -- list and status-summary. Kept apart
from `api/routers/runs.py` (which addresses one run by
`{owner}/{repo}/{issue_number}`) since the two routers have genuinely
different path shapes and can't share one `APIRouter` prefix."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.dependencies import RunServiceDep, require_bearer_token
from api.schemas import RunListResponse, RunSummaryResponse
from graph.schemas import IssueSource, RunStatus, TimeRangePeriod

router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_bearer_token)])


@router.get("", response_model=RunListResponse)
async def list_runs(
    service: RunServiceDep,
    status: Annotated[list[RunStatus] | None, Query()] = None,
    repo_full_name: Annotated[str | None, Query()] = None,
    source: Annotated[IssueSource | None, Query()] = None,
    period: Annotated[TimeRangePeriod | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunListResponse:
    return await service.list_runs(
        page=page,
        page_size=page_size,
        statuses=status,
        repo_full_name=repo_full_name,
        source=source,
        period=period,
    )


@router.get("/summary", response_model=RunSummaryResponse)
async def get_runs_summary(
    service: RunServiceDep,
    repo_full_name: Annotated[str | None, Query()] = None,
    period: Annotated[TimeRangePeriod | None, Query()] = None,
) -> RunSummaryResponse:
    return await service.get_status_summary(repo_full_name=repo_full_name, period=period)
