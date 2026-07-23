from datetime import UTC, datetime
from typing import ClassVar

from structlog import get_logger

from graph.nodes.llm_node import LLMNode
from graph.nodes.node_names import NodeName
from graph.schemas import PlannerClassification, PlannerOutput, RunStatus
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from prompts.planner import PLANNER_PROMPT, format_issue_for_prompt

log = get_logger(__name__)


class PlannerNode(LLMNode):
    """Reads the raw issue and classifies it via an LLM call."""

    name: ClassVar[NodeName] = NodeName.PLANNER
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="openai", model="gpt-5.4-nano", temperature=0.0),
        fallback=LLMEndpointConfig(provider="openai", model="gpt-5-nano", temperature=0.0),
    )

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        messages = PLANNER_PROMPT.format_messages(
            issue_text=format_issue_for_prompt(state["issue"])
        )
        result = await self.call_structured(messages, PlannerClassification)
        output = PlannerOutput(**result.parsed.model_dump(), classified_at=datetime.now(UTC))

        run_meta = state["run_meta"]
        new_cost = run_meta.estimated_cost_usd + result.estimated_cost_usd

        log.info(
            "planner_classified",
            issue_number=state["issue"].issue_number,
            issue_type=output.issue_type.value,
            classification_confidence=output.classification_confidence,
            investigation_plan=output.investigation_plan,
            reasoning=output.reasoning,
            classified_at=output.classified_at.isoformat(),
            estimated_cost_usd=result.estimated_cost_usd,
        )
        return TriageStateUpdate(
            planner_output=output,
            status=RunStatus.PLANNING,
            run_meta=run_meta.model_copy(update={"estimated_cost_usd": new_cost}),
        )
