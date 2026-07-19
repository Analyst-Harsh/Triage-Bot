from datetime import UTC, datetime
from typing import ClassVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from graph.nodes.agent_subgraph import AgentSubgraph
from graph.nodes.node_names import NodeName
from graph.schemas import (
    DraftedAction,
    DraftOutput,
    DraftProposal,
    GroundingCritique,
    RunStatus,
    ToolCallRecord,
)
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from llm.structured import call_structured
from prompts.drafter import (
    GROUNDING_CHECK_PROMPT,
    build_drafter_system_prompt,
    build_drafting_message,
    format_evidence_for_prompt,
    format_public_draft_text,
)

DRAFTER_MAX_TOOL_CALLS = 5


class DrafterSubgraph(AgentSubgraph[DraftProposal]):
    """Turns the Planner's classification + the Researcher's findings into a
    concrete, grounded proposed action (or set of actions). Built exactly
    like `ResearcherSubgraph` — `tools=[]` today, since drafting a
    comment/label/close action needs no tool calls; the future sandboxed
    code-fix path (propose diff -> run sandbox -> maybe retry) is a genuine
    tool-calling loop and lands as more tools passed into this same class,
    not a rewiring of the parent graph.

    `finalize()` also makes its own independent LLM call — the grounding
    self-check — after building the draft from `summary`. This is a
    genuinely separate pass from the one that produced `summary` (the
    evaluator-optimizer pattern the brief calls for: a model is a much
    weaker judge of its own claims in the same breath it wrote them), not a
    second field on the same structured-output call. `finalize()` only adds
    this call's own cost onto the `run_meta` it returns — `assemble_node`
    (inherited, unmodified) still owns accumulating the draft-generation
    cost (trajectory + summarize) and bumping `iteration_count`, exactly the
    same contract every `AgentSubgraph` subclass gets for free.
    """

    name: ClassVar[NodeName] = NodeName.DRAFTER
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="openai", model="gpt-4o-mini"),
        fallback=LLMEndpointConfig(provider="anthropic", model="claude-haiku-4-5-20251001"),
    )
    # Inert until the sandboxed code-fix path adds real tools -- `tools=[]`
    # today means this cap is unreachable. Left non-zero (rather than 0) so
    # `assemble_node`'s `cap_hit = len(tool_calls) >= max_tool_calls` doesn't
    # log a false "cap hit" on every run.
    max_tool_calls: ClassVar[int] = DRAFTER_MAX_TOOL_CALLS
    summary_schema: ClassVar[type[BaseModel]] = DraftProposal

    def system_prompt(self) -> str:
        return build_drafter_system_prompt([tool.name for tool in self._tools])

    def prepare(self, state: TriageState) -> list[BaseMessage] | None:
        planner_output = state["planner_output"]
        if planner_output is None:
            raise ValueError("DrafterSubgraph requires planner_output to be set")
        research_findings = state["research_findings"]
        if research_findings is None:
            raise ValueError("DrafterSubgraph requires research_findings to be set")
        return [build_drafting_message(state["issue"], planner_output, research_findings)]

    async def finalize(
        self,
        summary: DraftProposal | None,
        tool_calls: list[ToolCallRecord],  # noqa: ARG002
        state: TriageState,
    ) -> TriageStateUpdate:
        if summary is None:
            raise ValueError(
                "DrafterSubgraph.finalize() received summary=None -- prepare() never "
                "short-circuits, so this should be unreachable"
            )
        research_findings = state["research_findings"]
        if research_findings is None:
            raise ValueError("DrafterSubgraph.finalize() requires research_findings to be set")

        actions = [
            DraftedAction(action=item.action, rationale=item.rationale) for item in summary.actions
        ]

        # Only the text actually posted to GitHub is checked -- never
        # rationale/overall_rationale (internal reasoning, never posted, a
        # judgment call rather than a factual claim). `None` means no action
        # here produces any public-facing text (e.g. a label-only draft), so
        # there is nothing to fact-check -- skip the grounding-check LLM call
        # entirely rather than running it against rationale (see
        # `format_public_draft_text`'s docstring for the bug this avoids).
        public_draft_text = format_public_draft_text(actions)
        if public_draft_text is None:
            draft = DraftOutput(
                actions=actions,
                overall_rationale=summary.overall_rationale,
                unsupported_claims=[],
                drafted_at=datetime.now(UTC),
            )
            return TriageStateUpdate(draft=draft, status=RunStatus.DRAFTING)

        # Independent second LLM call: the grounding self-check. See class
        # docstring for why this must be a genuinely separate pass rather
        # than a second field on the call that produced `summary`.
        critique_messages = GROUNDING_CHECK_PROMPT.format_messages(
            draft_text=public_draft_text,
            evidence=format_evidence_for_prompt(research_findings.evidence),
        )
        critique_result = await call_structured(
            self._primary_model, self._fallback_model, critique_messages, GroundingCritique
        )

        draft = DraftOutput(
            actions=actions,
            overall_rationale=summary.overall_rationale,
            unsupported_claims=critique_result.parsed.unsupported_claims,
            drafted_at=datetime.now(UTC),
        )
        # Only this call's own cost is added here -- never replicate
        # assemble_node's trajectory/summarize accumulation or touch
        # iteration_count; assemble_node adds the draft-generation cost and
        # the iteration bump on top of whatever run_meta this method returns.
        updated_run_meta = state["run_meta"].model_copy(
            update={
                "estimated_cost_usd": state["run_meta"].estimated_cost_usd
                + critique_result.estimated_cost_usd
            }
        )
        return TriageStateUpdate(draft=draft, status=RunStatus.DRAFTING, run_meta=updated_run_meta)
