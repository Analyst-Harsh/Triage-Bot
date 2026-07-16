from graph.nodes.researcher import ResearcherNode
from graph.schemas import RunStatus
from graph.state import TriageState


async def test_execute_appends_stub_message(triage_state: TriageState) -> None:
    node = ResearcherNode()
    update = await node.execute(triage_state)

    assert "messages" in update
    assert len(update["messages"]) == 1
    assert update["messages"][0].content == "no research done"


async def test_execute_returns_stub_findings(triage_state: TriageState) -> None:
    node = ResearcherNode()
    update = await node.execute(triage_state)

    assert "research_findings" in update
    assert update["research_findings"] is not None
    assert "status" in update
    assert update["status"] == RunStatus.RESEARCHING


async def test_call_bumps_iteration_count(triage_state: TriageState) -> None:
    node = ResearcherNode()
    update = await node(triage_state)

    assert "run_meta" in update
    assert update["run_meta"].iteration_count == 1
