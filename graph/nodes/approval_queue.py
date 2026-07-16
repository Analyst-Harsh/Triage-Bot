from typing import ClassVar

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.schemas import RunStatus
from graph.state import TriageState, TriageStateUpdate


class ApprovalQueueNode(TriageNode):
    """Terminal node for risky actions: waits for human approval. Stub: no
    queueing side effect yet, just marks the run as pending approval."""

    name: ClassVar[NodeName] = NodeName.APPROVAL_QUEUE

    # `state` is unused in this stub; TriageNode.execute()'s signature
    # requires it (renaming breaks strict override typing, see base.py).
    async def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        return TriageStateUpdate(status=RunStatus.PENDING_APPROVAL)
