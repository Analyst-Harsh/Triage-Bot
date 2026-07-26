from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

import pytest

from graph.nodes.spam_rejected import SpamRejectedNode
from graph.schemas import IssueType, PlannerOutput, RunStatus
from graph.state import TriageState
from utils.episodic_memory_store import BaseEpisodicMemoryStore


def make_memory_store_stub() -> Any:
    return create_autospec(BaseEpisodicMemoryStore, instance=True, spec_set=True)


def make_planner_output(**overrides: Any) -> PlannerOutput:
    defaults: dict[str, Any] = {
        "issue_type": IssueType.SPAM_OR_ABUSE,
        "classification_confidence": 0.95,
        "investigation_plan": [],
        "reasoning": "Issue body is unrelated promotional content.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)


def _with_dry_run(state: TriageState, *, dry_run: bool) -> TriageState:
    state["run_meta"] = state["run_meta"].model_copy(update={"dry_run": dry_run})
    return state


async def test_execute_sets_status_rejected(triage_state: TriageState) -> None:
    triage_state["planner_output"] = make_planner_output()
    memory_store = make_memory_store_stub()
    node = SpamRejectedNode(memory_store)

    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.REJECTED


async def test_execute_raises_without_planner_output(triage_state: TriageState) -> None:
    node = SpamRejectedNode(make_memory_store_stub())

    with pytest.raises(ValueError, match="planner_output"):
        await node.execute(triage_state)


async def test_writes_episode_when_not_dry_run(triage_state: TriageState) -> None:
    triage_state["planner_output"] = make_planner_output()
    _with_dry_run(triage_state, dry_run=False)
    memory_store = make_memory_store_stub()
    node = SpamRejectedNode(memory_store)

    await node.execute(triage_state)

    memory_store.save_episode.assert_awaited_once()
    call_kwargs = memory_store.save_episode.await_args.kwargs
    assert call_kwargs["outcome"] == RunStatus.REJECTED
    assert call_kwargs["run_id"] == triage_state["run_meta"].run_id
    assert call_kwargs["draft_actions"] == []
    assert call_kwargs["risk_assessment"] is None
    assert call_kwargs["post_results"] is None


async def test_does_not_write_episode_when_dry_run(triage_state: TriageState) -> None:
    triage_state["planner_output"] = make_planner_output()
    memory_store = make_memory_store_stub()
    node = SpamRejectedNode(memory_store)

    await node.execute(triage_state)

    memory_store.save_episode.assert_not_awaited()
