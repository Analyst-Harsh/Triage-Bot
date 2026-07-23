from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
import structlog
from github import Github
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import SecretStr
from structlog.testing import capture_logs

import graph.nodes.drafter as drafter_module
from config.settings import Settings
from graph.nodes.agent_subgraph import AgentLoopState
from graph.nodes.drafter import DrafterSubgraph
from graph.schemas import (
    CodeFixAction,
    CodeFixIntent,
    CommentAction,
    DraftProposal,
    Evidence,
    GroundingCritique,
    IssueType,
    LabelAction,
    PlannerOutput,
    ProposedAction,
    ResearchFindings,
    SandboxAttempt,
    SandboxResult,
)
from graph.state import TriageState, create_initial_state
from llm.pricing import estimate_cost_usd
from llm.result import LLMResult
from tests.graph.nodes.conftest import make_fake_chat_model, make_issue
from tools.sandbox import MAX_SANDBOX_FIX_ATTEMPTS, SandboxHandle


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

    def __init__(
        self,
        primary_model: BaseChatModel,
        fallback_model: BaseChatModel,
        *,
        sandbox_handle: SandboxHandle | None = None,
    ) -> None:
        self._tools = []
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._sandbox_handle = sandbox_handle


def make_drafter(
    proposal: DraftProposal | None = None,
    critique: GroundingCritique | None = None,
    *,
    sandbox_handle: SandboxHandle | None = None,
) -> _FakeDrafterSubgraph:
    primary = make_fake_chat_model(
        model_name="gpt-4o-mini",
        parsed_results_by_schema={
            DraftProposal: proposal,
            GroundingCritique: critique or GroundingCritique(),
        },
    )
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    return _FakeDrafterSubgraph(primary, fallback, sandbox_handle=sandbox_handle)


def make_sandbox_handle(**overrides: object) -> SandboxHandle:
    """Constructs a real `SandboxHandle` with dummy `settings`/`github_client`
    -- safe for `finalize()`/`_resolve_code_fix_intent()` tests since neither
    calls `ensure_ready()` or any other real sandbox I/O; they only read
    `.attempts`/`.last_passing_fix_attempt`/`.base_commit_sha`/`.base_ref`/
    `.estimated_cost_usd`, all of which this helper sets directly rather than
    via any E2B/GitHub round trip."""
    defaults: dict[str, object] = {
        "settings": Settings(e2b_api_key=SecretStr("test-e2b-key")),
        "github_client": Github(),
        "repo_full_name": "octo/repo",
        "ref": "main",
    }
    defaults.update(overrides)
    return SandboxHandle(**defaults)  # type: ignore[arg-type]


def make_sandbox_attempt(**overrides: object) -> SandboxAttempt:
    defaults: dict[str, object] = {
        "kind": "fix_attempt",
        "attempt_number": 1,
        "diff": "diff --git a/src/config.py b/src/config.py\n+fix",
        "changed_files": ["src/config.py"],
        "result": SandboxResult(
            passed=True, logs="1 passed", test_command="pytest", duration_seconds=1.5
        ),
        "recorded_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return SandboxAttempt(**defaults)  # type: ignore[arg-type]


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


# ---------------------------------------------------------------------------
# Sandboxed code-fix path: `_resolve_code_fix_intent` + `finalize()` dispatch
# ---------------------------------------------------------------------------


def make_code_fix_intent_item(**overrides: object) -> ProposedAction:
    defaults: dict[str, object] = {
        "action": CodeFixIntent(),
        "rationale": "Verified a passing fix in the sandbox.",
    }
    defaults.update(overrides)
    return ProposedAction(**defaults)  # type: ignore[arg-type]


def test_resolve_code_fix_intent_builds_code_fix_action_from_passing_attempt() -> None:
    attempt = make_sandbox_attempt()
    handle = make_sandbox_handle()
    handle.attempts = [attempt]
    handle.base_commit_sha = "abc123def456"
    handle.base_ref = "main"
    node = make_drafter(sandbox_handle=handle)
    item = make_code_fix_intent_item()

    # Protected-member access is deliberate: the brief calls for testing this
    # helper directly (its behavior is the unit under test, not just an
    # implementation detail exercised incidentally via finalize()).
    drafted, eligible_for_grounding = node._resolve_code_fix_intent(  # pyright: ignore[reportPrivateUsage]
        item
    )

    assert isinstance(drafted.action, CodeFixAction)
    assert drafted.action.diff == attempt.diff
    assert drafted.action.target_files == attempt.changed_files
    assert drafted.action.sandbox_result == attempt.result
    assert drafted.action.base_commit_sha == "abc123def456"
    assert drafted.action.base_ref == "main"
    assert drafted.rationale == item.rationale
    # A passing fix's `CodeFixAction` produces no public-facing text anyway
    # (see `public_facing_text`), but is marked eligible for
    # correctness/symmetry -- its `sandbox_result` is a genuine
    # system-derived fact, not an unverifiable claim.
    assert eligible_for_grounding is True


def test_resolve_code_fix_intent_degrades_to_comment_when_no_passing_attempt() -> None:
    failing_attempt = make_sandbox_attempt(
        result=SandboxResult(
            passed=False, logs="1 failed", test_command="pytest", duration_seconds=1.0
        )
    )
    handle = make_sandbox_handle()
    handle.attempts = [failing_attempt]
    node = make_drafter(sandbox_handle=handle)
    item = make_code_fix_intent_item()

    drafted, eligible_for_grounding = node._resolve_code_fix_intent(  # pyright: ignore[reportPrivateUsage]
        item
    )

    assert isinstance(drafted.action, CommentAction)
    assert "couldn't land a passing result" in drafted.action.comment_body
    assert drafted.rationale == item.rationale
    # Sandbox-derived fallback text is ineligible for the grounding check --
    # it can't be verified against `ResearchFindings.evidence`.
    assert eligible_for_grounding is False


def test_resolve_code_fix_intent_no_warning_when_budget_genuinely_exhausted() -> None:
    failing_attempts = [
        make_sandbox_attempt(
            attempt_number=i + 1,
            result=SandboxResult(
                passed=False, logs="1 failed", test_command="pytest", duration_seconds=1.0
            ),
        )
        for i in range(MAX_SANDBOX_FIX_ATTEMPTS)
    ]
    handle = make_sandbox_handle()
    handle.attempts = failing_attempts
    node = make_drafter(sandbox_handle=handle)
    item = make_code_fix_intent_item()

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        node._resolve_code_fix_intent(item)  # pyright: ignore[reportPrivateUsage]

    assert not any(entry["event"] == "drafter_gave_up_with_budget_remaining" for entry in cap_logs)


def test_resolve_code_fix_intent_degrades_to_comment_when_handle_is_none() -> None:
    node = make_drafter(sandbox_handle=None)
    item = make_code_fix_intent_item()

    drafted, eligible_for_grounding = node._resolve_code_fix_intent(  # pyright: ignore[reportPrivateUsage]
        item
    )

    assert isinstance(drafted.action, CommentAction)
    assert drafted.rationale == item.rationale
    assert eligible_for_grounding is False


async def test_finalize_resolves_code_fix_intent_into_draft_action() -> None:
    attempt = make_sandbox_attempt()
    handle = make_sandbox_handle()
    handle.attempts = [attempt]
    handle.base_commit_sha = "abc123def456"
    handle.base_ref = "main"
    node = make_drafter(sandbox_handle=handle)
    proposal = make_proposal(actions=[make_code_fix_intent_item()])
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(proposal, [], state)

    draft = update.get("draft")
    assert draft is not None
    assert len(draft.actions) == 1
    assert isinstance(draft.actions[0].action, CodeFixAction)


async def test_finalize_drops_duplicate_code_fix_intent_with_warning() -> None:
    """A proposal with two `CodeFixIntent`s must resolve exactly one of them
    against the sandbox handle -- resolving both would duplicate (or
    misattribute) the same recorded sandbox attempts across two actions."""
    attempt = make_sandbox_attempt()
    handle = make_sandbox_handle()
    handle.attempts = [attempt]
    handle.base_commit_sha = "abc123def456"
    handle.base_ref = "main"
    node = make_drafter(sandbox_handle=handle)
    proposal = make_proposal(
        actions=[
            make_code_fix_intent_item(rationale="First fix intent."),
            make_code_fix_intent_item(rationale="Second fix intent."),
        ]
    )
    state = make_state(make_planner_output(), make_research_findings())

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        update = await node.finalize(proposal, [], state)

    draft = update.get("draft")
    assert draft is not None
    code_fix_actions = [a for a in draft.actions if a.action.action_type == "code_fix"]
    assert len(code_fix_actions) == 1
    assert code_fix_actions[0].rationale == "First fix intent."
    assert any(entry["event"] == "duplicate_code_fix_intent_dropped" for entry in cap_logs)


async def test_finalize_folds_sandbox_cost_into_run_meta_when_handle_set() -> None:
    handle = make_sandbox_handle()
    handle.attempts = [
        make_sandbox_attempt(kind="baseline"),
        make_sandbox_attempt(kind="fix_attempt", diff=""),  # not counted as a "billed" step here
    ]
    # `estimated_cost_usd` is derived purely from billed sandbox time, which
    # only run_tests()/install_dependencies() accumulate -- simulate that
    # directly rather than driving real sandbox I/O. Protected-attribute
    # access is deliberate: `SandboxHandle` exposes no public setter for
    # billed time (by design -- only its own I/O methods should ever
    # accumulate it), so a test that wants a nonzero `estimated_cost_usd`
    # without real E2B I/O has no other way to arrange it.
    handle._billed_seconds = 120.0  # pyright: ignore[reportPrivateUsage]
    node = make_drafter(sandbox_handle=handle)
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(make_proposal(), [], state)

    run_meta = update.get("run_meta")
    assert run_meta is not None
    assert handle.estimated_cost_usd > 0.0
    assert run_meta.estimated_cost_usd == pytest.approx(
        state["run_meta"].estimated_cost_usd
        + estimate_cost_usd("gpt-4o-mini", 10, 5)
        + handle.estimated_cost_usd
    )


async def test_finalize_does_not_fold_sandbox_cost_when_handle_is_none() -> None:
    """`sandbox_handle=None` is today's common comment/label/close-only
    path; this pins its cost accounting to exactly what it was before the
    sandboxed code-fix path landed."""
    node = make_drafter(sandbox_handle=None)
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(make_proposal(), [], state)

    run_meta = update.get("run_meta")
    assert run_meta is not None
    # Only the grounding-check call's own cost was added -- nothing from a
    # sandbox that was never configured this run.
    assert run_meta.estimated_cost_usd == pytest.approx(
        state["run_meta"].estimated_cost_usd + estimate_cost_usd("gpt-4o-mini", 10, 5)
    )


async def test_finalize_folds_sandbox_cost_into_run_meta_on_code_fix_only_early_return() -> None:
    """A draft consisting solely of a successful `CodeFixAction` takes the
    early-return branch (`format_public_draft_text` is `None` for
    `code_fix`, so the grounding check never runs) -- this is the primary
    success case the sandboxed code-fix feature exists to produce, and its
    real E2B sandbox spend must still be folded into `run_meta` even though
    no grounding-check cost is added on this path."""
    attempt = make_sandbox_attempt()
    handle = make_sandbox_handle()
    handle.attempts = [attempt]
    handle.base_commit_sha = "abc123def456"
    handle.base_ref = "main"
    # See `test_finalize_folds_sandbox_cost_into_run_meta_when_handle_set`
    # for why `_billed_seconds` is set directly.
    handle._billed_seconds = 120.0  # pyright: ignore[reportPrivateUsage]
    node = make_drafter(sandbox_handle=handle)
    proposal = make_proposal(actions=[make_code_fix_intent_item()])
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(proposal, [], state)

    draft = update.get("draft")
    assert draft is not None
    assert len(draft.actions) == 1
    assert isinstance(draft.actions[0].action, CodeFixAction)

    run_meta = update.get("run_meta")
    assert run_meta is not None
    assert handle.estimated_cost_usd > 0.0
    assert run_meta.estimated_cost_usd == pytest.approx(
        state["run_meta"].estimated_cost_usd + handle.estimated_cost_usd
    )


# ---------------------------------------------------------------------------
# Finding 2: grounding check must not run against sandbox-derived facts it
# has no way to verify (the code-fix fallback comment's provenance).
# ---------------------------------------------------------------------------


async def test_finalize_skips_grounding_check_for_fallback_only_code_fix_draft() -> None:
    """A draft consisting solely of a degraded code-fix fallback comment
    (a fix was attempted in the sandbox but nothing passed) must not run
    the grounding check -- that comment's facts (files touched, test-log
    excerpt) come from `SandboxAttempt` data, not `ResearchFindings.evidence`,
    so the check has no way to verify them (same category as
    `test_finalize_skips_grounding_check_for_label_only_draft`, just a
    different reason there's no eligible public text). The critique here is
    deliberately configured with non-empty claims -- if the check ran, this
    test would fail, proving it was actually skipped, not just
    coincidentally empty."""
    failing_attempt = make_sandbox_attempt(
        result=SandboxResult(
            passed=False, logs="1 failed", test_command="pytest", duration_seconds=1.0
        )
    )
    handle = make_sandbox_handle()
    handle.attempts = [failing_attempt]
    node = make_drafter(
        sandbox_handle=handle,
        critique=GroundingCritique(unsupported_claims=["should never appear"]),
    )
    proposal = make_proposal(actions=[make_code_fix_intent_item()])
    state = make_state(make_planner_output(), make_research_findings())

    update = await node.finalize(proposal, [], state)

    draft = update.get("draft")
    assert draft is not None
    assert len(draft.actions) == 1
    assert isinstance(draft.actions[0].action, CommentAction)
    assert draft.unsupported_claims == []
    # No grounding-check cost was folded in -- `handle.estimated_cost_usd`
    # is 0.0 here (no billed sandbox time simulated), so an absent
    # `run_meta` confirms the grounding-check LLM call itself never fired.
    assert "run_meta" not in update


async def test_finalize_grounding_check_excludes_fallback_comment_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A draft with both a genuine LLM-authored comment and a degraded
    code-fix fallback comment must still run the grounding check (the
    genuine action does produce public text) -- but the check's input text
    must be built only from the genuine action, never the fallback's
    sandbox-derived text. Intercepts `call_structured` directly (rather than
    inspecting `GroundingCritique` output, which can't reveal what was sent
    as input) to capture the exact draft text the grounding check received."""
    failing_attempt = make_sandbox_attempt(
        result=SandboxResult(
            passed=False, logs="1 failed", test_command="pytest", duration_seconds=1.0
        )
    )
    handle = make_sandbox_handle()
    handle.attempts = [failing_attempt]
    node = make_drafter(sandbox_handle=handle)
    proposal = make_proposal(
        actions=[
            ProposedAction(
                action=CommentAction(comment_body="MARKER_GENUINE_COMMENT_TEXT"),
                rationale="Genuine LLM-authored comment.",
            ),
            make_code_fix_intent_item(),
        ]
    )
    state = make_state(make_planner_output(), make_research_findings())

    captured_draft_texts: list[str] = []

    async def fake_call_structured(
        primary: BaseChatModel,  # noqa: ARG001
        fallback: BaseChatModel,  # noqa: ARG001
        messages: Sequence[BaseMessage],
        schema: type[object],  # noqa: ARG001
    ) -> LLMResult[GroundingCritique]:
        captured_draft_texts.append(str(messages[-1].content))
        return LLMResult(
            parsed=GroundingCritique(),
            total_input_tokens=0,
            total_output_tokens=0,
            estimated_cost_usd=0.0,
            models_invoked=[],
        )

    monkeypatch.setattr(drafter_module, "call_structured", fake_call_structured)

    update = await node.finalize(proposal, [], state)

    # The grounding check fired exactly once, with only the genuine
    # comment's text -- the fallback comment's "couldn't land a passing
    # result" text never reached it.
    assert len(captured_draft_texts) == 1
    assert "MARKER_GENUINE_COMMENT_TEXT" in captured_draft_texts[0]
    assert "couldn't land a passing result" not in captured_draft_texts[0]

    draft = update.get("draft")
    assert draft is not None
    assert len(draft.actions) == 2


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


async def test_drafter_subgraph_end_to_end_produces_grounded_code_fix_draft() -> None:
    """Same shape as `test_drafter_subgraph_end_to_end_produces_grounded_draft`,
    but the scripted LLM response proposes a `CodeFixIntent` instead of a
    `CommentAction`, and the subgraph is built with a pre-populated
    `SandboxHandle` (no real E2B/GitHub I/O -- same fixture pattern as
    `test_resolve_code_fix_intent_builds_code_fix_action_from_passing_attempt`).
    Proves the full compiled graph -- prepare -> agent loop -> summarize ->
    finalize()'s `_resolve_code_fix_intent` dispatch -- turns a proposed
    intent into a real `CodeFixAction` sourced from the handle's recorded
    attempt, not just that the helper does so in isolation."""
    attempt = make_sandbox_attempt()
    handle = make_sandbox_handle()
    handle.attempts = [attempt]
    handle.base_commit_sha = "abc123def456"
    handle.base_ref = "main"

    proposal = make_proposal(actions=[make_code_fix_intent_item()])
    response = AIMessage(
        content="",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        response_metadata={"model_name": "gpt-4o-mini"},
    )
    primary = _ScriptedModel(
        response=response,
        parsed_results_by_schema={DraftProposal: proposal, GroundingCritique: GroundingCritique()},
    )
    fallback = _ScriptedModel(
        response=response,
        parsed_results_by_schema={DraftProposal: proposal, GroundingCritique: GroundingCritique()},
    )
    node = _FakeDrafterSubgraph(primary, fallback, sandbox_handle=handle)
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
    assert len(draft.actions) == 1
    code_fix_action = draft.actions[0].action
    assert isinstance(code_fix_action, CodeFixAction)
    # `code_fix` has no public-facing text (`format_public_draft_text`
    # returns `None` for it), so the grounding check is skipped entirely --
    # the fields below are traced straight back to the `SandboxHandle` set
    # up above, not the (unused) `GroundingCritique()`.
    assert draft.unsupported_claims == []
    assert code_fix_action.diff == attempt.diff
    assert code_fix_action.target_files == attempt.changed_files
    assert code_fix_action.sandbox_result == attempt.result
    assert code_fix_action.base_commit_sha == "abc123def456"
    assert code_fix_action.base_ref == "main"
    assert result["run_meta"].iteration_count == 1
