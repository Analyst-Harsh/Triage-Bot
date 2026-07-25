from datetime import UTC, datetime
from typing import ClassVar

import structlog

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.nodes.utils.action_executor import ActionExecutor
from graph.schemas import ActionPostResult, PostOutcome, PostResults, RiskLevel, RunStatus
from graph.state import TriageState, TriageStateUpdate

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
    """

    name: ClassVar[NodeName] = NodeName.AUTO_POST

    def __init__(self) -> None:
        self._action_executor: ActionExecutor = ActionExecutor()

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
        log.info(
            "auto_post_completed",
            issue_number=issue.issue_number,
            posted=sum(1 for r in results if r.outcome == PostOutcome.POSTED),
            failed=sum(1 for r in results if r.outcome == PostOutcome.FAILED),
            queued=sum(1 for r in results if r.outcome == PostOutcome.QUEUED),
            dry_run=dry_run,
        )
        status = RunStatus.PENDING_APPROVAL if any_queued else RunStatus.AUTO_POSTED
        return TriageStateUpdate(post_results=post_results, status=status)
