from pydantic import BaseModel


class JudgeVerdict(BaseModel):
    """One LLM-judge rubric result -- see `evals.judges`. `score` is a
    continuous rubric score for a `call_structured`-backed judge, or 0.0/1.0
    for an `agentevals` trajectory judge (which returns a bool verdict)."""

    judge_name: str
    case_id: str
    score: float | bool
    passed: bool | None = None
    rationale: str
    judge_model: str
