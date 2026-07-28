from evals.schemas import GoldenCase
from graph.schemas import ActionType, IssueType, RiskLevel

# Hand-picked from this repo's own replay-pipeline test runs. Only cases
# with a genuinely complete, correctly-traced Langfuse trace are included --
# see docs/agent/evals.md for how the other candidates found during
# authoring (Analyst-Harsh/triage-bot-test#1, arrow-py/arrow#1278) were
# investigated and excluded (orphaned root spans / zero observations,
# respectively), and why a GoldenCase can only ever reference an issue that
# was actually run through the pipeline with Langfuse configured -- there's
# no data to fetch otherwise. More cases to be added once more issues have
# been run with tracing on.
GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        case_id="triage-bot-test-3-factorial-zero",
        repo_full_name="Analyst-Harsh/triage-bot-test",
        issue_number=3,
        issue_category="question",
        notes=(
            "Issue claims factorial(0) should return 0, but 0! = 1 by "
            "mathematical convention -- the report itself is a "
            "misunderstanding, not a real bug. The system correctly "
            "classified this as needs_more_info (low confidence, 0.36) and "
            "closed with an explanatory comment rather than proposing a "
            "code change. Good real case for 'don't fix what isn't broken'."
        ),
        expected_issue_type=IssueType.NEEDS_MORE_INFO,
        expected_action_types=[ActionType.COMMENT, ActionType.CLOSE],
        expected_max_risk_level=RiskLevel.MEDIUM,
        expected_researcher_tool_subset=["search_code"],
        expected_code_fix=False,
    ),
    GoldenCase(
        case_id="triage-bot-test-6-sqrt-feature-request",
        repo_full_name="Analyst-Harsh/triage-bot-test",
        issue_number=6,
        issue_category="feature",
        notes=(
            "Feature request to add sqrt() support (classification "
            "confidence 0.86). The run's most recent attempt actually "
            "failed -- it exceeded its cost_usd budget during risk_check, "
            "after Researcher/Drafter had already produced a reasonable "
            "3-comment draft. This is a legitimate real example of the "
            "budget guardrail firing mid-run: expect the "
            "'cost_within_budget' hand-labeled check to FAIL for this case "
            "-- that's the guardrail correctly tripping, not a false "
            "negative in the grader."
        ),
        expected_issue_type=IssueType.FEATURE_REQUEST,
        expected_action_types=[ActionType.COMMENT, ActionType.CODE_FIX],
        expected_researcher_tool_subset=["query_repo"],
        expected_code_fix=True,
    ),
]
