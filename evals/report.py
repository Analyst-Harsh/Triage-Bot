import json
from datetime import UTC, datetime
from typing import Literal

from evals.schemas import EvalCaseResult, EvalRunReport, GraderCheck, JudgeVerdict


def make_case_result(
    case_id: str,
    eval_type: Literal["e2e", "researcher", "drafter"],
    hand_labeled: list[GraderCheck],
    llm_judged: list[JudgeVerdict],
) -> EvalCaseResult:
    """`overall_passed` reflects only `hand_labeled` checks -- `llm_judged`
    verdicts are rubric-scored, not ground-truth, so they inform the report
    but don't gate pass/fail (see `EvalCaseResult`'s docstring)."""
    return EvalCaseResult(
        case_id=case_id,
        eval_type=eval_type,
        hand_labeled=hand_labeled,
        llm_judged=llm_judged,
        overall_passed=all(check.passed for check in hand_labeled),
    )


def build_report(case_results: list[EvalCaseResult], eval_types_run: list[str]) -> EvalRunReport:
    return EvalRunReport(
        run_at=datetime.now(UTC), eval_types_run=eval_types_run, case_results=case_results
    )


def print_report(report: EvalRunReport) -> None:
    for result in report.case_results:
        print(f"\n=== [{result.eval_type}] {result.case_id} ===")
        for check in result.hand_labeled:
            mark = "PASS" if check.passed else "FAIL"
            print(f"  [{mark}] {check.name}: {check.detail}")
        for verdict in result.llm_judged:
            print(f"  [judge:{verdict.judge_name}] score={verdict.score} -- {verdict.rationale}")
    print("\n=== Summary ===")
    for eval_type, counts in report.summary().items():
        print(f"  {eval_type}: {counts['passed']}/{counts['total']} passed")


def report_to_json(report: EvalRunReport) -> str:
    return json.dumps(json.loads(report.model_dump_json()), indent=2)
