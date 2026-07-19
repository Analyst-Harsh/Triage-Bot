from collections.abc import Sequence
from typing import cast

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pydantic import JsonValue

from graph.schemas import ToolCallRecord
from llm.pricing import estimate_cost_usd


def derive_tool_call_records(messages: Sequence[BaseMessage]) -> list[ToolCallRecord]:
    """Walks a tool-calling trajectory and derives one `ToolCallRecord` per
    actual tool invocation, by matching each `AIMessage.tool_calls` entry to
    its corresponding `ToolMessage` (via `tool_call_id`).

    Programmatic, not LLM-authored — see `ToolCallRecord`'s docstring for
    why. A tool call with no matching `ToolMessage` (a loop cut short by the
    tool-call cap, e.g.) is skipped: it never actually ran.
    """
    tool_results = {msg.tool_call_id: msg for msg in messages if isinstance(msg, ToolMessage)}
    records: list[ToolCallRecord] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        for call in msg.tool_calls:
            call_id = call["id"]
            result = tool_results.get(call_id) if call_id is not None else None
            if result is None:
                continue
            status = "error" if result.status == "error" else "success"
            records.append(
                ToolCallRecord(
                    tool_name=call["name"],
                    arguments=cast(dict[str, JsonValue], call["args"]),
                    status=status,
                )
            )
    return records


def estimate_trajectory_cost(messages: Sequence[BaseMessage]) -> float:
    """Sums the cost of every model call in a trajectory, reading each
    `AIMessage`'s own `usage_metadata` (populated by the provider on the raw
    API response) rather than requiring a callback — the trajectory is
    inspected after the fact, once the loop has already finished."""
    total = 0.0
    for msg in messages:
        if not isinstance(msg, AIMessage) or not msg.usage_metadata:
            continue
        model_name = str(msg.response_metadata.get("model_name", ""))
        total += estimate_cost_usd(
            model_name,
            msg.usage_metadata["input_tokens"],
            msg.usage_metadata["output_tokens"],
        )
    return total
