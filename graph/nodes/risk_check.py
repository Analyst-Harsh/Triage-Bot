from datetime import UTC, datetime
from typing import ClassVar

from structlog import get_logger

from graph.nodes.llm_node import LLMNode
from graph.nodes.node_names import NodeName
from graph.nodes.utils.injection_pattern_scanner import InjectionPatternScanner, extract_urls
from graph.schemas import (
    ActionRiskAssessment,
    Evidence,
    RiskAssessment,
    RiskJudgmentBatch,
    RiskLevel,
    RunStatus,
)
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from prompts.drafter import public_facing_text
from prompts.risk_check import build_risk_judgment_messages

log = get_logger(__name__)

# Ordering used to enforce the unsupported-claims floor: an LLM judgment can
# never be *downgraded* by the floor, only bumped up to it.
_RISK_ORDER: dict[RiskLevel, int] = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def _max_risk_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def _evidence_urls(evidence: list[Evidence]) -> set[str]:
    urls: set[str] = set()
    for item in evidence:
        urls |= extract_urls(item.reference)
        urls |= extract_urls(item.snippet)
    return urls


class RiskCheckNode(LLMNode):
    """Tags every drafted action with its own risk level. `label` and
    `code_fix` are resolved by hardcoded policy (no judgment call, no LLM
    spend); `comment`/`close` actions are batched into a single LLM call,
    since deciding whether a given comment or close is "routine" vs.
    "substantive" is a genuine judgment call the other two aren't.

    After every action has a level, `InjectionPatternScanner` runs a second,
    deterministic pass over every action still resolved to `RiskLevel.LOW`
    (the only level that skips human review): a hit there bumps that one
    action to `MEDIUM`, exactly like the `unsupported_claims` floor below --
    it never lowers a level, only raises one already-LOW action into human
    review. See that scanner's own docstring for why this lives here rather
    than in a dedicated node, and why it's deterministic rather than a
    second LLM call.
    """

    name: ClassVar[NodeName] = NodeName.RISK_CHECK
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="openai", model="gpt-5.4-nano", temperature=0.0),
        fallback=LLMEndpointConfig(provider="openai", model="gpt-5-nano", temperature=0.0),
    )

    def __init__(self) -> None:
        super().__init__()
        self._scanner = InjectionPatternScanner()

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
        cache_read_tokens = 0
        cache_creation_tokens = 0
        if judged_indices:
            messages = build_risk_judgment_messages(
                draft, state["research_findings"], judged_indices
            )
            result = await self.call_structured(messages, RiskJudgmentBatch)
            cost_usd = result.estimated_cost_usd
            cache_read_tokens = result.cache_read_tokens
            cache_creation_tokens = result.cache_creation_tokens

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

        research_findings = state["research_findings"]
        evidence_urls = _evidence_urls(research_findings.evidence if research_findings else [])
        issue = state["issue"]
        # Scans every action with public-facing text, not just LOW ones --
        # a hit on an already-MEDIUM/HIGH action changes nothing, but is
        # still logged (see injection_hits below) as tuning data for the
        # phrase list's real-world false-positive/negative rate.
        injection_hits: dict[int, list[str]] = {}
        for index, drafted in enumerate(draft.actions):
            text = public_facing_text(drafted.action)
            if text is None:
                continue
            signals = self._scanner.scan(
                text, issue_title=issue.title, issue_body=issue.body, evidence_urls=evidence_urls
            )
            if not signals:
                continue
            injection_hits[index] = signals
            if results[index].level == RiskLevel.LOW:
                existing = results[index]
                results[index] = ActionRiskAssessment(
                    level=RiskLevel.MEDIUM,
                    risk_factors=[*existing.risk_factors, *signals],
                    reasoning=f"{existing.reasoning} Bumped to MEDIUM: {'; '.join(signals)}.",
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
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            injection_scanner_hits=injection_hits,
        )

        update: TriageStateUpdate = {
            "risk_assessment": risk_assessment,
            "status": RunStatus.RISK_CHECK,
        }
        if cost_usd > 0.0 or cache_read_tokens > 0 or cache_creation_tokens > 0:
            update["run_meta"] = state["run_meta"].with_usage(
                cost_usd=cost_usd,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
            )
        return update
