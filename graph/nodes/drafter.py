from datetime import UTC, datetime
from typing import ClassVar

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.schemas import CommentAction, DraftOutput, RunStatus
from graph.state import TriageState, TriageStateUpdate


class DrafterNode(TriageNode):
    """Writes the actual response action. Stub: always drafts a placeholder
    comment until the real drafting logic (and sandboxed code-fix path) is
    implemented."""

    name: ClassVar[NodeName] = NodeName.DRAFTER

    # `state` is unused in this stub; TriageNode.execute()'s signature
    # requires it (renaming breaks strict override typing, see base.py).
    async def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        draft = DraftOutput(
            action=CommentAction(comment_body="stub: drafter not yet implemented"),
            rationale="stub: drafter not yet implemented",
            drafted_at=datetime.now(UTC),
        )
        return TriageStateUpdate(draft=draft, status=RunStatus.DRAFTING)
