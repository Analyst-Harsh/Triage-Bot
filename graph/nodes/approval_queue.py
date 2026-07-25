from datetime import UTC, datetime
from typing import ClassVar

import structlog
from langgraph.types import interrupt

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.nodes.utils.action_executor import ActionExecutor
from graph.nodes.utils.approval_request_builder import ApprovalRequestBuilder
from graph.schemas import ActionPostResult, ApprovalDecision, PostOutcome, PostResults, RunStatus
from graph.state import TriageState, TriageStateUpdate

log = structlog.get_logger(__name__)


class ApprovalQueueNode(TriageNode):
    """Pauses the run for human review of every queued (non-LOW-risk)
    drafted action, then posts whichever ones are approved.

    Uses LangGraph's `interrupt()`: the first execution raises here (the
    graph checkpoints and control returns to the caller with the
    `ApprovalRequest` payload); resuming with `Command(resume=...)`
    re-executes this node from the top, and `interrupt()` returns the
    resume value instead of raising. Everything above the `interrupt()`
    call is pure reads/validation -- no GitHub call, no state mutation --
    so re-running it on resume is harmless.

    Only reached when `route_after_auto_post` (see `graph/nodes/routing.py`)
    finds at least one `PostOutcome.QUEUED` result; `execute()` raises if
    that invariant is somehow violated.
    """

    name: ClassVar[NodeName] = NodeName.APPROVAL_QUEUE

    def __init__(self) -> None:
        self._action_executor: ActionExecutor = ActionExecutor()
        self._request_builder: ApprovalRequestBuilder = ApprovalRequestBuilder()

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        draft = state["draft"]
        risk_assessment = state["risk_assessment"]
        post_results = state["post_results"]
        if draft is None or risk_assessment is None or post_results is None:
            raise ValueError(
                "approval_queue called before draft/risk_assessment/post_results was set"
            )

        queued_indices = [
            index
            for index, result in enumerate(post_results.action_results)
            if result.outcome == PostOutcome.QUEUED
        ]
        if not queued_indices:
            raise ValueError("approval_queue called with no queued actions to approve")

        issue = state["issue"]
        run_meta = state["run_meta"]
        request = self._request_builder.build(
            issue, draft, risk_assessment, run_meta, queued_indices
        )

        raw_decision = interrupt(request.model_dump(mode="json"))
        decision = _validate_decision(raw_decision, queued_indices)

        results = list(post_results.action_results)
        any_approved = False
        for action_decision in decision.decisions:
            index = action_decision.index
            if not action_decision.approved:
                results[index] = ActionPostResult(
                    outcome=PostOutcome.REJECTED, detail=action_decision.note
                )
                continue

            any_approved = True
            results[index] = await self._action_executor.execute(
                draft.actions[index], issue, dry_run=run_meta.dry_run, run_id=run_meta.run_id
            )

        updated_post_results = PostResults(action_results=results, evaluated_at=datetime.now(UTC))
        log.info(
            "approval_queue_resolved",
            issue_number=issue.issue_number,
            approved=sum(1 for d in decision.decisions if d.approved),
            rejected=sum(1 for d in decision.decisions if not d.approved),
            posted=sum(1 for r in results if r.outcome == PostOutcome.POSTED),
            failed=sum(1 for r in results if r.outcome == PostOutcome.FAILED),
            dry_run=run_meta.dry_run,
        )
        status = RunStatus.APPROVED_AND_POSTED if any_approved else RunStatus.REJECTED
        return TriageStateUpdate(post_results=updated_post_results, status=status)


def _validate_decision(raw: object, queued_indices: list[int]) -> ApprovalDecision:
    """The resume value crosses a trust boundary -- supplied by whatever
    external surface resumes the graph, not produced internally -- so it's
    validated with `ApprovalDecision`'s own `extra="forbid"`, then checked
    here against the exact set of indices this request asked about (no
    missing, no extra, no duplicates). A mismatch raises `ValueError`,
    which the graph-wide error handler turns into `status=FAILED`: a
    deliberate tradeoff until a real approval surface validates before
    ever resuming (see docs/agent/architecture-conventions.md)."""
    decision = ApprovalDecision.model_validate(raw)
    decided_indices = [d.index for d in decision.decisions]
    if len(decided_indices) != len(set(decided_indices)):
        raise ValueError(f"approval decision contains duplicate indices: {decided_indices}")
    if set(decided_indices) != set(queued_indices):
        raise ValueError(
            f"approval decision indices {sorted(decided_indices)} do not match "
            f"queued indices {sorted(queued_indices)}"
        )
    return decision
