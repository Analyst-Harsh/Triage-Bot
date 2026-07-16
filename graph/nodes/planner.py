from datetime import UTC, datetime
from typing import ClassVar

from graph.nodes.base import TriageNode
from graph.schemas import IssueType, PlannerOutput, RunStatus
from graph.state import TriageState, TriageStateUpdate


class PlannerNode(TriageNode):
    """Reads the raw issue and classifies it. Stub: hardcodes a BUG
    classification until the real planning logic is implemented."""

    name: ClassVar[str] = "planner"

    # `state` is unused in this stub; TriageNode.execute()'s signature
    # requires it (renaming breaks strict override typing, see base.py).
    def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        output = PlannerOutput(
            issue_type=IssueType.BUG,
            classification_confidence=0.0,
            investigation_plan=[],
            reasoning="stub: planner not yet implemented",
            classified_at=datetime.now(UTC),
        )
        return TriageStateUpdate(planner_output=output, status=RunStatus.PLANNING)
