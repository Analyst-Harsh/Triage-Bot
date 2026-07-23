from collections.abc import Sequence
from copy import deepcopy
from typing import cast

from langchain.agents.middleware import ClearToolUsesEdit
from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
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


def missing_tool_results(messages: Sequence[BaseMessage]) -> list[ToolMessage]:
    """Synthesizes a `ToolMessage` for every `AIMessage.tool_calls` entry
    that has no matching response in `messages`.

    This happens when `ToolCallLimitMiddleware` (`exit_behavior="end"`)
    blocks part of a parallel tool-call batch: it jumps straight to exit
    without ever reaching the tools node, so even the calls it counted as
    "allowed" never actually run and never get a `ToolMessage`. Left as-is,
    that dangling `tool_call_id` breaks the next model call outright — both
    OpenAI and Anthropic reject an assistant message with an unresolved
    tool call. Building block for `resolve_dangling_tool_calls`; see there
    for how these get placed back into a trajectory.
    """
    resolved_ids = {msg.tool_call_id for msg in messages if isinstance(msg, ToolMessage)}
    missing: list[ToolMessage] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        for call in msg.tool_calls:
            call_id = call["id"]
            if call_id is not None and call_id not in resolved_ids:
                missing.append(
                    ToolMessage(
                        content=(
                            "Tool call not executed: the tool-call limit was "
                            "reached before this call could run."
                        ),
                        tool_call_id=call_id,
                        name=call["name"],
                        status="error",
                    )
                )
    return missing


def resolve_dangling_tool_calls(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Returns a new trajectory with a synthetic `ToolMessage` (see
    `missing_tool_results`) spliced in immediately after the `AIMessage`
    that owns each unresolved tool call — i.e. exactly where a real
    `ToolMessage` would have landed, so every tool call is resolved before
    the next non-tool message. Simply appending the patches to the end (via
    the `messages` channel's `add_messages` reducer, say) would put them
    *after* whatever the loop already appended following that turn (e.g.
    `ToolCallLimitMiddleware`'s own synthetic message for a sibling blocked
    call, plus its final `AIMessage`) — still an invalid ordering for both
    OpenAI and Anthropic.

    Purely transient: used to build the message list handed to a fresh
    model call (`AgentSubgraph.summarize_node`) or to
    `derive_tool_call_records`. Never written back into the checkpointed
    `messages` channel — that stays a faithful record of what actually
    happened, cap included.
    """
    patches_by_call_id = {patch.tool_call_id: patch for patch in missing_tool_results(messages)}
    resolved: list[BaseMessage] = []
    for msg in messages:
        resolved.append(msg)
        if not isinstance(msg, AIMessage):
            continue
        for call in msg.tool_calls:
            call_id = call["id"]
            patch = patches_by_call_id.get(call_id) if call_id is not None else None
            if patch is not None:
                resolved.append(patch)
    return resolved


def clamp_trajectory_for_model_call(
    messages: Sequence[BaseMessage], *, trigger: int, keep: int, placeholder: str
) -> list[BaseMessage]:
    """Applies the same deterministic tool-result clearing
    `ContextEditingMiddleware`/`ClearToolUsesEdit` applies to every in-loop
    model call, to the one model call that sits outside that loop:
    `AgentSubgraph.summarize_node`'s structured-output pass.
    `ContextEditingMiddleware.wrap_model_call` only edits its ephemeral
    outgoing request -- it never persists into the graph's checkpointed
    `messages` channel, so `summarize_node` needs its own pass rather than
    inheriting the loop's.

    Operates on a deep copy: `ClearToolUsesEdit.apply` mutates its argument
    in place, and the input trajectory must stay untouched -- the
    checkpointed state stays a faithful, unpruned record either way (same
    "never written back" precedent as `resolve_dangling_tool_calls`).
    """
    edited = cast(list[AnyMessage], deepcopy(list(messages)))
    ClearToolUsesEdit(trigger=trigger, keep=keep, placeholder=placeholder).apply(
        edited, count_tokens=count_tokens_approximately
    )
    return cast(list[BaseMessage], edited)


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
