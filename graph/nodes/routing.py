from typing import Literal

from graph.nodes.node_names import NodeName
from graph.schemas import RiskLevel
from graph.state import TriageState


def route_by_risk(state: TriageState) -> Literal[NodeName.AUTO_POST, NodeName.APPROVAL_QUEUE]:
    """Conditional-edge routing function for `risk_check`'s outgoing edge.

    Not a `TriageNode` — it makes a routing decision, it doesn't write state.

    Whole-draft binary decision for now: any action above LOW sends the
    entire run to `approval_queue`. Routing each action independently
    (auto-posting the low-risk ones while pausing only for the rest, via
    LangGraph's `interrupt()`) is deliberately out of scope here -- tracked
    as follow-up work once `risk_check` itself produces per-action verdicts
    (see `RiskCheckNode`/`RiskAssessment.action_assessments`).
    """
    risk_assessment = state["risk_assessment"]
    if risk_assessment is None:
        raise ValueError("route_by_risk called before risk_assessment was set")
    if any(assessment.level != RiskLevel.LOW for assessment in risk_assessment.action_assessments):
        return NodeName.APPROVAL_QUEUE
    return NodeName.AUTO_POST
