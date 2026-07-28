from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from evals.schemas.grader_check import GraderCheck
from evals.schemas.judge_verdict import JudgeVerdict


class EvalCaseResult(BaseModel):
    """One case's result for one eval type. `overall_passed` reflects only
    `hand_labeled` checks -- `llm_judged` verdicts inform the report but
    don't gate pass/fail, since they're rubric-scored, not ground-truth."""

    case_id: str
    eval_type: Literal["e2e", "researcher", "drafter"]
    hand_labeled: list[GraderCheck] = []
    llm_judged: list[JudgeVerdict] = []
    overall_passed: bool


class EvalRunReport(BaseModel):
    """Aggregate report for one `evals.cli` invocation -- see `evals.report`."""

    run_at: datetime
    eval_types_run: list[str]
    case_results: list[EvalCaseResult] = []

    def summary(self) -> dict[str, dict[str, int]]:
        """Per-eval-type passed/total counts over `hand_labeled` checks,
        e.g. `{"e2e": {"passed": 2, "total": 3}}`."""
        counts: dict[str, dict[str, int]] = {}
        for result in self.case_results:
            bucket = counts.setdefault(result.eval_type, {"passed": 0, "total": 0})
            bucket["total"] += 1
            if result.overall_passed:
                bucket["passed"] += 1
        return counts
