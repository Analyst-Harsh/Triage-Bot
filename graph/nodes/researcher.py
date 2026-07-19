from datetime import UTC, datetime
from typing import ClassVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from graph.nodes.agent_subgraph import AgentSubgraph
from graph.nodes.node_names import NodeName
from graph.schemas import ResearchFindings, ResearchSummary, RunStatus, ToolCallRecord
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from prompts.researcher import build_investigation_message, build_researcher_system_prompt

RESEARCHER_MAX_TOOL_CALLS = 5


class ResearcherSubgraph(AgentSubgraph[ResearchSummary]):
    """Investigates the issue via whatever tools are available (DocMind,
    GitHub, web search), driven by the Planner's `investigation_plan` —
    the model chooses which tool to call and when, no hardcoded order.

    Trajectory scoping: this subgraph's `messages` channel is private (see
    `AgentSubgraph`/`AgentLoopState`) — it never touches top-level
    `TriageState`, so it coexists with any number of other tool-calling
    nodes (e.g. a future Drafter code-fix loop) with zero ambiguity. The
    raw trajectory is observable via this subgraph's own namespaced
    checkpoints and OTel/Langfuse traces, joinable by `run_id`; the typed
    distillation nodes downstream actually consume is `ResearchFindings`.
    """

    name: ClassVar[NodeName] = NodeName.RESEARCHER
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="anthropic", model="claude-sonnet-5"),
        fallback=LLMEndpointConfig(provider="openai", model="gpt-4o"),
    )
    max_tool_calls: ClassVar[int] = RESEARCHER_MAX_TOOL_CALLS
    # Typed as the base's `type[BaseModel]`, not `type[ResearchSummary]`:
    # `ClassVar` can't be parameterized by a type variable (the class's own
    # `SummaryT`), so a narrower override would violate pyright strict's
    # invariant-ClassVar check. `finalize()`'s signature is where subclasses
    # actually get `ResearchSummary`-typed access (see `_assemble_node`'s
    # cast in agent_subgraph.py).
    summary_schema: ClassVar[type[BaseModel]] = ResearchSummary

    def system_prompt(self) -> str:
        return build_researcher_system_prompt([tool.name for tool in self._tools])

    def prepare(self, state: TriageState) -> list[BaseMessage] | None:
        planner_output = state["planner_output"]
        if planner_output is None:
            # The graph always runs Planner -> Researcher, so this should
            # never happen in practice; `TriageState` types it optional only
            # because it's `None` before the Planner runs. Fail loudly
            # rather than silently treating a wiring bug as "no plan".
            raise ValueError("ResearcherSubgraph requires planner_output to be set")
        if not planner_output.investigation_plan:
            return None
        return [build_investigation_message(state["issue"], planner_output)]

    # `state` is unused here; the base class's finalize() signature requires
    # it for subclasses that do need it (renaming breaks strict override
    # typing, see base.py's precedent for this same pattern).
    def finalize(
        self,
        summary: ResearchSummary | None,
        tool_calls: list[ToolCallRecord],
        state: TriageState,  # noqa: ARG002
    ) -> TriageStateUpdate:
        gaps: list[str] = []
        tools_used = sorted({call.tool_name for call in tool_calls})

        if summary is None:
            findings = ResearchFindings(
                summary="No investigation was warranted for this issue.",
                confidence=1.0,
                researched_at=datetime.now(UTC),
            )
            return TriageStateUpdate(research_findings=findings, status=RunStatus.RESEARCHING)

        gaps = list(summary.gaps)
        if len(tool_calls) >= self.max_tool_calls:
            gaps.append(
                f"Stopped after hitting the {self.max_tool_calls}-tool-call research budget."
            )
        if self._settings.docmind_mcp_command is None:
            gaps.append("DocMind (docs/codebase index) was not available this run.")

        findings = ResearchFindings(
            summary=summary.summary,
            evidence=summary.evidence,
            focus_addressed=summary.focus_addressed,
            gaps=gaps,
            confidence=summary.confidence,
            tool_calls=tool_calls,
            tools_used=tools_used,
            researched_at=datetime.now(UTC),
        )
        return TriageStateUpdate(research_findings=findings, status=RunStatus.RESEARCHING)
