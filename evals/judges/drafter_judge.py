# agentevals ships incomplete type stubs for this factory's return type
# (verified working at runtime) -- same category as this repo's existing
# reportUnknownVariableType ignores for other third-party libraries (e.g.
# llm/factory.py's ChatAnthropic/ChatOpenAI construction).
from agentevals.trajectory.llm import TRAJECTORY_ACCURACY_PROMPT  # noqa: I001
from agentevals.trajectory.llm import (
    create_async_trajectory_llm_as_judge,  # pyright: ignore[reportUnknownVariableType]
)
from config.settings import Settings
from evals.judges.model import JUDGE_LLM_CONFIG, judge_chat_model
from evals.judges.prompts.drafter_prompt import (
    build_drafter_groundedness_messages,
    build_drafter_tone_messages,
)
from evals.judges.rubric_output import JudgeRubricOutput
from evals.langfuse_fetch.reconstruct import message_from_dict
from evals.schemas import JudgeVerdict, ReconstructedTrajectory
from graph.schemas import DraftOutput, ResearchFindings
from llm.structured import call_structured


async def run_drafter_efficiency_judge(
    case_id: str, trajectory: ReconstructedTrajectory, *, settings: Settings
) -> JudgeVerdict:
    """Did the Drafter's own tool-calling loop (sandbox propose-diff/run-tests
    cycles, when a `SandboxHandle` is configured -- see `DrafterSubgraph`'s
    docstring) proceed efficiently, without redundant/looping calls -- the
    same `agentevals` trajectory-quality rubric
    `researcher_judge.run_researcher_efficiency_judge` uses, applied to the
    Drafter's trajectory instead. Needs no authored reference trajectory, so
    this runs against any fetched case, golden or not."""
    model = judge_chat_model(settings)
    evaluator = create_async_trajectory_llm_as_judge(
        prompt=TRAJECTORY_ACCURACY_PROMPT, judge=model, continuous=True
    )
    messages = [message_from_dict(m) for m in trajectory.messages if isinstance(m, dict)]
    result = await evaluator(outputs=messages)
    if isinstance(result, list):
        raise ValueError(f"expected a single EvaluatorResult, got a list: {result!r}")
    return JudgeVerdict(
        judge_name="drafter_efficiency",
        case_id=case_id,
        score=result["score"],
        rationale=result.get("comment") or "",  # pyright: ignore[reportUnknownMemberType]
        judge_model=JUDGE_LLM_CONFIG.model,
    )


async def run_drafter_groundedness_judge(
    case_id: str,
    draft: DraftOutput,
    research_findings: ResearchFindings | None,
    *,
    settings: Settings,
) -> JudgeVerdict:
    """Is each drafted claim actually backed by `ResearchFindings.evidence`
    -- the same groundedness pattern as
    `evals.judges.researcher_judge.run_researcher_groundedness_judge`,
    scoped to the drafter's own public-facing text this time."""
    model = judge_chat_model(settings)
    messages = build_drafter_groundedness_messages(draft, research_findings)
    result = await call_structured(
        model,
        model,
        messages,
        JudgeRubricOutput,
        max_attempts=settings.guardrails.structured_output_max_attempts,
    )
    return JudgeVerdict(
        judge_name="drafter_groundedness",
        case_id=case_id,
        score=result.parsed.score,
        rationale=result.parsed.rationale,
        judge_model=JUDGE_LLM_CONFIG.model,
    )


async def run_drafter_tone_judge(
    case_id: str, draft: DraftOutput, *, settings: Settings
) -> JudgeVerdict:
    """Is the drafted text specific, actionable, and proportionate in tone."""
    model = judge_chat_model(settings)
    messages = build_drafter_tone_messages(draft)
    result = await call_structured(
        model,
        model,
        messages,
        JudgeRubricOutput,
        max_attempts=settings.guardrails.structured_output_max_attempts,
    )
    return JudgeVerdict(
        judge_name="drafter_tone",
        case_id=case_id,
        score=result.parsed.score,
        rationale=result.parsed.rationale,
        judge_model=JUDGE_LLM_CONFIG.model,
    )
