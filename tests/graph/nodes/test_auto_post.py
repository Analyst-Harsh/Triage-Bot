from graph.nodes.auto_post import AutoPostNode
from graph.schemas import RunStatus
from graph.state import TriageState


async def test_execute_returns_auto_posted_status(triage_state: TriageState) -> None:
    node = AutoPostNode()
    update = await node.execute(triage_state)

    assert "status" in update
    assert update["status"] == RunStatus.AUTO_POSTED


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    node = AutoPostNode()
    update = await node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].iteration_count == 1
