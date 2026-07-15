from datetime import UTC, datetime

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from graph.schemas import (
    ActionType,
    CodeFixAction,
    DraftOutput,
    EpisodicMemoryHit,
    IssuePayload,
    IssueSource,
    IssueType,
    PlannerOutput,
    ResearchFindings,
    ResearchSource,
    RiskAssessment,
    RiskLevel,
    RunStatus,
    SandboxResult,
)
from graph.state import create_initial_state


def make_issue() -> IssuePayload:
    return IssuePayload(
        repo_full_name="octo/repo",
        issue_number=42,
        title="Crash on startup",
        body="App crashes with a NoneType error.",
        author="octocat",
        author_association="CONTRIBUTOR",
        labels=["bug"],
        created_at=datetime.now(UTC),
        url="https://github.com/octo/repo/issues/42",
        source=IssueSource.WEBHOOK,
        installation_id=123,
    )


def make_fully_populated_state():
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=15, max_cost_usd=2.5)

    state["messages"] = [
        HumanMessage(content="Investigate this issue."),
        AIMessage(content="Searching codebase for related error handling."),
    ]
    state["planner_output"] = PlannerOutput(
        issue_type=IssueType.BUG,
        classification_confidence=0.87,
        investigation_plan=["search codebase for NoneType", "check startup sequence"],
        reasoning="Traceback matches a known startup failure pattern.",
        classified_at=datetime.now(UTC),
    )
    state["research_findings"] = ResearchFindings(
        summary="Missing null check in the config loader.",
        sources=[
            ResearchSource(
                source_type="codebase",
                reference="src/config.py:12",
                snippet="config = load_config()",
                relevance=0.95,
            )
        ],
        code_references=["src/config.py"],
        confidence=0.9,
        open_questions=[],
    )
    state["draft"] = DraftOutput(
        action=CodeFixAction(
            diff="--- a/src/config.py\n+++ b/src/config.py\n",
            target_files=["src/config.py"],
            sandbox_result=SandboxResult(
                passed=True,
                logs="1 passed in 0.42s",
                test_command="pytest tests/test_config.py",
                duration_seconds=0.42,
            ),
        ),
        rationale="Reproduced the crash and verified the fix in sandbox.",
        drafted_at=datetime.now(UTC),
    )
    state["risk_assessment"] = RiskAssessment(
        level=RiskLevel.MEDIUM,
        score=45.0,
        risk_factors=["proposes code change"],
        reasoning="Small, well-tested fix to a single file.",
        requires_human_approval=True,
        assessed_at=datetime.now(UTC),
    )
    state["episodic_context"] = [
        EpisodicMemoryHit(
            past_issue_number=17,
            past_repo="octo/repo",
            summary="Similar config loader crash.",
            action_taken=ActionType.CODE_FIX,
            outcome="accepted",
            similarity_score=0.88,
            retrieved_at=datetime.now(UTC),
        )
    ]
    state["status"] = RunStatus.PENDING_APPROVAL
    return state


def test_create_initial_state_defaults():
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)

    assert state["issue"] == issue
    assert state["messages"] == []
    assert state["planner_output"] is None
    assert state["research_findings"] is None
    assert state["draft"] is None
    assert state["risk_assessment"] is None
    assert state["episodic_context"] == []
    assert state["status"] is RunStatus.RECEIVED
    assert state["run_meta"].thread_id == "octo/repo#42"
    assert state["run_meta"].max_iterations == 10
    assert state["run_meta"].max_cost_usd == 1.0
    assert state["run_meta"].iteration_count == 0


def test_checkpoint_serde_round_trip_on_initial_state():
    issue = make_issue()
    state = create_initial_state(issue, max_iterations=10, max_cost_usd=1.0)

    serializer = JsonPlusSerializer()
    type_, payload = serializer.dumps_typed(state)
    restored = serializer.loads_typed((type_, payload))

    assert restored == state


def test_checkpoint_serde_round_trip_on_fully_populated_state():
    state = make_fully_populated_state()

    serializer = JsonPlusSerializer()
    type_, payload = serializer.dumps_typed(state)
    restored = serializer.loads_typed((type_, payload))

    assert restored == state
