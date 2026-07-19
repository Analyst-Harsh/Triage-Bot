from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool, tool

from config.settings import Settings
from graph.nodes.agent_subgraph import AgentLoopState
from graph.nodes.researcher import ResearcherSubgraph
from graph.schemas import IssueType, PlannerOutput, ResearchSummary, ToolCallRecord
from graph.state import TriageState, create_initial_state
from tests.graph.nodes.conftest import make_fake_chat_model, make_issue


def make_planner_output(**overrides: object) -> PlannerOutput:
    defaults: dict[str, object] = {
        "issue_type": IssueType.BUG,
        "classification_confidence": 0.9,
        "investigation_plan": ["search codebase for NoneType"],
        "reasoning": "Traceback matches a known startup failure pattern.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)  # type: ignore[arg-type]


def make_state(planner_output: PlannerOutput | None) -> TriageState:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    state["planner_output"] = planner_output
    return state


class _FakeResearcherSubgraph(ResearcherSubgraph):
    """Test double: overrides `AgentSubgraph.__init__` to accept fake models
    and settings directly, same pattern as `_FakePlannerNode`."""

    def __init__(
        self,
        tools: list[BaseTool],
        primary_model: BaseChatModel,
        fallback_model: BaseChatModel,
        settings: Settings,
    ) -> None:
        self._tools = tools
        self._settings = settings
        self._primary_model = primary_model
        self._fallback_model = fallback_model


def make_researcher(
    tools: list[BaseTool] | None = None,
    settings: Settings | None = None,
    summary: ResearchSummary | None = None,
) -> _FakeResearcherSubgraph:
    primary = make_fake_chat_model(model_name="claude-sonnet-5", parsed_result=summary)
    fallback = make_fake_chat_model(model_name="gpt-4o")
    return _FakeResearcherSubgraph(
        tools or [], primary, fallback, settings or Settings(docmind_mcp_command=None)
    )


def test_prepare_returns_none_when_investigation_plan_is_empty() -> None:
    node = make_researcher()
    state = make_state(make_planner_output(investigation_plan=[]))

    result = node.prepare(state)

    assert result is None


def test_prepare_returns_investigation_message_with_plan_items() -> None:
    node = make_researcher()
    plan = ["search codebase for NoneType", "check startup sequence"]
    state = make_state(make_planner_output(investigation_plan=plan))

    result = node.prepare(state)

    assert result is not None
    assert len(result) == 1
    assert isinstance(result[0], HumanMessage)
    content = str(result[0].content)
    for item in plan:
        assert item in content


def test_prepare_raises_when_planner_output_missing() -> None:
    node = make_researcher()
    state = make_state(None)

    with pytest.raises(ValueError, match="planner_output"):
        node.prepare(state)


def test_finalize_with_none_summary_returns_minimal_findings() -> None:
    node = make_researcher()
    state = make_state(make_planner_output(investigation_plan=[]))

    update = node.finalize(None, [], state)

    findings = update.get("research_findings")
    assert findings is not None
    assert findings.confidence == 1.0
    assert findings.evidence == []


def test_finalize_maps_summary_fields_into_findings() -> None:
    node = make_researcher()
    summary = ResearchSummary(
        summary="Found the bug.",
        evidence=[],
        focus_addressed=["search codebase for NoneType"],
        gaps=[],
        confidence=0.85,
    )
    state = make_state(make_planner_output())

    update = node.finalize(summary, [], state)

    findings = update.get("research_findings")
    assert findings is not None
    assert findings.summary == "Found the bug."
    assert findings.confidence == 0.85
    assert findings.focus_addressed == ["search codebase for NoneType"]


def test_finalize_adds_gap_when_tool_call_cap_hit() -> None:
    node = make_researcher()
    summary = ResearchSummary(summary="x", confidence=0.5)
    state = make_state(make_planner_output())
    tool_calls = [
        ToolCallRecord(tool_name="lookup", arguments={}, status="success")
        for _ in range(node.max_tool_calls)
    ]

    update = node.finalize(summary, tool_calls, state)

    findings = update.get("research_findings")
    assert findings is not None
    assert any("budget" in gap for gap in findings.gaps)


def test_finalize_adds_gap_when_docmind_unconfigured() -> None:
    node = make_researcher(settings=Settings(docmind_mcp_command=None))
    summary = ResearchSummary(summary="x", confidence=0.5)
    state = make_state(make_planner_output())

    update = node.finalize(summary, [], state)

    findings = update.get("research_findings")
    assert findings is not None
    assert any("DocMind" in gap for gap in findings.gaps)


def test_finalize_no_docmind_gap_when_configured() -> None:
    node = make_researcher(settings=Settings(docmind_mcp_command="docmind-mcp"))
    summary = ResearchSummary(summary="x", confidence=0.5)
    state = make_state(make_planner_output())

    update = node.finalize(summary, [], state)

    findings = update.get("research_findings")
    assert findings is not None
    assert not any("DocMind" in gap for gap in findings.gaps)


def test_finalize_derives_tools_used_from_tool_calls() -> None:
    node = make_researcher()
    summary = ResearchSummary(summary="x", confidence=0.5)
    state = make_state(make_planner_output())
    tool_calls = [
        ToolCallRecord(tool_name="search_code", arguments={}, status="success"),
        ToolCallRecord(tool_name="web_search", arguments={}, status="success"),
    ]

    update = node.finalize(summary, tool_calls, state)

    findings = update.get("research_findings")
    assert findings is not None
    assert findings.tools_used == ["search_code", "web_search"]


def test_system_prompt_lists_available_tool_names() -> None:
    @tool
    def search_code(query: str) -> str:
        """Search the codebase."""
        return query

    node = make_researcher(tools=[search_code])

    prompt = node.system_prompt()

    assert "search_code" in prompt


class _ScriptedToolCallModel(BaseChatModel):
    """Minimal fake chat model that requests one tool call then stops —
    used to exercise the real compiled subgraph end-to-end (create_agent +
    middleware included), mirroring the implementation spike."""

    script: list[AIMessage]
    calls_made: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: Any,  # noqa: ARG002
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: Any = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> ChatResult:
        msg = self.script[min(self.calls_made, len(self.script) - 1)]
        self.calls_made += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable[Any, Any]:  # noqa: ARG002
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:  # noqa: ARG002
        def _parse(_: AIMessage) -> ResearchSummary:
            return ResearchSummary(
                summary="Found the null check bug.",
                evidence=[],
                focus_addressed=["search codebase for NoneType"],
                gaps=[],
                confidence=0.9,
            )

        return self | RunnableLambda(_parse)


async def test_researcher_subgraph_end_to_end_produces_findings() -> None:
    @tool
    def search_code(query: str) -> str:
        """Search the codebase."""
        return f"found: {query}"

    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "search_code", "args": {"query": "NoneType"}, "id": "call_1"}],
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            response_metadata={"model_name": "claude-sonnet-5"},
        ),
        AIMessage(
            content="Done investigating.",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            response_metadata={"model_name": "claude-sonnet-5"},
        ),
    ]
    primary = _ScriptedToolCallModel(script=script)
    fallback = _ScriptedToolCallModel(script=script)
    node = _FakeResearcherSubgraph(
        [search_code],
        primary,
        fallback,
        Settings(docmind_mcp_command=None),
    )
    graph = node.compile()
    triage_state = make_state(make_planner_output())
    state = AgentLoopState(
        **triage_state,
        messages=[],
        summary=None,
        summarize_cost=0.0,
    )

    result = await graph.ainvoke(state)  # pyright: ignore[reportUnknownMemberType]

    findings = result["research_findings"]
    assert findings is not None
    assert findings.summary == "Found the null check bug."
    assert findings.tools_used == ["search_code"]
    assert len(findings.tool_calls) == 1
    assert findings.tool_calls[0].tool_name == "search_code"
    assert result["run_meta"].tool_calls_made == 1
    assert result["run_meta"].iteration_count == 1
