from typing import ClassVar

from langchain_core.messages import AIMessage

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.schemas import ResearchFindings, RunStatus
from graph.state import TriageState, TriageStateUpdate


class ResearcherNode(TriageNode):
    """Searches the codebase, docs, and web for context on the issue. Stub:
    does no real research, just appends a placeholder trajectory message.

    Open question: top level messages is scoped for tool calls of this node
    but other nodes will also have tool calls which makes this ambiguous
    so need to think about how to scope messages and research findings.
    """

    name: ClassVar[NodeName] = NodeName.RESEARCHER

    # `state` is unused in this stub; TriageNode.execute()'s signature
    # requires it (renaming breaks strict override typing, see base.py).
    async def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
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
