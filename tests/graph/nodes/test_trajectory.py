from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from graph.nodes.trajectory import derive_tool_call_records, estimate_trajectory_cost


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
