from evals.schemas import GoldenCase
from graph.schemas import ActionType, IssueType, RiskLevel

# Hand-picked from this repo's own replay-pipeline test runs. Only cases
# with a genuinely complete, correctly-traced Langfuse trace are included --
# see docs/agent/evals.md for how the other candidates found during
# authoring (Analyst-Harsh/triage-bot-test#1, arrow-py/arrow#1278) were
# investigated and excluded (orphaned root spans / zero observations,
# respectively), and why a GoldenCase can only ever reference an issue that
# was actually run through the pipeline with Langfuse configured -- there's
# no data to fetch otherwise. Five cases now, all from
# Analyst-Harsh/triage-bot-test -- #9 is the first genuine spam/abuse case
# (previously missing), which exercises SpamCloseNode and required matching
# fixes in evals/graders/e2e_grader.py (_check_spam_short_circuit) and
# evals/cli.py (_run_selected skips researcher/drafter for it, since those
# nodes never ran).
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
    GoldenCase(
        case_id="triage-bot-test-8-cli-feature-request",
        repo_full_name="Analyst-Harsh/triage-bot-test",
        issue_number=8,
        issue_category="feature",
        notes=(
            "Feature request to add a CLI entry point for the calculator "
            "(classification confidence 0.98). Unlike case-6 (sqrt feature "
            "request, which tripped the budget guardrail), this run "
            "completed the full verified code-fix pipeline within budget "
            "(cost $0.014/$1.00, 6/10 iterations): Drafter implemented the "
            "CLI, verified it in the sandbox, and opened a real PR "
            "(github.com/Analyst-Harsh/triage-bot-test/pull/11) plus an "
            "explanatory issue comment. Both actions were assessed HIGH "
            "risk and required human approval before posting -- the happy "
            "path counterpart to case-6's budget-exceeded failure."
        ),
        expected_issue_type=IssueType.FEATURE_REQUEST,
        expected_action_types=[ActionType.CODE_FIX, ActionType.COMMENT],
        expected_max_risk_level=RiskLevel.HIGH,
        expected_researcher_tool_subset=["query_repo"],
        expected_code_fix=True,
    ),
    GoldenCase(
        case_id="triage-bot-test-9-workfromhome-spam",
        repo_full_name="Analyst-Harsh/triage-bot-test",
        issue_number=9,
        issue_category="spam",
        notes=(
            "First real spam/abuse golden case -- a 'MAKE $5000/WEEK' "
            "work-from-home scam posted as an issue, correctly classified "
            "spam_or_abuse (confidence 0.99). Exercises the current "
            "SpamCloseNode behavior (replacing the old SpamRejectedNode): "
            "the node builds a close action directly, hardcodes it HIGH "
            "risk by policy, and routes straight to approval_queue rather "
            "than posting automatically -- so this run does carry a "
            "one-action close draft (unlike the old draft=None short-"
            "circuit semantics). expected_spam_short_circuit now asserts "
            "Researcher/Drafter never ran (research_findings is None), not "
            "that no draft was produced -- see the accompanying fix to "
            "_check_spam_short_circuit in evals/graders/e2e_grader.py, and "
            "the researcher/drafter skip for such cases in "
            "evals/cli.py::_run_selected."
        ),
        expected_issue_type=IssueType.SPAM_OR_ABUSE,
        expected_spam_short_circuit=True,
        expected_action_types=[ActionType.CLOSE],
        expected_max_risk_level=RiskLevel.HIGH,
    ),
    GoldenCase(
        case_id="triage-bot-test-10-divide-float-precision",
        repo_full_name="Analyst-Harsh/triage-bot-test",
        issue_number=10,
        issue_category="bug",
        notes=(
            "Bug report claiming divide(10, 3) returns 'imprecise' output "
            "(3.3333333333333335), but this is standard Python float "
            "representation, not a defect -- classification confidence "
            "only 0.78, the lowest of any golden case so far, reflecting "
            "genuine ambiguity in whether this is a real bug. The system "
            "investigated (search_code, get_file_contents) and closed with "
            "an explanatory comment plus a triage label rather than "
            "attempting a fix -- the same 'don't fix what isn't broken' "
            "pattern as case-3, but for a bug report, and the first golden "
            "case exercising a label action."
        ),
        expected_issue_type=IssueType.BUG,
        expected_action_types=[ActionType.COMMENT, ActionType.CLOSE, ActionType.LABEL],
        expected_max_risk_level=RiskLevel.MEDIUM,
        expected_researcher_tool_subset=["search_code"],
        expected_code_fix=False,
    ),
]
