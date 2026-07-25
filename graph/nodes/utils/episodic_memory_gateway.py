from uuid import UUID

import structlog

from config.settings import get_settings
from graph.schemas import (
    DraftedAction,
    EpisodicMemoryHit,
    IssuePayload,
    PlannerOutput,
    PostResults,
    RiskAssessment,
    RunStatus,
)
from utils.episodic_memory_store import BaseEpisodicMemoryStore, EpisodicMemoryUnavailableError

log = structlog.get_logger(__name__)


class EpisodicMemoryGateway:
    """Shared episodic-memory access for `PlannerNode`/`AutoPostNode`/
    `ApprovalQueueNode`: wraps both `BaseEpisodicMemoryStore.find_similar`
    and `.save_episode` with the one deliberate narrow catch every caller
    needs -- a memory-store failure must never fail a run outright, whether
    that means classifying without historical context or failing to
    retroactively record a run whose GitHub actions already resolved."""

    def __init__(self, memory_store: BaseEpisodicMemoryStore) -> None:
        self._memory_store = memory_store

    async def find_similar(self, issue: IssuePayload) -> list[EpisodicMemoryHit]:
        settings = get_settings()
        try:
            return await self._memory_store.find_similar(
                issue, top_k=settings.episodic_memory_top_k
            )
        except EpisodicMemoryUnavailableError as exc:
            log.warning("episodic_memory_unavailable", error=str(exc))
            return []

    async def write(
        self,
        *,
        run_id: UUID,
        issue: IssuePayload,
        planner_output: PlannerOutput,
        draft_actions: list[DraftedAction],
        risk_assessment: RiskAssessment,
        post_results: PostResults,
        outcome: RunStatus,
    ) -> None:
        try:
            await self._memory_store.save_episode(
                run_id=run_id,
                issue=issue,
                planner_output=planner_output,
                draft_actions=draft_actions,
                risk_assessment=risk_assessment,
                post_results=post_results,
                outcome=outcome,
            )
        except EpisodicMemoryUnavailableError as exc:
            log.warning("episodic_memory_unavailable", error=str(exc))
