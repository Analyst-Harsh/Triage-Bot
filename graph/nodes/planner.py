from datetime import UTC, datetime
from typing import ClassVar

from structlog import get_logger

from graph.nodes.llm_node import LLMNode
from graph.nodes.node_names import NodeName
from graph.nodes.utils.episodic_memory_gateway import EpisodicMemoryGateway
from graph.schemas import PlannerClassification, PlannerOutput, RunStatus
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from prompts.planner import (
    PLANNER_PROMPT,
    format_episodic_context_for_prompt,
    format_issue_for_prompt,
)
from utils.episodic_memory_store import BaseEpisodicMemoryStore

log = get_logger(__name__)


class PlannerNode(LLMNode):
    """Reads the raw issue and classifies it via an LLM call, informed by
    similar past issues pulled from episodic memory."""

    name: ClassVar[NodeName] = NodeName.PLANNER
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="openai", model="gpt-5.4-nano", temperature=0.0),
        fallback=LLMEndpointConfig(provider="openai", model="gpt-5-nano", temperature=0.0),
    )

    def __init__(self, memory_store: BaseEpisodicMemoryStore) -> None:
        super().__init__()
        self._memory_gateway = EpisodicMemoryGateway(memory_store)

    async def execute(self, state: TriageState) -> TriageStateUpdate:
        issue = state["issue"]
        hits = await self._memory_gateway.find_similar(issue)

        messages = PLANNER_PROMPT.format_messages(
            issue_text=format_issue_for_prompt(issue),
            episodic_context_text=format_episodic_context_for_prompt(hits),
        )
        result = await self.call_structured(messages, PlannerClassification)
        output = PlannerOutput(**result.parsed.model_dump(), classified_at=datetime.now(UTC))

        cache_hit_ratio = (
            result.cache_read_tokens / result.total_input_tokens
            if result.total_input_tokens
            else 0.0
        )
        log.info(
            "planner_classified",
            issue_number=issue.issue_number,
            issue_type=output.issue_type.value,
            classification_confidence=output.classification_confidence,
            investigation_plan=output.investigation_plan,
            reasoning=output.reasoning,
            classified_at=output.classified_at.isoformat(),
            estimated_cost_usd=result.estimated_cost_usd,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
            cache_hit_ratio=cache_hit_ratio,
            episodic_hits=len(hits),
        )
        return TriageStateUpdate(
            planner_output=output,
            episodic_context=hits,
            status=RunStatus.PLANNING,
            run_meta=state["run_meta"].with_usage(
                cost_usd=result.estimated_cost_usd,
                cache_read_tokens=result.cache_read_tokens,
                cache_creation_tokens=result.cache_creation_tokens,
            ),
        )
