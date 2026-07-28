from evals.graders.action_types import action_types_present, check_expected_action_types
from evals.schemas import GoldenCase, GraderCheck, ReconstructedRun
from graph.schemas import IssueType, RiskLevel

_RISK_LEVEL_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def grade_e2e(case: GoldenCase, run: ReconstructedRun) -> list[GraderCheck]:
    """Hand-labeled, deterministic checks against a `GoldenCase`'s
    `expected_*`/`forbidden_action_types` fields. No LLM, no network -- a
    pure function over already-reconstructed data."""
    checks: list[GraderCheck] = []

    if case.expected_issue_type is not None:
        checks.append(_check_expected_issue_type(case.expected_issue_type, run))

    if case.expected_spam_short_circuit:
        checks.append(_check_spam_short_circuit(run))

    checks.extend(check_expected_action_types(case, action_types_present(run)))

    if case.expected_max_risk_level is not None:
        checks.append(_check_max_risk_level(case.expected_max_risk_level, run))

    checks.append(_check_cost_within_budget(run))
    checks.append(_check_iterations_within_budget(run))

    return checks


def _check_expected_issue_type(expected: IssueType, run: ReconstructedRun) -> GraderCheck:
    actual = run.planner_output.issue_type if run.planner_output is not None else None
    return GraderCheck(
        name="expected_issue_type_matches",
        passed=actual == expected,
        detail=f"expected {expected.value}, got {actual.value if actual is not None else None}",
    )


def _check_spam_short_circuit(run: ReconstructedRun) -> GraderCheck:
    """`SpamCloseNode` (replacing the old `SpamRejectedNode`) builds a
    hardcoded-HIGH-risk `close` action and routes straight to
    `approval_queue`, so a spam run always carries a draft now -- `draft is
    None` is no longer the short-circuit signal. `research_findings is
    None` is: Researcher/Drafter never ran, since `route_after_planner`
    sends `SPAM_OR_ABUSE` straight to `spam_close`."""
    is_spam_classification = (
        run.planner_output is not None and run.planner_output.issue_type == IssueType.SPAM_OR_ABUSE
    )
    short_circuited = is_spam_classification and run.research_findings is None
    return GraderCheck(
        name="spam_short_circuit",
        passed=short_circuited,
        detail=(
            "planner classified spam_or_abuse and Researcher never ran"
            if short_circuited
            else (
                f"expected a spam short-circuit, got issue_type="
                f"{run.planner_output.issue_type.value if run.planner_output else None}, "
                f"researcher_ran={run.research_findings is not None}"
            )
        ),
    )


def _check_max_risk_level(expected_max: RiskLevel, run: ReconstructedRun) -> GraderCheck:
    if run.risk_assessment is None:
        return GraderCheck(
            name="no_risk_level_exceeds_expected_max",
            passed=True,
            detail="no risk_assessment present (nothing to exceed the cap)",
        )
    levels = [assessment.level for assessment in run.risk_assessment.action_assessments]
    over_cap = [
        level for level in levels if _RISK_LEVEL_ORDER[level] > _RISK_LEVEL_ORDER[expected_max]
    ]
    return GraderCheck(
        name="no_risk_level_exceeds_expected_max",
        passed=not over_cap,
        detail=(
            f"all risk levels <= {expected_max.value}"
            if not over_cap
            else f"levels exceeding {expected_max.value}: {[level.value for level in over_cap]}"
        ),
    )


def _check_cost_within_budget(run: ReconstructedRun) -> GraderCheck:
    cost, cap = run.run_meta.estimated_cost_usd, run.run_meta.max_cost_usd
    return GraderCheck(
        name="cost_within_budget",
        passed=cost <= cap,
        detail=f"estimated_cost_usd={cost}, max_cost_usd={cap}",
    )


def _check_iterations_within_budget(run: ReconstructedRun) -> GraderCheck:
    count, cap = run.run_meta.iteration_count, run.run_meta.max_iterations
    return GraderCheck(
        name="iterations_within_budget",
        passed=count <= cap,
        detail=f"iteration_count={count}, max_iterations={cap}",
    )
