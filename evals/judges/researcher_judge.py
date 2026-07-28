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
from evals.judges.prompts.researcher_prompt import build_researcher_groundedness_messages
from evals.judges.rubric_output import JudgeRubricOutput
from evals.langfuse_fetch.reconstruct import message_from_dict
from evals.schemas import JudgeVerdict, ReconstructedTrajectory
from graph.schemas import ResearchFindings
from llm.structured import call_structured


async def run_researcher_efficiency_judge(
    case_id: str, trajectory: ReconstructedTrajectory, *, settings: Settings
) -> JudgeVerdict:
    """Did the Researcher investigate efficiently, without redundant/looping
    calls -- via `agentevals`' own trajectory-quality rubric. Needs no
    authored reference trajectory (unlike a full `agentevals` trajectory
    *match*, which `evals.graders.researcher_grader` deliberately doesn't
    use -- see that module's docstring), so this runs against any fetched
    case, golden or not."""
    model = judge_chat_model(settings)
    evaluator = create_async_trajectory_llm_as_judge(
        prompt=TRAJECTORY_ACCURACY_PROMPT, judge=model, continuous=True
    )
    messages = [message_from_dict(m) for m in trajectory.messages if isinstance(m, dict)]
    result = await evaluator(outputs=messages)
    if isinstance(result, list):
        raise ValueError(f"expected a single EvaluatorResult, got a list: {result!r}")
    return JudgeVerdict(
        judge_name="researcher_efficiency",
        case_id=case_id,
        score=result["score"],
        rationale=result.get("comment") or "",  # pyright: ignore[reportUnknownMemberType]
        judge_model=JUDGE_LLM_CONFIG.model,
    )


async def run_researcher_groundedness_judge(
    case_id: str,
    research_findings: ResearchFindings,
    trajectory: ReconstructedTrajectory,
    *,
    settings: Settings,
) -> JudgeVerdict:
    """Cross-checks each `Evidence` entry in the final `ResearchSummary`
    against what the tools in the raw trajectory actually returned --
    only possible because the trajectory is pulled from Langfuse, not the
    distilled `ResearchFindings.tool_calls` list."""
    model = judge_chat_model(settings)
    messages = build_researcher_groundedness_messages(research_findings, trajectory)
    result = await call_structured(
        model,
        model,
        messages,
        JudgeRubricOutput,
        max_attempts=settings.guardrails.structured_output_max_attempts,
    )
    return JudgeVerdict(
        judge_name="researcher_groundedness",
        case_id=case_id,
        score=result.parsed.score,
        rationale=result.parsed.rationale,
        judge_model=JUDGE_LLM_CONFIG.model,
    )
