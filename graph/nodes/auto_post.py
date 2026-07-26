from datetime import UTC, datetime
from typing import ClassVar

import structlog

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.nodes.utils.action_executor import ActionExecutor
from graph.nodes.utils.episodic_memory_gateway import EpisodicMemoryGateway
from graph.schemas import ActionPostResult, PostOutcome, PostResults, RiskLevel, RunStatus
from graph.state import TriageState, TriageStateUpdate
from utils.episodic_memory_store import BaseEpisodicMemoryStore

log = structlog.get_logger(__name__)


class AutoPostNode(TriageNode):
    """Applies every LOW-risk drafted action for real (comment/label/close)
    via GitHub; anything riskier is left queued for `ApprovalQueueNode`.
    `code_fix` actions are never LOW risk by `RiskCheckNode` policy, so this
    node never routes one to the `ActionExecutor` -- posting a code fix (as
    a pull request) only ever happens after human approval.

    Status reflects whether anything was left queued: `AUTO_POSTED` when
    every action was LOW risk (the run is finished), `PENDING_APPROVAL`
    when at least one action needs a human decision (the run continues to
    `approval_queue` -- see `route_after_auto_post` in `graph/nodes/routing.py`).

    Only writes to episodic memory when `AUTO_POSTED`: a `PENDING_APPROVAL`
    run isn't finished yet, and `ApprovalQueueNode` writes the complete
    episode once it resolves -- the two write paths are mutually exclusive
    by construction (see `route_after_auto_post`), never both firing for
    the same run.
    """

    name: ClassVar[NodeName] = NodeName.AUTO_POST

    def __init__(self, memory_store: BaseEpisodicMemoryStore) -> None:
        self._action_executor: ActionExecutor = ActionExecutor()
        self._memory_gateway = EpisodicMemoryGateway(memory_store)

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        draft = state["draft"]
        risk_assessment = state["risk_assessment"]
        if draft is None or risk_assessment is None:
            raise ValueError("auto_post called before draft/risk_assessment was set")

        issue = state["issue"]
        run_meta = state["run_meta"]
        dry_run = run_meta.dry_run

        results: list[ActionPostResult] = []
        for drafted, assessment in zip(
            draft.actions, risk_assessment.action_assessments, strict=True
        ):
            if assessment.level != RiskLevel.LOW:
                results.append(ActionPostResult(outcome=PostOutcome.QUEUED))
                continue

            results.append(
                await self._action_executor.execute(
                    drafted, issue, dry_run=dry_run, run_id=run_meta.run_id
                )
            )

        post_results = PostResults(action_results=results, evaluated_at=datetime.now(UTC))
        any_queued = any(r.outcome == PostOutcome.QUEUED for r in results)
        failed = [r for r in results if r.outcome == PostOutcome.FAILED]
        log.info(
            "auto_post_completed",
            issue_number=issue.issue_number,
            posted=sum(1 for r in results if r.outcome == PostOutcome.POSTED),
            failed=len(failed),
            queued=sum(1 for r in results if r.outcome == PostOutcome.QUEUED),
            dry_run=dry_run,
        )
        status = RunStatus.PENDING_APPROVAL if any_queued else RunStatus.AUTO_POSTED
        if failed:
            # `status` still records the routing decision (see class
            # docstring / docs/agent/architecture-conventions.md) -- this
            # is the signal that actually reaches RunError/the node's
            # Langfuse span (TriageNode.__call__) when a real GitHub post
            # failed, which `status` alone never surfaced.
            run_meta = run_meta.with_error(
                node_name=self.name,
                error_message=(
                    f"{len(failed)} action(s) failed to post: "
                    + "; ".join(r.detail or "" for r in failed)
                ),
            )

        if status == RunStatus.AUTO_POSTED and not dry_run:
            planner_output = state["planner_output"]
            if planner_output is None:
                raise ValueError("auto_post called before planner_output was set")
            await self._memory_gateway.write(
                run_id=run_meta.run_id,
                issue=issue,
                planner_output=planner_output,
                draft_actions=draft.actions,
                risk_assessment=risk_assessment,
                post_results=post_results,
                outcome=status,
            )

        return TriageStateUpdate(post_results=post_results, status=status, run_meta=run_meta)
