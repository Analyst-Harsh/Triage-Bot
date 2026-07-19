from datetime import UTC, datetime
from typing import ClassVar

from graph.nodes.base import TriageNode
from graph.nodes.node_names import NodeName
from graph.schemas import CommentAction, DraftOutput, RunStatus
from graph.state import TriageState, TriageStateUpdate


class DrafterNode(TriageNode):
    """Writes the actual response action. Stub: always drafts a placeholder
    comment until the real drafting logic (and sandboxed code-fix path) is
    implemented.

    Open question for the sandboxed code-fix path (`CodeFixAction`, see
    `graph/schemas/actions.py`): does verifying a fix need an iterative
    LLM tool-calling loop (propose diff -> run tests via a bound tool ->
    see failure -> revise -> retry)? If so it's structurally identical to
    the Researcher's tool-calling loop and should reuse the same
    abstraction: a second `AgentSubgraph` subclass (see
    `graph/nodes/agent_subgraph.py` and `graph/nodes/researcher.py`), with
    its own private trajectory channel — never top-level `TriageState`, see
    `AgentLoopState`'s docstring for why. Or is a single procedural sandbox
    run enough (generate one diff, run it once, capture pass/fail)? If so
    this stays a plain `TriageNode`, and can still reuse
    `graph/nodes/trajectory.py`'s helpers directly.
    `CodeFixAction.sandbox_result` is currently a single flat
    `SandboxResult`, not a `list[SandboxResult]`, which fits the
    single-shot reading — but that shape hasn't been deliberately chosen
    with this question in mind, so don't treat it as a decision already
    made. Resolve this when this node's real implementation lands.
    """

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
