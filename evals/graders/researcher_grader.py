from evals.schemas import GoldenCase, GraderCheck, ReconstructedTrajectory


def grade_researcher(case: GoldenCase, trajectory: ReconstructedTrajectory) -> list[GraderCheck]:
    """Hand-labeled, deterministic check against `GoldenCase.expected_researcher_tool_subset`
    -- a bare containment check over tool *names*, not a full trajectory
    match: `GoldenCase` only authors the minimal set of tools a case expects
    to see used, not a complete reference trajectory with matching
    arguments, so `agentevals`' message-level trajectory-match evaluators
    (which compare full reference trajectories) don't fit this check's
    granularity -- they're used instead in `evals.judges.researcher_judge`,
    where no reference trajectory is needed."""
    if not case.expected_researcher_tool_subset:
        return []

    actual_tool_names = {record.tool_name for record in trajectory.tool_call_records}
    missing = set(case.expected_researcher_tool_subset) - actual_tool_names
    return [
        GraderCheck(
            name="expected_researcher_tools_used",
            passed=not missing,
            detail=(
                "all expected tools were used"
                if not missing
                else f"missing expected tools: {sorted(missing)}"
            ),
        )
    ]
