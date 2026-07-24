from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import Field

from config.settings import get_settings
from graph.nodes.auto_post import AutoPostNode
from graph.nodes.drafter import DrafterSubgraph
from graph.nodes.planner import PlannerNode
from graph.nodes.researcher import ResearcherSubgraph
from graph.nodes.risk_check import RiskCheckNode
from graph.nodes.utils.action_executor import ActionExecutor
from graph.schemas import (
    ActionPostResult,
    ActionRiskJudgment,
    CommentAction,
    DraftProposal,
    GroundingCritique,
    IssuePayload,
    IssueSource,
    IssueType,
    PlannerClassification,
    PostOutcome,
    ProposedAction,
    ResearchSummary,
    RiskJudgmentBatch,
    RiskLevel,
)
from graph.state import TriageState, create_initial_state
from tools.sandbox import SandboxHandle


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
    # If > 0, `_parse` raises for exactly this many calls, then succeeds --
    # lets a test verify retry-then-succeed behavior (call_structured's
    # in-place repair loop) rather than only ever-fails/never-fails.
    fail_parse_times: int = 0
    # Like `fail_parse_times`, but raises a genuine `pydantic.ValidationError`
    # (via validating an empty payload against `schema`) instead of a plain
    # `ValueError` -- lets a test verify call_structured's repair loop
    # actually appends a corrective message on this specific exception type.
    raise_validation_error_times: int = 0
    parse_attempts: int = 0
    # Captures exactly what each _generate call actually received -- lets a
    # test assert on the real (possibly clamped/cleared) messages a caller
    # sent, rather than trusting that the caller sent what it intended to.
    received_messages: list[list[BaseMessage]] = Field(default_factory=list[list[BaseMessage]])

    @property
    def _llm_type(self) -> str:
        return "fake-structured"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: Any = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> ChatResult:
        self.received_messages.append(messages)
        if self.raise_on_generate:
            raise RuntimeError("fake API failure")
        return ChatResult(generations=[ChatGeneration(message=self.response)])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:  # noqa: ARG002
        def _parse(_: AIMessage) -> Any:
            if self.fail_parse:
                raise ValueError("fake parsing failure")
            if self.fail_parse_times > 0 or self.raise_validation_error_times > 0:
                self.parse_attempts += 1
                if self.parse_attempts <= self.raise_validation_error_times:
                    schema.model_validate({})  # raises pydantic.ValidationError
                if self.parse_attempts <= self.fail_parse_times:
                    raise ValueError("fake parsing failure (transient)")
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
    fail_parse_times: int = 0,
    raise_validation_error_times: int = 0,
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
        fail_parse_times=fail_parse_times,
        raise_validation_error_times=raise_validation_error_times,
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


class _FakeRiskCheckNode(RiskCheckNode):
    """Test double: overrides `RiskCheckNode.__init__` (inherited from
    `LLMNode`) to accept chat models directly instead of building them from
    `Settings` — the real `execute()` logic (inherited, not overridden) is
    what's actually under test. Default parsed result judges a single
    comment action (index 0) as low-risk, matching `_FakeDrafterSubgraph`'s
    single-`CommentAction` draft output, so the two fakes compose cleanly in
    `test_builder.py` without a real LLM call happening for either node."""

    def __init__(
        self, primary_model: FakeStructuredChatModel, fallback_model: FakeStructuredChatModel
    ) -> None:
        self._primary_model = primary_model
        self._fallback_model = fallback_model


def make_fake_risk_check_node(*, parsed_result: RiskJudgmentBatch | None = None) -> RiskCheckNode:
    if parsed_result is None:
        parsed_result = RiskJudgmentBatch(
            judgments=[
                ActionRiskJudgment(
                    action_index=0,
                    level=RiskLevel.LOW,
                    risk_factors=[],
                    reasoning="Test double judgment.",
                )
            ]
        )
    primary = make_fake_chat_model(model_name="gpt-4o-mini", parsed_result=parsed_result)
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    return _FakeRiskCheckNode(primary_model=primary, fallback_model=fallback)


class _FakeResearcherSubgraph(ResearcherSubgraph):
    """Test double: overrides `AgentSubgraph.__init__` (inherited by
    `ResearcherSubgraph`) to accept chat models directly instead of building
    them from `Settings` -- a drop-in replacement for `ResearcherSubgraph`
    itself (same single-`tools`-arg call signature), so it can be swapped in
    via `monkeypatch.setattr(builder_module, "ResearcherSubgraph", ...)` in
    `test_builder.py`/`test_checkpointer.py`, matching `_FakeDrafterSubgraph`.
    `self._settings` is still real (`get_settings()`, no I/O, no credential
    needed) since `ResearcherSubgraph.finalize()` reads
    `self._settings.docmind_mcp_command`."""

    def __init__(self, tools: list[BaseTool] | None = None) -> None:
        self._tools = tools or []
        self._settings = get_settings()
        self._primary_model = make_fake_chat_model(
            model_name="gpt-4o-mini",
            parsed_result=ResearchSummary(summary="Test double research summary.", confidence=0.9),
        )
        self._fallback_model = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")


def make_fake_researcher_subgraph(tools: list[BaseTool] | None = None) -> ResearcherSubgraph:
    return _FakeResearcherSubgraph(tools)


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

    def __init__(
        self,
        tools: list[BaseTool] | None = None,
        *,
        sandbox_handle: SandboxHandle | None = None,
    ) -> None:
        self._tools = tools or []
        self._sandbox_handle = sandbox_handle
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


def make_fake_drafter_subgraph(
    tools: list[BaseTool] | None = None, *, sandbox_handle: SandboxHandle | None = None
) -> DrafterSubgraph:
    return _FakeDrafterSubgraph(tools, sandbox_handle=sandbox_handle)


class _FakeAutoPostNode(AutoPostNode):
    """Test double: overrides `AutoPostNode.__init__` (inherited, would
    otherwise construct a real `ActionExecutor`, which itself resolves the
    real process-wide `get_github_client()` singleton) to accept an
    `ActionExecutor`-shaped fake directly -- the real `execute()` logic
    (inherited, not overridden) is what's actually under test."""

    def __init__(self, action_executor: Any) -> None:
        self._action_executor = action_executor


def make_fake_auto_post_node(action_executor: Any = None) -> AutoPostNode:
    if action_executor is None:
        action_executor = create_autospec(ActionExecutor, instance=True, spec_set=True)
        # Default stub result so callers that don't care about ActionExecutor
        # behavior (e.g. builder-level integration tests) get a real,
        # schema-valid `ActionPostResult` back rather than a bare `AsyncMock`.
        action_executor.execute.return_value = ActionPostResult(outcome=PostOutcome.POSTED)
    return _FakeAutoPostNode(action_executor)
