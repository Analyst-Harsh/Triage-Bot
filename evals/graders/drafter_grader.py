from evals.graders.action_types import action_types_present, check_expected_action_types
from evals.schemas import GoldenCase, GraderCheck, ReconstructedRun
from graph.schemas import CodeFixAction


def grade_drafter(case: GoldenCase, run: ReconstructedRun) -> list[GraderCheck]:
    """Hand-labeled, deterministic checks against a `GoldenCase`'s
    `expected_action_types`/`forbidden_action_types` (shared with
    `e2e_grader` -- both read the same `ReconstructedRun.draft.actions`) and
    `expected_code_fix` -- e.g. the real `arrow-py` replay case where broken
    baseline tests correctly produced a comment-only response instead of a
    code fix. Kept independent of `grade_e2e` so `run drafter` alone (without
    `run e2e`/`run all`) still verifies the Drafter produced the expected
    action types, not just the code-fix-specific check."""
    checks = check_expected_action_types(case, action_types_present(run))

    if case.expected_code_fix is not None:
        checks.append(_check_expected_code_fix(case.expected_code_fix, run))

    return checks


def _check_expected_code_fix(expected_code_fix: bool, run: ReconstructedRun) -> GraderCheck:
    code_fix_actions = [
        drafted.action
        for drafted in (run.draft.actions if run.draft is not None else [])
        if isinstance(drafted.action, CodeFixAction)
    ]
    has_code_fix = bool(code_fix_actions)

    if not expected_code_fix:
        return GraderCheck(
            name="expected_no_code_fix",
            passed=not has_code_fix,
            detail=(
                "no code_fix action proposed, as expected"
                if not has_code_fix
                else "a code_fix action was proposed but none was expected"
            ),
        )

    detail = (
        f"code_fix proposed, sandbox_result.passed={code_fix_actions[0].sandbox_result.passed}"
        if has_code_fix
        else "expected a code_fix action but none was proposed"
    )
    return GraderCheck(name="expected_code_fix_proposed", passed=has_code_fix, detail=detail)
