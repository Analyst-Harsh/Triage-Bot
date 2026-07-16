from typing import Literal

from graph.nodes.node_names import NodeName
from graph.state import TriageState


def route_by_risk(state: TriageState) -> Literal[NodeName.AUTO_POST, NodeName.APPROVAL_QUEUE]:
    """Conditional-edge routing function for `risk_check`'s outgoing edge.

    Not a `TriageNode` — it makes a routing decision, it doesn't write state.
    """
    risk_assessment = state["risk_assessment"]
    if risk_assessment is None:
        raise ValueError("route_by_risk called before risk_assessment was set")
    if risk_assessment.requires_human_approval:
        return NodeName.APPROVAL_QUEUE
    return NodeName.AUTO_POST
