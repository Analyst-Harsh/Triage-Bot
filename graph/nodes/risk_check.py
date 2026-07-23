from datetime import UTC, datetime
from typing import ClassVar

from structlog import get_logger

from graph.nodes.llm_node import LLMNode
from graph.nodes.node_names import NodeName
from graph.schemas import (
    ActionRiskAssessment,
    RiskAssessment,
    RiskJudgmentBatch,
    RiskLevel,
    RunStatus,
)
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from prompts.risk_check import build_risk_judgment_messages

log = get_logger(__name__)

# Ordering used to enforce the unsupported-claims floor: an LLM judgment can
# never be *downgraded* by the floor, only bumped up to it.
_RISK_ORDER: dict[RiskLevel, int] = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def _max_risk_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


class RiskCheckNode(LLMNode):
    """Tags every drafted action with its own risk level. `label` and
    `code_fix` are resolved by hardcoded policy (no judgment call, no LLM
    spend); `comment`/`close` actions are batched into a single LLM call,
    since deciding whether a given comment or close is "routine" vs.
    "substantive" is a genuine judgment call the other two aren't.
    """

    name: ClassVar[NodeName] = NodeName.RISK_CHECK
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="openai", model="gpt-5.4-nano", temperature=0.0),
        fallback=LLMEndpointConfig(provider="openai", model="gpt-5-nano", temperature=0.0),
    )

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        draft = state["draft"]
        if draft is None:
            raise ValueError("risk_check called before draft was set")

        results: dict[int, ActionRiskAssessment] = {}
        judged_indices: list[int] = []
        for index, drafted in enumerate(draft.actions):
            match drafted.action.action_type:
                case "label":
                    results[index] = ActionRiskAssessment(
                        level=RiskLevel.LOW,
                        risk_factors=[],
                        reasoning="Label changes are always low-risk by policy.",
                    )
                case "code_fix":
                    results[index] = ActionRiskAssessment(
                        level=RiskLevel.HIGH,
                        risk_factors=["automated code change"],
                        reasoning=(
                            "Code fixes always require human review by policy, "
                            "regardless of sandbox result."
                        ),
                    )
                case "comment" | "close":
                    judged_indices.append(index)

        cost_usd = 0.0
        if judged_indices:
            messages = build_risk_judgment_messages(
                draft, state["research_findings"], judged_indices
            )
            result = await self.call_structured(messages, RiskJudgmentBatch)
            cost_usd = result.estimated_cost_usd

            judgments_by_index = {j.action_index: j for j in result.parsed.judgments}
            floor = RiskLevel.MEDIUM if draft.unsupported_claims else RiskLevel.LOW
            for index in judged_indices:
                judgment = judgments_by_index.get(index)
                if judgment is None:
                    raise ValueError(
                        f"risk judgment batch omitted a verdict for action_index {index}"
                    )
                results[index] = ActionRiskAssessment(
                    level=_max_risk_level(judgment.level, floor),
                    risk_factors=judgment.risk_factors,
                    reasoning=judgment.reasoning,
                )

        risk_assessment = RiskAssessment(
            action_assessments=[results[i] for i in range(len(draft.actions))],
            assessed_at=datetime.now(UTC),
        )

        log.info(
            "risk_assessed",
            issue_number=state["issue"].issue_number,
            levels=[a.level.value for a in risk_assessment.action_assessments],
            llm_judged_count=len(judged_indices),
            estimated_cost_usd=cost_usd,
        )

        update: TriageStateUpdate = {
            "risk_assessment": risk_assessment,
            "status": RunStatus.RISK_CHECK,
        }
        if cost_usd > 0.0:
            update["run_meta"] = state["run_meta"].with_usage(cost_usd=cost_usd)
        return update
