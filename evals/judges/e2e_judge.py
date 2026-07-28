from config.settings import Settings
from evals.judges.model import JUDGE_LLM_CONFIG, judge_chat_model
from evals.judges.prompts.e2e_prompt import build_e2e_judge_messages
from evals.judges.rubric_output import JudgeRubricOutput
from evals.schemas import JudgeVerdict, ReconstructedRun
from llm.structured import call_structured


async def run_e2e_judge(case_id: str, run: ReconstructedRun, *, settings: Settings) -> JudgeVerdict:
    """Holistic 1-5 rubric on overall pipeline coherence/proportionality --
    unlike `evals.graders.e2e_grader`'s exact-match checks (golden set
    only), this needs no ground truth and can run against any fetched
    case."""
    model = judge_chat_model(settings)
    messages = build_e2e_judge_messages(run)
    result = await call_structured(
        model,
        model,
        messages,
        JudgeRubricOutput,
        max_attempts=settings.guardrails.structured_output_max_attempts,
    )
    return JudgeVerdict(
        judge_name="e2e_coherence",
        case_id=case_id,
        score=result.parsed.score,
        rationale=result.parsed.rationale,
        judge_model=JUDGE_LLM_CONFIG.model,
    )
