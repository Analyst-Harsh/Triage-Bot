from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda

from graph.nodes.agent_subgraph import AgentLoopState
from graph.nodes.drafter import DrafterSubgraph
from graph.schemas import (
    CommentAction,
    DraftProposal,
    Evidence,
    GroundingCritique,
    IssueType,
    LabelAction,
    PlannerOutput,
    ProposedAction,
    ResearchFindings,
)
from graph.state import TriageState, create_initial_state
from llm.pricing import estimate_cost_usd
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


def make_research_findings(**overrides: object) -> ResearchFindings:
    defaults: dict[str, object] = {
        "summary": "Missing null check in the config loader.",
        "evidence": [
            Evidence(
                source_type="docmind",
                reference="src/config.py:12",
                snippet="config = load_config()",
                relevance=0.95,
            )
        ],
        "focus_addressed": ["search codebase for NoneType"],
        "gaps": [],
        "confidence": 0.9,
        "researched_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ResearchFindings(**defaults)  # type: ignore[arg-type]


def make_state(
    planner_output: PlannerOutput | None, research_findings: ResearchFindings | None
) -> TriageState:
    state = create_initial_state(make_issue(), max_iterations=10, max_cost_usd=1.0)
    state["planner_output"] = planner_output
    state["research_findings"] = research_findings
    return state


def make_proposal(**overrides: object) -> DraftProposal:
    defaults: dict[str, object] = {
        "actions": [
            ProposedAction(
                action=CommentAction(comment_body="Could you share a reproduction?"),
                rationale="Not enough information to act yet.",
            )
        ],
        "overall_rationale": "The issue lacks reproduction steps.",
    }
    defaults.update(overrides)
    return DraftProposal(**defaults)  # type: ignore[arg-type]


class _FakeDrafterSubgraph(DrafterSubgraph):
    """Test double: overrides `AgentSubgraph.__init__` to accept fake chat
    models directly, same pattern as `_FakeResearcherSubgraph`."""

    def __init__(self, primary_model: BaseChatModel, fallback_model: BaseChatModel) -> None:
        self._tools = []
        self._primary_model = primary_model
        self._fallback_model = fallback_model


def make_drafter(
    proposal: DraftProposal | None = None, critique: GroundingCritique | None = None
) -> _FakeDrafterSubgraph:
    primary = make_fake_chat_model(
        model_name="gpt-4o-mini",
        parsed_results_by_schema={
            DraftProposal: proposal,
            GroundingCritique: critique or GroundingCritique(),
        },
    )
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    return _FakeDrafterSubgraph(primary, fallback)


def test_prepare_raises_when_planner_output_missing() -> None:
    node = make_drafter()
    state = make_state(None, make_research_findings())

    with pytest.raises(ValueError, match="planner_output"):
        node.prepare(state)


def test_prepare_raises_when_research_findings_missing() -> None:
    node = make_drafter()
    state = make_state(make_planner_output(), None)

    with pytest.raises(ValueError, match="research_findings"):
        node.prepare(state)


def test_prepare_never_short_circuits() -> None:
    node = make_drafter()
    state = make_state(make_planner_output(), make_research_findings())

    result = node.prepare(state)

    assert result is not None
    assert len(result) == 1


async def test_finalize_raises_when_summary_is_none() -> None:
    node = make_drafter()
    state = make_state(make_planner_output(), make_research_findings())

    with pytest.raises(ValueError, match="summary"):
        await node.finalize(None, [], state)


async def test_finalize_raises_when_research_findings_missing() -> None:
    node = make_drafter()
    state = make_state(make_planner_output(), None)

    with pytest.raises(ValueError, match="research_findings"):
        await node.finalize(make_proposal(), [], state)


async def test_finalize_maps_proposal_into_draft_output() -> None:
    node = make_drafter()
    proposal = make_proposal()
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(proposal, [], state)

    draft = update.get("draft")
    assert draft is not None
    assert len(draft.actions) == 1
    assert isinstance(draft.actions[0].action, CommentAction)
    assert draft.overall_rationale == "The issue lacks reproduction steps."
    assert draft.unsupported_claims == []


async def test_finalize_populates_unsupported_claims_from_grounding_check() -> None:
    node = make_drafter(
        critique=GroundingCritique(unsupported_claims=["Claims the fix shipped already."])
    )
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(make_proposal(), [], state)

    draft = update.get("draft")
    assert draft is not None
    assert draft.unsupported_claims == ["Claims the fix shipped already."]


async def test_finalize_adds_grounding_cost_without_bumping_iteration_count() -> None:
    node = make_drafter()
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(make_proposal(), [], state)

    run_meta = update.get("run_meta")
    assert run_meta is not None
    assert run_meta.estimated_cost_usd > state["run_meta"].estimated_cost_usd
    assert run_meta.iteration_count == state["run_meta"].iteration_count


async def test_finalize_skips_grounding_check_for_label_only_draft() -> None:
    """Regression test for the bug where a label-only draft's rationale got
    flagged as "unsupported claims": with no public-facing text at all,
    finalize() must skip the grounding-check LLM call entirely rather than
    running it against rationale. The critique here is deliberately
    configured with non-empty claims -- if it were used, this test would
    fail, proving the call itself was skipped, not just coincidentally
    empty."""
    node = make_drafter(critique=GroundingCritique(unsupported_claims=["should never appear"]))
    label_only_proposal = make_proposal(
        actions=[
            ProposedAction(
                action=LabelAction(labels_to_add=["feature_request"], labels_to_remove=[]),
                rationale="This aligns with a feature request for design improvements.",
            )
        ]
    )
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(label_only_proposal, [], state)

    draft = update.get("draft")
    assert draft is not None
    assert draft.unsupported_claims == []
    # `run_meta` is legitimately absent here -- no cost was spent, so
    # finalize() leaves it unset (same "total=False, unchanged means
    # inherit" convention ResearcherSubgraph's own short-circuit path uses),
    # rather than redundantly returning a copy of the unchanged input.
    assert "run_meta" not in update


class _ScriptedModel(BaseChatModel):
    """Minimal fake chat model with no tool calls — Drafter has zero tools
    today, so the agent loop always ends after a single generation. Tracks
    `calls_made` so the end-to-end test can derive its expected total cost
    from the actual number of calls made, rather than assuming a fixed
    count."""

    response: AIMessage
    parsed_results_by_schema: dict[type, Any]
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
        self.calls_made += 1
        return ChatResult(generations=[ChatGeneration(message=self.response)])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:  # noqa: ARG002
        def _parse(_: AIMessage) -> Any:
            return self.parsed_results_by_schema[schema]

        return self | RunnableLambda(_parse)


async def test_drafter_subgraph_end_to_end_produces_grounded_draft() -> None:
    proposal = make_proposal()
    critique = GroundingCritique(unsupported_claims=["Claims the fix shipped already."])
    response = AIMessage(
        content="",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        response_metadata={"model_name": "gpt-4o-mini"},
    )
    primary = _ScriptedModel(
        response=response,
        parsed_results_by_schema={DraftProposal: proposal, GroundingCritique: critique},
    )
    fallback = _ScriptedModel(
        response=response,
        parsed_results_by_schema={DraftProposal: proposal, GroundingCritique: critique},
    )
    node = _FakeDrafterSubgraph(primary, fallback)
    graph = node.compile()
    triage_state = make_state(make_planner_output(), make_research_findings())
    state = AgentLoopState(
        **triage_state,
        messages=[],
        summary=None,
        summarize_cost=0.0,
    )

    result = await graph.ainvoke(state)  # pyright: ignore[reportUnknownMemberType]

    draft = result["draft"]
    assert draft is not None
    assert draft.unsupported_claims == ["Claims the fix shipped already."]
    assert isinstance(draft.actions[0].action, CommentAction)
    assert result["run_meta"].iteration_count == 1

    # Every call landed on primary (fallback never triggered) and cost
    # accumulation reflects each one exactly once -- proves finalize()'s own
    # grounding-check cost and assemble_node's trajectory/summarize cost are
    # both counted, with nothing duplicated or dropped.
    assert fallback.calls_made == 0
    assert primary.calls_made >= 2
    single_call_cost = estimate_cost_usd("gpt-4o-mini", 10, 5)
    expected_cost = primary.calls_made * single_call_cost
    assert result["run_meta"].estimated_cost_usd == pytest.approx(expected_cost)
