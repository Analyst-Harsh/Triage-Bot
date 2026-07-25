from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from langgraph.store.base import SearchItem
from openai import APIConnectionError

from graph.schemas import (
    ActionType,
    CommentAction,
    DraftedAction,
    IssuePayload,
    IssueSource,
    IssueType,
    PlannerOutput,
    PostOutcome,
    PostResults,
    RiskAssessment,
    RiskLevel,
    RunStatus,
)
from graph.schemas.risk import ActionRiskAssessment
from utils.episodic_memory_store import (
    EpisodicMemoryStore,
    EpisodicMemoryUnavailableError,
    NullEpisodicMemoryStore,
)


def make_issue(**overrides: Any) -> IssuePayload:
    defaults: dict[str, Any] = {
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "title": "Crash on startup",
        "body": "App crashes with a NoneType error.",
        "author": "octocat",
        "created_at": datetime.now(UTC),
        "url": "https://github.com/octo/repo/issues/42",
        "source": IssueSource.WEBHOOK,
    }
    defaults.update(overrides)
    return IssuePayload(**defaults)


def make_planner_output(**overrides: Any) -> PlannerOutput:
    defaults: dict[str, Any] = {
        "issue_type": IssueType.BUG,
        "classification_confidence": 0.9,
        "investigation_plan": [],
        "reasoning": "Test reasoning.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)


def make_risk_assessment() -> RiskAssessment:
    return RiskAssessment(
        action_assessments=[
            ActionRiskAssessment(level=RiskLevel.LOW, risk_factors=[], reasoning="Test.")
        ],
        assessed_at=datetime.now(UTC),
    )


def make_draft_actions() -> list[DraftedAction]:
    return [
        DraftedAction(action=CommentAction(comment_body="Thanks!"), rationale="Acknowledge report.")
    ]


def make_post_results(**overrides: Any) -> PostResults:
    defaults: dict[str, Any] = {
        "action_results": [{"outcome": PostOutcome.POSTED, "detail": "url"}],
        "evaluated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PostResults(**defaults)  # type: ignore[arg-type]


def make_value(**overrides: Any) -> dict[str, Any]:
    """A `SearchItem.value`-shaped dict, matching `Episode.model_dump(mode="json")`."""
    defaults: dict[str, Any] = {
        "run_id": str(uuid4()),
        "repo_full_name": "octo/repo",
        "issue_number": 17,
        "issue_summary": "Similar startup crash last month.",
        "issue_type": "bug",
        "issue_text": "Similar startup crash last month.\n\nFull body.",
        "actions_taken": [
            {
                "action": {"action_type": "comment", "comment_body": "Thanks!"},
                "rationale": "Acknowledge.",
            }
        ],
        "risk_levels": ["low"],
        "post_results": {
            "action_results": [{"outcome": "posted", "detail": "url"}],
            "evaluated_at": datetime.now(UTC).isoformat(),
        },
        "outcome": "auto_posted",
        "created_at": datetime.now(UTC).isoformat(),
    }
    defaults.update(overrides)
    return defaults


def make_search_item(**overrides: Any) -> SearchItem:
    value = overrides.pop("value", None) or make_value()
    defaults: dict[str, Any] = {
        "namespace": ("episodes", "octo/repo"),
        "key": value["run_id"],
        "value": value,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "score": 0.87,
    }
    defaults.update(overrides)
    return SearchItem(**defaults)


class _FakeAsyncPostgresStore:
    """Duck-typed stand-in for `AsyncPostgresStore`: `EpisodicMemoryStore`
    only ever calls `asearch`/`aput` on it."""

    def __init__(
        self, search_result: list[SearchItem] | None = None, *, raise_error: Exception | None = None
    ) -> None:
        self.search_result = search_result or []
        self.raise_error = raise_error
        self.asearch_calls: list[tuple[Any, ...]] = []
        self.aput_calls: list[tuple[Any, ...]] = []

    async def asearch(
        self, namespace_prefix: tuple[str, ...], *, query: str | None = None, limit: int = 10
    ) -> list[SearchItem]:
        self.asearch_calls.append((namespace_prefix, query, limit))
        if self.raise_error:
            raise self.raise_error
        return self.search_result

    async def aput(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        index: list[str] | None = None,
    ) -> None:
        self.aput_calls.append((namespace, key, value, index))
        if self.raise_error:
            raise self.raise_error


def make_store(
    search_result: list[SearchItem] | None = None, *, raise_error: Exception | None = None
) -> tuple[EpisodicMemoryStore, _FakeAsyncPostgresStore]:
    fake = _FakeAsyncPostgresStore(search_result, raise_error=raise_error)
    store = EpisodicMemoryStore(fake, namespace_prefix=("episodes",))  # type: ignore[arg-type]
    return store, fake


async def test_find_similar_passes_correct_namespace_query_limit() -> None:
    store, fake = make_store(search_result=[make_search_item()])

    await store.find_similar(make_issue(), top_k=3)

    namespace_prefix, query, limit = fake.asearch_calls[0]
    assert namespace_prefix == ("episodes",)
    assert query == "Crash on startup\n\nApp crashes with a NoneType error."
    assert limit == 3


async def test_find_similar_maps_items_to_hits() -> None:
    store, _ = make_store(search_result=[make_search_item()])

    hits = await store.find_similar(make_issue(), top_k=3)

    assert len(hits) == 1
    hit = hits[0]
    assert hit.past_issue_number == 17
    assert hit.past_repo == "octo/repo"
    assert len(hit.actions_taken) == 1
    assert hit.actions_taken[0].action_type == ActionType.COMMENT
    assert hit.actions_taken[0].outcome == PostOutcome.POSTED
    assert hit.outcome == RunStatus.AUTO_POSTED
    assert hit.similarity_score == 0.87


async def test_find_similar_folds_rejection_note_into_summary() -> None:
    value = make_value(
        post_results={
            "action_results": [{"outcome": "rejected", "detail": "Too risky right now."}],
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
    )
    store, _ = make_store(search_result=[make_search_item(value=value)])

    hits = await store.find_similar(make_issue(), top_k=3)

    assert "rejected by reviewer: Too risky right now." in hits[0].summary
    assert hits[0].actions_taken[0].outcome == PostOutcome.REJECTED


async def test_find_similar_clamps_similarity_score_to_valid_bounds() -> None:
    store, _ = make_store(search_result=[make_search_item(score=1.0000001)])

    hits = await store.find_similar(make_issue(), top_k=3)

    assert hits[0].similarity_score == 1.0


async def test_find_similar_handles_missing_score() -> None:
    store, _ = make_store(search_result=[make_search_item(score=None)])

    hits = await store.find_similar(make_issue(), top_k=3)

    assert hits[0].similarity_score == 0.0


async def test_find_similar_wraps_connection_error() -> None:
    store, _ = make_store(raise_error=psycopg.OperationalError("connection refused"))

    with pytest.raises(EpisodicMemoryUnavailableError):
        await store.find_similar(make_issue(), top_k=3)


async def test_find_similar_wraps_embedding_error() -> None:
    store, _ = make_store(raise_error=APIConnectionError(request=None))  # type: ignore[arg-type]

    with pytest.raises(EpisodicMemoryUnavailableError):
        await store.find_similar(make_issue(), top_k=3)


async def test_save_episode_calls_aput_with_namespace_key_value_index() -> None:
    store, fake = make_store()
    run_id = uuid4()

    await store.save_episode(
        run_id=run_id,
        issue=make_issue(),
        planner_output=make_planner_output(),
        draft_actions=make_draft_actions(),
        risk_assessment=make_risk_assessment(),
        post_results=make_post_results(),
        outcome=RunStatus.AUTO_POSTED,
    )

    namespace, key, value, index = fake.aput_calls[0]
    assert namespace == ("episodes", "octo/repo")
    assert key == str(run_id)
    assert value["run_id"] == str(run_id)
    assert value["issue_type"] == "bug"
    assert value["outcome"] == "auto_posted"
    assert value["issue_text"] == "Crash on startup\n\nApp crashes with a NoneType error."
    assert index == ["issue_text"]


async def test_save_episode_wraps_connection_error() -> None:
    store, _ = make_store(raise_error=psycopg.OperationalError("connection refused"))

    with pytest.raises(EpisodicMemoryUnavailableError):
        await store.save_episode(
            run_id=uuid4(),
            issue=make_issue(),
            planner_output=make_planner_output(),
            draft_actions=make_draft_actions(),
            risk_assessment=make_risk_assessment(),
            post_results=make_post_results(),
            outcome=RunStatus.AUTO_POSTED,
        )


async def test_null_store_find_similar_returns_empty() -> None:
    store = NullEpisodicMemoryStore()

    hits = await store.find_similar(make_issue(), top_k=3)

    assert hits == []


async def test_null_store_save_episode_is_a_no_op() -> None:
    store = NullEpisodicMemoryStore()

    await store.save_episode(
        run_id=uuid4(),
        issue=make_issue(),
        planner_output=make_planner_output(),
        draft_actions=make_draft_actions(),
        risk_assessment=make_risk_assessment(),
        post_results=make_post_results(),
        outcome=RunStatus.AUTO_POSTED,
    )
