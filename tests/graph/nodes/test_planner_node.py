from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

from graph.nodes.planner import PlannerNode
from graph.schemas import (
    ActionType,
    EpisodicActionOutcome,
    EpisodicMemoryHit,
    IssueType,
    PlannerClassification,
    PostOutcome,
    RunStatus,
)
from graph.state import TriageState
from tests.graph.nodes.conftest import (
    _FakePlannerNode,  # pyright: ignore[reportPrivateUsage]
    make_fake_chat_model,
    make_fake_planner_node,
)
from utils.episodic_memory_store import BaseEpisodicMemoryStore, EpisodicMemoryUnavailableError


def _make_node(classification: PlannerClassification) -> PlannerNode:
    return make_fake_planner_node(parsed_result=classification)


def make_hit(**overrides: Any) -> EpisodicMemoryHit:
    defaults: dict[str, Any] = {
        "past_issue_number": 17,
        "past_repo": "octo/repo",
        "summary": "Similar startup crash last month.",
        "actions_taken": [
            EpisodicActionOutcome(action_type=ActionType.COMMENT, outcome=PostOutcome.POSTED)
        ],
        "outcome": RunStatus.APPROVED_AND_POSTED,
        "similarity_score": 0.91,
        "retrieved_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return EpisodicMemoryHit(**defaults)


def make_memory_store_stub(hits: list[EpisodicMemoryHit] | None = None) -> Any:
    store = create_autospec(BaseEpisodicMemoryStore, instance=True, spec_set=True)
    store.find_similar.return_value = hits or []
    return store


async def test_execute_classifies_bug_report(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=["search codebase for the referenced exception"],
        reasoning="Stack trace matches a known exception type.",
    )
    node = _make_node(classification)

    update = await node.execute(triage_state)

    assert "planner_output" in update
    output = update["planner_output"]
    assert output is not None
    assert output.issue_type == IssueType.BUG
    assert output.classification_confidence == 0.9
    assert output.investigation_plan == ["search codebase for the referenced exception"]
    assert output.classified_at is not None
    assert "status" in update
    assert update["status"] == RunStatus.PLANNING


async def test_execute_requests_json_schema_structured_output(
    triage_state: TriageState,
) -> None:
    """`PlannerClassification` has no discriminated union, so the Planner
    should opt into OpenAI's strict `json_schema` mode for a real
    provider-side conformance guarantee rather than `function_calling`'s
    best-effort bias."""
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Test double classification.",
    )
    primary = make_fake_chat_model(model_name="gpt-4o-mini", parsed_result=classification)
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    node = _FakePlannerNode(primary_model=primary, fallback_model=fallback)

    await node.execute(triage_state)

    assert primary.received_structured_output_kwargs == [{"method": "json_schema"}]


async def test_execute_classifies_feature_request(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.FEATURE_REQUEST,
        classification_confidence=0.75,
        investigation_plan=[],
        reasoning="Author is asking for new functionality, not reporting a defect.",
    )
    node = _make_node(classification)

    update = await node.execute(triage_state)

    assert "planner_output" in update
    output = update["planner_output"]
    assert output is not None
    assert output.issue_type == IssueType.FEATURE_REQUEST


async def test_execute_increases_estimated_cost(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    node = _make_node(classification)

    update = await node.execute(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.estimated_cost_usd > triage_state["run_meta"].estimated_cost_usd


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    node = _make_node(classification)

    update = await node(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.iteration_count == 1


async def test_execute_threads_cache_tokens_into_run_meta(triage_state: TriageState) -> None:
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    primary = make_fake_chat_model(
        model_name="gpt-4o-mini",
        parsed_result=classification,
        cache_read_tokens=800,
        cache_creation_tokens=50,
    )
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    node = _FakePlannerNode(primary, fallback)

    update = await node.execute(triage_state)

    assert "run_meta" in update
    run_meta = update["run_meta"]
    assert run_meta is not None
    assert run_meta.cache_read_tokens == triage_state["run_meta"].cache_read_tokens + 800
    assert run_meta.cache_creation_tokens == triage_state["run_meta"].cache_creation_tokens + 50


async def test_execute_includes_episodic_hits_in_prompt(triage_state: TriageState) -> None:
    hit = make_hit(summary="Similar startup crash last month, fix was rejected as too risky.")
    memory_store = make_memory_store_stub([hit])
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    primary = make_fake_chat_model(model_name="gpt-4o-mini", parsed_result=classification)
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    node = _FakePlannerNode(primary, fallback, memory_store=memory_store)

    update = await node.execute(triage_state)

    assert "episodic_context" in update
    assert update["episodic_context"] == [hit]
    memory_store.find_similar.assert_called_once()
    sent_messages = primary.received_messages[0]
    assert any("Similar startup crash last month" in str(m.content) for m in sent_messages)


async def test_execute_with_no_episodic_hits_still_succeeds(triage_state: TriageState) -> None:
    memory_store = make_memory_store_stub([])
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    node = make_fake_planner_node(parsed_result=classification, memory_store=memory_store)

    update = await node.execute(triage_state)

    assert "episodic_context" in update
    assert update["episodic_context"] == []
    assert "status" in update
    assert update["status"] == RunStatus.PLANNING


async def test_execute_degrades_gracefully_when_memory_store_unavailable(
    triage_state: TriageState,
) -> None:
    memory_store = make_memory_store_stub()
    memory_store.find_similar.side_effect = EpisodicMemoryUnavailableError("connection refused")
    classification = PlannerClassification(
        issue_type=IssueType.BUG,
        classification_confidence=0.9,
        investigation_plan=[],
        reasoning="Reasoning.",
    )
    node = make_fake_planner_node(parsed_result=classification, memory_store=memory_store)

    update = await node.execute(triage_state)

    assert "episodic_context" in update
    assert update["episodic_context"] == []
    assert "status" in update
    assert update["status"] == RunStatus.PLANNING
    assert "planner_output" in update
    output = update["planner_output"]
    assert output is not None
    assert output.issue_type == IssueType.BUG
