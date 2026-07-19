from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool

from graph.nodes.drafter import DrafterSubgraph
from graph.nodes.planner import PlannerNode
from graph.schemas import (
    CommentAction,
    DraftProposal,
    GroundingCritique,
    IssuePayload,
    IssueSource,
    IssueType,
    PlannerClassification,
    ProposedAction,
)
from graph.state import TriageState, create_initial_state


def make_issue() -> IssuePayload:
    return IssuePayload(
        repo_full_name="octo/repo",
        issue_number=42,
        title="Crash on startup",
        body="App crashes with a NoneType error.",
        author="octocat",
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/42",
        source=IssueSource.WEBHOOK,
    )


@pytest.fixture
def triage_state() -> TriageState:
    return create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)


class FakeStructuredChatModel(BaseChatModel):
    """Test double for `LLMNode.call_structured`. Overrides
    `with_structured_output` directly instead of emulating real
    provider-specific tool-calling (LangChain's own fake chat models don't
    implement `with_structured_output`), while still routing through real
    `_generate`/callback machinery so `get_usage_metadata_callback()` fires
    exactly as it would against a real provider."""

    response: AIMessage
    parsed_result: Any = None
    parsed_results_by_schema: dict[type, Any] | None = None
    raise_on_generate: bool = False
    fail_parse: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake-structured"

    def _generate(
        self,
        messages: Any,  # noqa: ARG002
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: Any = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> ChatResult:
        if self.raise_on_generate:
            raise RuntimeError("fake API failure")
        return ChatResult(generations=[ChatGeneration(message=self.response)])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:  # noqa: ARG002
        def _parse(_: AIMessage) -> Any:
            if self.fail_parse:
                raise ValueError("fake parsing failure")
            if self.parsed_results_by_schema is not None:
                return self.parsed_results_by_schema[schema]
            return self.parsed_result

        return self | RunnableLambda(_parse)


def make_fake_chat_model(
    *,
    model_name: str = "fake-model",
    input_tokens: int = 10,
    output_tokens: int = 5,
    parsed_result: Any = None,
    parsed_results_by_schema: dict[type, Any] | None = None,
    raise_on_generate: bool = False,
    fail_parse: bool = False,
) -> FakeStructuredChatModel:
    return FakeStructuredChatModel(
        response=AIMessage(
            content="",
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            response_metadata={"model_name": model_name},
        ),
        parsed_result=parsed_result,
        parsed_results_by_schema=parsed_results_by_schema,
        raise_on_generate=raise_on_generate,
        fail_parse=fail_parse,
    )


class _FakePlannerNode(PlannerNode):
    """Test double: overrides `PlannerNode.__init__` (inherited from
    `LLMNode`) to accept chat models directly instead of building them from
    `Settings` — the real `execute()` logic (inherited, not overridden) is
    what's actually under test."""

    def __init__(
        self, primary_model: FakeStructuredChatModel, fallback_model: FakeStructuredChatModel
    ) -> None:
        self._primary_model = primary_model
        self._fallback_model = fallback_model


def make_fake_planner_node(*, parsed_result: PlannerClassification | None = None) -> PlannerNode:
    if parsed_result is None:
        parsed_result = PlannerClassification(
            issue_type=IssueType.BUG,
            classification_confidence=0.9,
            investigation_plan=[],
            reasoning="Test double classification.",
        )
    # Real, litellm-recognized model names (matching PlannerNode.llm_config)
    # rather than arbitrary fake names, so tests asserting on cost behavior
    # (e.g. estimated_cost_usd increasing) get a realistic non-zero cost.
    primary = make_fake_chat_model(model_name="gpt-4o-mini", parsed_result=parsed_result)
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    return _FakePlannerNode(primary_model=primary, fallback_model=fallback)


class _FakeDrafterSubgraph(DrafterSubgraph):
    """Test double: overrides `AgentSubgraph.__init__` (inherited by
    `DrafterSubgraph`) to accept chat models built in-line instead of via
    `Settings` — a drop-in replacement for `DrafterSubgraph` itself (same
    single-`tools`-arg call signature), so it can be swapped in via
    `monkeypatch.setattr(builder_module, "DrafterSubgraph", ...)` in
    `test_builder.py`. `DrafterSubgraph` never short-circuits (drafting
    always happens), so any builder-level test that actually invokes the
    graph needs this rather than the real class, which would otherwise
    attempt a real LLM call."""

    def __init__(self, tools: list[BaseTool] | None = None) -> None:
        self._tools = tools or []
        self._primary_model = make_fake_chat_model(
            model_name="gpt-4o-mini",
            parsed_results_by_schema={
                DraftProposal: DraftProposal(
                    actions=[
                        ProposedAction(
                            action=CommentAction(comment_body="Test double draft comment."),
                            rationale="Test double rationale.",
                        )
                    ],
                    overall_rationale="Test double overall rationale.",
                ),
                GroundingCritique: GroundingCritique(),
            },
        )
        self._fallback_model = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")


def make_fake_drafter_subgraph(tools: list[BaseTool] | None = None) -> DrafterSubgraph:
    return _FakeDrafterSubgraph(tools)
