from pydantic import BaseModel, JsonValue

from graph.nodes.node_names import NodeName
from graph.schemas import ToolCallRecord


class ReconstructedTrajectory(BaseModel):
    """The raw tool-calling trajectory for one `AgentSubgraph` node
    (Researcher or Drafter), reconstructed from the latest same-named CHAIN
    observation in a trace. `messages` are stored as plain dicts -- each one
    a flat `model_dump()` of a real `langchain_core.messages` object
    (confirmed against a real trace: `{"type": "ai", "tool_calls": [...]}`
    etc., already in LangChain's own native shape) -- converted back into
    real `BaseMessage` objects at grader/judge call time via
    `evals.langfuse_fetch.reconstruct`'s type-keyed dispatch, not re-adapted
    here."""

    node_name: NodeName
    messages: list[JsonValue]
    tool_call_records: list[ToolCallRecord]
