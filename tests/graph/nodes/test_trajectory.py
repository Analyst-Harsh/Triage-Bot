from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from graph.nodes.trajectory import (
    clamp_trajectory_for_model_call,
    derive_tool_call_records,
    estimate_trajectory_cost,
    missing_tool_results,
    resolve_dangling_tool_calls,
)


def make_ai_tool_call(
    tool_name: str, args: dict[str, object], call_id: str, **kwargs: object
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": call_id}],
        **kwargs,  # type: ignore[arg-type]
    )


def test_derive_tool_call_records_matches_ai_message_to_tool_message() -> None:
    messages = [
        HumanMessage(content="investigate"),
        make_ai_tool_call("search_code", {"query": "NoneType"}, "call_1"),
        ToolMessage(content="found it", tool_call_id="call_1", status="success"),
    ]

    records = derive_tool_call_records(messages)

    assert len(records) == 1
    assert records[0].tool_name == "search_code"
    assert records[0].arguments == {"query": "NoneType"}
    assert records[0].status == "success"


def test_derive_tool_call_records_marks_error_status() -> None:
    messages = [
        make_ai_tool_call("search_code", {"query": "x"}, "call_1"),
        ToolMessage(content="boom", tool_call_id="call_1", status="error"),
    ]

    records = derive_tool_call_records(messages)

    assert records[0].status == "error"


def test_derive_tool_call_records_skips_tool_calls_with_no_matching_result() -> None:
    """A tool call cut short by a cap (or otherwise never resolved) has no
    matching ToolMessage — it never actually ran, so it's not a record."""
    messages = [make_ai_tool_call("search_code", {"query": "x"}, "call_1")]

    records = derive_tool_call_records(messages)

    assert records == []


def test_derive_tool_call_records_preserves_order_across_multiple_calls() -> None:
    messages = [
        make_ai_tool_call("search_code", {"query": "a"}, "call_1"),
        ToolMessage(content="a result", tool_call_id="call_1", status="success"),
        make_ai_tool_call("web_search", {"query": "b"}, "call_2"),
        ToolMessage(content="b result", tool_call_id="call_2", status="success"),
    ]

    records = derive_tool_call_records(messages)

    assert [r.tool_name for r in records] == ["search_code", "web_search"]


def test_missing_tool_results_returns_empty_when_every_call_resolved() -> None:
    messages = [
        make_ai_tool_call("search_code", {"query": "a"}, "call_1"),
        ToolMessage(content="a result", tool_call_id="call_1", status="success"),
    ]

    assert missing_tool_results(messages) == []


def test_missing_tool_results_synthesizes_error_message_for_unresolved_call() -> None:
    """The scenario `ToolCallLimitMiddleware`'s `exit_behavior="end"` leaves
    behind: an "allowed" call from a parallel batch that never actually ran
    because the loop jumped straight to exit before reaching the tools
    node, so it never got a real `ToolMessage`."""
    messages = [make_ai_tool_call("search_code", {"query": "x"}, "call_1")]

    patches = missing_tool_results(messages)

    assert len(patches) == 1
    patch = patches[0]
    assert isinstance(patch, ToolMessage)
    assert patch.tool_call_id == "call_1"
    assert patch.name == "search_code"
    assert patch.status == "error"


def test_missing_tool_results_ignores_already_resolved_calls_in_mixed_batch() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search_code", "args": {}, "id": "call_1"},
                {"name": "web_search", "args": {}, "id": "call_2"},
            ],
        ),
        ToolMessage(content="a result", tool_call_id="call_1", status="success"),
    ]

    patches = missing_tool_results(messages)

    assert len(patches) == 1
    assert patches[0].tool_call_id == "call_2"


def test_resolve_dangling_tool_calls_returns_unchanged_when_nothing_dangling() -> None:
    messages = [
        make_ai_tool_call("search_code", {"query": "a"}, "call_1"),
        ToolMessage(content="a result", tool_call_id="call_1", status="success"),
    ]

    assert resolve_dangling_tool_calls(messages) == messages


def test_resolve_dangling_tool_calls_closes_the_gap_in_derive_tool_call_records() -> None:
    """Once the synthetic patch is spliced into the trajectory, the
    previously-dropped call becomes a proper (error) record instead of
    silently vanishing."""
    messages = [make_ai_tool_call("search_code", {"query": "x"}, "call_1")]

    records = derive_tool_call_records(resolve_dangling_tool_calls(messages))

    assert len(records) == 1
    assert records[0].tool_name == "search_code"
    assert records[0].status == "error"


def test_resolve_dangling_tool_calls_inserts_immediately_after_owning_ai_message() -> None:
    """The exact scenario `ToolCallLimitMiddleware`'s `exit_behavior="end"`
    produces: one call in a parallel batch gets blocked (real synthetic
    ToolMessage + a final AIMessage appended by the middleware itself)
    while a sibling call in the *same* AIMessage was "allowed" but never
    executed. Simply appending the missing patch at the very end would put
    it after the middleware's own trailing messages — still invalid for
    both OpenAI and Anthropic, which require every tool_call in an
    assistant message to be resolved before the next non-tool message.
    """
    turn = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_code", "args": {}, "id": "allowed_call"},
            {"name": "web_search", "args": {}, "id": "blocked_call"},
        ],
    )
    blocked_result = ToolMessage(
        content="Tool call limit exceeded.", tool_call_id="blocked_call", status="error"
    )
    final = AIMessage(content="Tool call limit reached.")
    messages = [turn, blocked_result, final]

    resolved = resolve_dangling_tool_calls(messages)

    assert resolved[0] is turn
    assert isinstance(resolved[1], ToolMessage)
    assert resolved[1].tool_call_id == "allowed_call"
    assert resolved[2] is blocked_result
    assert resolved[3] is final


def test_estimate_trajectory_cost_sums_ai_message_usage() -> None:
    messages = [
        AIMessage(
            content="",
            usage_metadata={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
            response_metadata={"model_name": "gpt-4o-mini"},
        ),
        AIMessage(
            content="done",
            usage_metadata={"input_tokens": 200, "output_tokens": 50, "total_tokens": 250},
            response_metadata={"model_name": "gpt-4o-mini"},
        ),
    ]

    cost = estimate_trajectory_cost(messages)

    assert cost > 0.0


def test_estimate_trajectory_cost_ignores_messages_without_usage_metadata() -> None:
    messages = [HumanMessage(content="hi"), AIMessage(content="no usage data here")]

    cost = estimate_trajectory_cost(messages)

    assert cost == 0.0


def test_estimate_trajectory_cost_unmapped_model_contributes_zero() -> None:
    messages = [
        AIMessage(
            content="",
            usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            response_metadata={"model_name": "not-a-real-model"},
        )
    ]

    cost = estimate_trajectory_cost(messages)

    assert cost == 0.0


def make_tool_call_pair(index: int, content: str) -> list[AIMessage | ToolMessage]:
    return [
        make_ai_tool_call("read_file", {"path": f"f{index}.py"}, f"call_{index}"),
        ToolMessage(content=content, tool_call_id=f"call_{index}", status="success"),
    ]


def test_clamp_trajectory_for_model_call_noop_under_trigger() -> None:
    messages = [
        *make_tool_call_pair(0, "short result"),
        *make_tool_call_pair(1, "another short result"),
    ]

    clamped = clamp_trajectory_for_model_call(
        messages, trigger=1_000_000, keep=1, placeholder="[cleared]"
    )

    assert [m.content for m in clamped] == [m.content for m in messages]


def test_clamp_trajectory_for_model_call_clears_oldest_beyond_keep() -> None:
    contents = [f"result-{i}-" + ("x" * 200) for i in range(5)]
    messages: list[AIMessage | ToolMessage] = []
    for i, content in enumerate(contents):
        messages.extend(make_tool_call_pair(i, content))

    clamped = clamp_trajectory_for_model_call(messages, trigger=10, keep=2, placeholder="[cleared]")

    assert len(clamped) == len(messages)  # replaced in place, never removed
    clamped_tool_messages = [m for m in clamped if isinstance(m, ToolMessage)]
    assert [m.content for m in clamped_tool_messages[:3]] == ["[cleared]"] * 3
    assert [m.content for m in clamped_tool_messages[3:]] == contents[3:]


def test_clamp_trajectory_for_model_call_does_not_mutate_input() -> None:
    contents = [f"result-{i}-" + ("x" * 200) for i in range(5)]
    messages: list[AIMessage | ToolMessage] = []
    for i, content in enumerate(contents):
        messages.extend(make_tool_call_pair(i, content))

    clamp_trajectory_for_model_call(messages, trigger=10, keep=2, placeholder="[cleared]")

    original_tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.content for m in original_tool_messages] == contents


def test_clamp_trajectory_for_model_call_skips_tool_messages_with_no_matching_ai_message() -> None:
    """A dangling `ToolMessage` with no preceding `AIMessage` owning its
    `tool_call_id` (the shape `missing_tool_results` can produce before
    `resolve_dangling_tool_calls` splices it back next to its real owner)
    is left untouched rather than raising."""
    orphan_content = "orphaned result " + ("z" * 200)
    messages = [ToolMessage(content=orphan_content, tool_call_id="orphan_call", status="error")]

    clamped = clamp_trajectory_for_model_call(messages, trigger=1, keep=0, placeholder="[cleared]")

    assert len(clamped) == 1
    assert clamped[0].content == orphan_content
