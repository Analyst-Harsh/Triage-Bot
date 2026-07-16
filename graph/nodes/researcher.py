from typing import ClassVar

from langchain_core.messages import AIMessage

from graph.nodes.base import TriageNode
from graph.schemas import ResearchFindings, RunStatus
from graph.state import TriageState, TriageStateUpdate


class ResearcherNode(TriageNode):
    """Searches the codebase, docs, and web for context on the issue. Stub:
    does no real research, just appends a placeholder trajectory message."""

    name: ClassVar[str] = "researcher"

    # `state` is unused in this stub; TriageNode.execute()'s signature
    # requires it (renaming breaks strict override typing, see base.py).
    def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        findings = ResearchFindings(
            summary="stub: researcher not yet implemented",
            sources=[],
            code_references=[],
            confidence=0.0,
            open_questions=[],
        )
        return TriageStateUpdate(
            messages=[AIMessage(content="no research done")],
            research_findings=findings,
            status=RunStatus.RESEARCHING,
        )
