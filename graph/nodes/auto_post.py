from typing import ClassVar

from graph.nodes.base import TriageNode
from graph.schemas import RunStatus
from graph.state import TriageState, TriageStateUpdate


class AutoPostNode(TriageNode):
    """Terminal node for low-risk actions: posts immediately. Stub: no
    posting side effect yet, just marks the run as auto-posted."""

    name: ClassVar[str] = "auto_post"

    # `state` is unused in this stub; TriageNode.execute()'s signature
    # requires it (renaming breaks strict override typing, see base.py).
    def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        return TriageStateUpdate(status=RunStatus.AUTO_POSTED)
