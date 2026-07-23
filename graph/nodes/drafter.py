from datetime import UTC, datetime
from typing import ClassVar

import structlog
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from graph.nodes.agent_subgraph import AgentSubgraph
from graph.nodes.node_names import NodeName
from graph.schemas import (
    CodeFixAction,
    CodeFixIntent,
    CommentAction,
    DraftedAction,
    DraftOutput,
    DraftProposal,
    GroundingCritique,
    ProposedAction,
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
    format_failed_fix_comment,
    format_public_draft_text,
)
from tools.sandbox import SandboxHandle

log = structlog.get_logger(__name__)

# Global Constraints value: exploration budget to discover language/manifest/
# test command (4) + dependency install (2) + baseline run_tests (1) + repro
# write+run (2) + 3 fix cycles x (read+edit+run, budget 4 each = 12) = 21,
# rounded up for margin.
DRAFTER_MAX_TOOL_CALLS = 50


class DrafterSubgraph(AgentSubgraph[DraftProposal]):
    """Turns the Planner's classification + the Researcher's findings into a
    concrete, grounded proposed action (or set of actions). Built exactly
    like `ResearcherSubgraph`: comment/label/close drafting needs no tool
    calls, so `tools=[]` is still the common case (e.g. `E2B_API_KEY` unset,
    see `tools.sandbox.sandbox_toolset`). When a run does have sandbox
    access, the composition root passes the sandbox's 7 tools
    (`tools.sandbox.build_sandbox_tools`) plus the matching `SandboxHandle`
    via `sandbox_handle` — the same genuine tool-calling loop
    (propose diff -> run sandbox -> maybe retry) as any other
    `AgentSubgraph`, requiring no rewiring of the parent graph. The model
    itself never proposes a `CodeFixAction` directly (it can't type one
    into existence — `ProposedAction.action` only accepts `CodeFixIntent`,
    intent-only); once the tool-calling loop ends, `finalize()`'s
    `_resolve_code_fix_intent` reads `sandbox_handle`'s already-recorded
    `SandboxAttempt`s and builds the real `CodeFixAction` from the last
    passing `fix_attempt`, degrading to a `CommentAction` describing what
    was tried if none passed (or no handle was configured at all).

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
        primary=LLMEndpointConfig(provider="openai", model="gpt-5.4-nano", temperature=0.0),
        fallback=LLMEndpointConfig(provider="openai", model="gpt-5-nano", temperature=0.0),
    )
    # Inert until the sandboxed code-fix path adds real tools -- `tools=[]`
    # today means this cap is unreachable. Left non-zero (rather than 0) so
    # `assemble_node`'s `cap_hit = len(tool_calls) >= max_tool_calls` doesn't
    # log a false "cap hit" on every run.
    max_tool_calls: ClassVar[int] = DRAFTER_MAX_TOOL_CALLS
    summary_schema: ClassVar[type[BaseModel]] = DraftProposal

    def __init__(
        self, tools: list[BaseTool], *, sandbox_handle: SandboxHandle | None = None
    ) -> None:
        """`sandbox_handle` is the same handle `tools` were built against
        (see `tools.sandbox.sandbox_toolset`) -- `finalize()` reads its
        already-recorded `.attempts`/`.last_passing_fix_attempt`/
        `.base_commit_sha`/`.base_ref`/`.estimated_cost_usd` to turn a
        proposed `CodeFixIntent` into a real `CodeFixAction`. `None` (the
        default) means no sandbox this run -- the same "no tools" case that
        already made `tools=[]` the common case before this class had a
        code-fix path at all."""
        super().__init__(tools)
        self._sandbox_handle = sandbox_handle

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

        # `item.action` is `DraftIntent`, not yet `DraftAction` -- a
        # `CodeFixIntent` is resolved against `self._sandbox_handle`'s
        # already-recorded attempts (see `_resolve_code_fix_intent`), never
        # against a second one: two `CodeFixIntent`s in the same proposal
        # would both resolve to the same handle state, duplicating (or
        # misattributing) sandbox attempts across two actions, so only the
        # first is honored.
        #
        # `grounding_eligible_actions` tracks, in parallel, which of
        # `actions` are safe to send to the grounding self-check below. The
        # fallback-to-comment branch of `_resolve_code_fix_intent` builds its
        # text from `SandboxAttempt` data (files touched, test-log excerpt),
        # not from `ResearchFindings.evidence` -- the grounding check has no
        # way to verify sandbox-derived facts against evidence it was never
        # given, so that action is excluded from the check's input while
        # still being included, unmodified, in `draft.actions`.
        actions: list[DraftedAction] = []
        grounding_eligible_actions: list[DraftedAction] = []
        code_fix_resolved = False
        for item in summary.actions:
            if isinstance(item.action, CodeFixIntent):
                if code_fix_resolved:
                    log.warning("duplicate_code_fix_intent_dropped")
                    continue
                drafted_action, eligible_for_grounding = self._resolve_code_fix_intent(item)
                actions.append(drafted_action)
                if eligible_for_grounding:
                    grounding_eligible_actions.append(drafted_action)
                code_fix_resolved = True
            else:
                drafted_action = DraftedAction(action=item.action, rationale=item.rationale)
                actions.append(drafted_action)
                grounding_eligible_actions.append(drafted_action)

        # Sandbox spend must be folded into run_meta unconditionally --
        # computed once here, before branching, so a code-fix-only draft
        # (which skips the grounding check below and returns early) doesn't
        # silently drop real E2B sandbox cost from the run's accounting.
        sandbox_cost = self._sandbox_handle.estimated_cost_usd if self._sandbox_handle else 0.0

        # Only the text actually posted to GitHub is checked -- never
        # rationale/overall_rationale (internal reasoning, never posted, a
        # judgment call rather than a factual claim) -- and only from
        # `grounding_eligible_actions`, never `actions` wholesale, so a
        # degraded code-fix-fallback comment (sandbox-derived facts the
        # grounding check has no evidence to verify against) never reaches
        # it. `None` means nothing eligible produces any public-facing text
        # (e.g. a label-only draft, or a draft consisting solely of the
        # fallback comment), so there is nothing to fact-check -- skip the
        # grounding-check LLM call entirely rather than running it against
        # rationale or unverifiable sandbox facts (see
        # `format_public_draft_text`'s docstring for the rationale bug this
        # avoids).
        public_draft_text = format_public_draft_text(grounding_eligible_actions)
        if public_draft_text is None:
            draft = DraftOutput(
                actions=actions,
                overall_rationale=summary.overall_rationale,
                unsupported_claims=[],
                drafted_at=datetime.now(UTC),
            )
            update = TriageStateUpdate(draft=draft, status=RunStatus.DRAFTING)
            # Only actually write `run_meta` when there is real sandbox
            # spend to fold in -- a no-op key (same value as the input) here
            # would blur the "total=False, absent key means unchanged"
            # convention this schema otherwise follows (see
            # `ResearcherSubgraph`'s own short-circuit path).
            if sandbox_cost:
                update["run_meta"] = state["run_meta"].with_usage(cost_usd=sandbox_cost)
            return update

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
        # Only this call's own cost (plus this run's sandbox spend, if any) is
        # added here -- never replicate assemble_node's trajectory/summarize
        # accumulation or touch iteration_count; assemble_node adds the
        # draft-generation cost and the iteration bump on top of whatever
        # run_meta this method returns.
        updated_run_meta = state["run_meta"].with_usage(
            cost_usd=critique_result.estimated_cost_usd + sandbox_cost
        )
        return TriageStateUpdate(draft=draft, status=RunStatus.DRAFTING, run_meta=updated_run_meta)

    def _resolve_code_fix_intent(self, item: ProposedAction) -> tuple[DraftedAction, bool]:
        """Turns a model-proposed `CodeFixIntent` into a real `DraftedAction`,
        reading only `self._sandbox_handle`'s already-recorded state -- never
        touching the sandbox itself (no `ensure_ready`/tool call happens
        here; that's the tool-calling loop's job, already finished by the
        time `finalize()` runs).

        Returns `(drafted_action, eligible_for_grounding_check)`. The
        fallback-to-comment branch below builds its text from
        `SandboxAttempt` data (files touched, a test-log excerpt) rather
        than `ResearchFindings.evidence`, so it comes back with
        `eligible_for_grounding_check=False` -- the grounding self-check has
        no way to verify sandbox-derived facts against evidence it was never
        given. The action is still returned (and still lands in
        `draft.actions`) either way; only its eligibility for the grounding
        check's input differs."""
        handle = self._sandbox_handle
        attempt = handle.last_passing_fix_attempt if handle is not None else None
        if handle is None or attempt is None:
            # No verified fix exists: degrade to a comment describing the
            # attempt rather than silently omitting it (DraftOutput.actions
            # requires min_length=1, and a human reviewer benefits from
            # visibility into what was tried and why it didn't pass).
            return (
                DraftedAction(
                    action=CommentAction(
                        comment_body=format_failed_fix_comment(
                            handle.attempts if handle else [],
                            install_attempted=handle.install_attempted if handle else False,
                        )
                    ),
                    rationale=item.rationale,
                ),
                False,
            )
        if handle.base_commit_sha is None or handle.base_ref is None:
            # Invariant: `run_tests` is the only method that appends to
            # `attempts`, and it always calls `_ensure_ready_locked()` first
            # -- which sets both fields before any attempt can exist. A
            # passing `attempt` here means the sandbox was already set up,
            # so this should be unreachable outside a `SandboxHandle` bug.
            raise ValueError(
                "SandboxHandle has a passing fix attempt but no base_commit_sha/base_ref recorded"
            )
        return (
            DraftedAction(
                action=CodeFixAction(
                    diff=attempt.diff,
                    target_files=attempt.changed_files,
                    sandbox_result=attempt.result,
                    base_commit_sha=handle.base_commit_sha,
                    base_ref=handle.base_ref,
                ),
                rationale=item.rationale,
            ),
            # `_public_facing_text` returns `None` for `code_fix` actions
            # regardless (a passing diff is never posted verbatim as
            # GitHub-comment prose), so this eligibility bit is inert today
            # -- marked `True` for correctness/symmetry, since a passing
            # `CodeFixAction`'s `sandbox_result` genuinely is the kind of
            # system-derived fact this check exists to trust, not flag.
            True,
        )
