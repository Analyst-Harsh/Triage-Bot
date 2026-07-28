from datetime import UTC, datetime
from typing import ClassVar

import structlog

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.schemas import (
    ActionPostResult,
    ActionRiskAssessment,
    CloseAction,
    DraftedAction,
    DraftOutput,
    PostOutcome,
    PostResults,
    RiskAssessment,
    RiskLevel,
    RunStatus,
)
from graph.state import TriageState, TriageStateUpdate

log = structlog.get_logger(__name__)

_SPAM_CLOSE_COMMENT = (
    "This issue has been automatically closed as spam or abuse by triage bot. "
    "If this was a mistake, please reopen or contact a maintainer."
)


class SpamCloseNode(TriageNode):
    """Handles issues the Planner classified as `SPAM_OR_ABUSE`
    (see `route_after_planner`, `graph/nodes/routing.py`): builds a
    one-action `close` draft directly -- no Researcher/Drafter LLM call
    needed, since the action is fully determined by the Planner's own
    classification -- and hardcodes its risk to `RiskLevel.HIGH` by policy,
    exactly like `RiskCheckNode` does for `label`/`code_fix` (see that
    node's docstring): a spam call is a Planner judgment that can be wrong,
    so closing a real user's issue on the strength of it always requires a
    human to confirm first, never an automatic post.

    Skips `RiskCheckNode`/`AutoPostNode` entirely and routes straight to
    `ApprovalQueueNode` (see `graph/builder.py`), which is the single place
    that actually posts the close (on approval) and writes the completed
    episode to memory -- this node does neither itself, unlike the old
    `SpamRejectedNode` it replaces.
    """

    name: ClassVar[NodeName] = NodeName.SPAM_CLOSE

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        planner_output = state["planner_output"]
        if planner_output is None:
            raise ValueError("spam_close called before planner_output was set")

        issue = state["issue"]
        log.info(
            "issue_flagged_as_spam",
            issue_number=issue.issue_number,
            reasoning=planner_output.reasoning,
        )

        draft = DraftOutput(
            actions=[
                DraftedAction(
                    action=CloseAction(
                        reason="spam or abuse",
                        close_comment=_SPAM_CLOSE_COMMENT,
                    ),
                    rationale=planner_output.reasoning,
                )
            ],
            overall_rationale=planner_output.reasoning,
            unsupported_claims=[],
            drafted_at=datetime.now(UTC),
        )
        risk_assessment = RiskAssessment(
            action_assessments=[
                ActionRiskAssessment(
                    level=RiskLevel.HIGH,
                    risk_factors=["spam_or_abuse close always requires human review by policy"],
                    reasoning=(
                        "Closing an issue on the strength of a spam/abuse classification "
                        "always requires human review by policy, regardless of the "
                        "Planner's confidence -- a false positive here silently closes a "
                        "real user's issue."
                    ),
                )
            ],
            assessed_at=datetime.now(UTC),
        )
        post_results = PostResults(
            action_results=[ActionPostResult(outcome=PostOutcome.QUEUED)],
            evaluated_at=datetime.now(UTC),
        )

        return TriageStateUpdate(
            draft=draft,
            risk_assessment=risk_assessment,
            post_results=post_results,
            status=RunStatus.PENDING_APPROVAL,
        )
