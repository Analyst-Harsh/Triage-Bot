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
    via GitHub; anything riskier is left for `ApprovalQueueNode`. `code_fix`
    actions are never LOW risk by `RiskCheckNode` policy, so this node never
    routes one to the `ActionExecutor`.
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
        dry_run = state["run_meta"].dry_run

        results: list[ActionPostResult] = []
        for drafted, assessment in zip(
            draft.actions, risk_assessment.action_assessments, strict=True
        ):
            if assessment.level != RiskLevel.LOW:
                results.append(ActionPostResult(outcome=PostOutcome.QUEUED))
                continue

            results.append(
                await self._action_executor.execute(drafted.action, issue, dry_run=dry_run)
            )

        post_results = PostResults(action_results=results, evaluated_at=datetime.now(UTC))
        log.info(
            "auto_post_completed",
            issue_number=issue.issue_number,
            posted=sum(1 for r in results if r.outcome == PostOutcome.POSTED),
            failed=sum(1 for r in results if r.outcome == PostOutcome.FAILED),
            queued=sum(1 for r in results if r.outcome == PostOutcome.QUEUED),
            dry_run=dry_run,
        )
        return TriageStateUpdate(post_results=post_results, status=RunStatus.AUTO_POSTED)
