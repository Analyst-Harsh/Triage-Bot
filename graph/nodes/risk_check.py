from datetime import UTC, datetime
from typing import ClassVar

from graph.nodes.base import TriageNode
from graph.schemas import RiskAssessment, RiskLevel, RunStatus
from graph.state import TriageState, TriageStateUpdate


class RiskCheckNode(TriageNode):
    """Decides how much trust the drafted action deserves. Stub: always
    reports LOW risk (auto-post path) until the real risk logic is
    implemented."""

    name: ClassVar[str] = "risk_check"

    # `state` is unused in this stub; TriageNode.execute()'s signature
    # requires it (renaming breaks strict override typing, see base.py).
    def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        assessment = RiskAssessment(
            level=RiskLevel.LOW,
            score=0.0,
            risk_factors=[],
            reasoning="stub: risk check not yet implemented",
            requires_human_approval=False,
            assessed_at=datetime.now(UTC),
        )
        return TriageStateUpdate(risk_assessment=assessment, status=RunStatus.RISK_CHECK)
