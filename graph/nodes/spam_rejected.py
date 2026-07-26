from typing import ClassVar

import structlog

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.nodes.utils.episodic_memory_gateway import EpisodicMemoryGateway
from graph.schemas import RunStatus
from graph.state import TriageState, TriageStateUpdate
from utils.episodic_memory_store import BaseEpisodicMemoryStore

log = structlog.get_logger(__name__)


class SpamRejectedNode(TriageNode):
    """Terminal node for issues the Planner classified as `SPAM_OR_ABUSE`
    (see `route_after_planner`, `graph/nodes/routing.py`) -- a graceful
    outcome, not a system failure: sets `status=REJECTED` and ends the run
    without ever reaching Researcher/Drafter/RiskCheck/AutoPost.

    Still writes to episodic memory (draft_actions=[], risk_assessment=None,
    post_results=None) so the "every outcome logged" invariant holds and a
    future Planner retrieval can learn from past spam classifications --
    same dry_run gating as `AutoPostNode`/`ApprovalQueueNode`, and the same
    narrow-catch-on-store-failure contract via `EpisodicMemoryGateway`.
    """

    name: ClassVar[NodeName] = NodeName.SPAM_REJECTED

    def __init__(self, memory_store: BaseEpisodicMemoryStore) -> None:
        self._memory_gateway = EpisodicMemoryGateway(memory_store)

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        planner_output = state["planner_output"]
        if planner_output is None:
            raise ValueError("spam_rejected called before planner_output was set")

        issue = state["issue"]
        run_meta = state["run_meta"]
        log.info(
            "issue_rejected_as_spam",
            issue_number=issue.issue_number,
            reasoning=planner_output.reasoning,
        )

        if not run_meta.dry_run:
            await self._memory_gateway.write(
                run_id=run_meta.run_id,
                issue=issue,
                planner_output=planner_output,
                draft_actions=[],
                risk_assessment=None,
                post_results=None,
                outcome=RunStatus.REJECTED,
            )

        return TriageStateUpdate(status=RunStatus.REJECTED)
