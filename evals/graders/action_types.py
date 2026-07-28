from evals.schemas import GoldenCase, GraderCheck, ReconstructedRun
from graph.schemas import ActionType


def action_types_present(run: ReconstructedRun) -> set[ActionType]:
    if run.draft is None:
        return set()
    return {ActionType(drafted.action.action_type) for drafted in run.draft.actions}


def check_expected_action_types(case: GoldenCase, present: set[ActionType]) -> list[GraderCheck]:
    """Shared by `e2e_grader` and `drafter_grader` -- both read the same
    `ReconstructedRun.draft.actions`, so `GoldenCase.expected_action_types`/
    `forbidden_action_types` mean the same thing checked from either eval
    type rather than two independently-drifting implementations."""
    checks: list[GraderCheck] = []

    if case.expected_action_types:
        missing = set(case.expected_action_types) - present
        checks.append(
            GraderCheck(
                name="expected_action_types_present",
                passed=not missing,
                detail=(
                    "all expected action types present"
                    if not missing
                    else f"missing expected action types: {sorted(t.value for t in missing)}"
                ),
            )
        )

    forbidden_present = set(case.forbidden_action_types) & present
    checks.append(
        GraderCheck(
            name="forbidden_action_types_absent",
            passed=not forbidden_present,
            detail=(
                "no forbidden action types present"
                if not forbidden_present
                else f"forbidden action types present: {sorted(t.value for t in forbidden_present)}"
            ),
        )
    )
    return checks
