"""Validates the mechanism BudgetGuardMiddleware depends on before trusting
it in production: a middleware's own `state_schema` can declare a key
(`run_meta`) already owned by the *parent* graph (`AgentLoopState`), not just
middleware-private state (the only pattern this codebase's one existing
precedent, `ModelCallLimitMiddleware`'s `ModelCallLimitState`, actually
uses). Exercises the real nested-subgraph topology `AgentSubgraph.compile()`
produces -- a `create_agent`-built graph registered as a node inside an
outer `StateGraph` -- rather than only unit-testing `abefore_model` in
isolation, since the thing being verified is specifically whether
`run_meta` flows across that subgraph boundary."""

from typing import Annotated, Any, TypedDict

import pytest
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.messages.ai import UsageMetadata
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

from graph.errors import BudgetExceededError
from graph.nodes.utils.budget_guard_middleware import BudgetGuardMiddleware
from tests.graph.schemas.test_run_meta import make_run_meta


class _OuterState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    run_meta: Any


def _build_outer_graph(*, node_name: str = "test_node") -> CompiledStateGraph[Any]:
    usage: UsageMetadata = {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="hi", usage_metadata=usage, response_metadata={})]
    )
    inner_agent = create_agent(
        model, tools=[], middleware=[BudgetGuardMiddleware(node_name=node_name)]
    )

    outer = StateGraph(_OuterState)
    outer.add_node("agent", inner_agent)  # pyright: ignore[reportUnknownMemberType]
    outer.add_edge(START, "agent")
    outer.add_edge("agent", END)
    return outer.compile()  # pyright: ignore[reportUnknownMemberType]


async def test_budget_guard_middleware_allows_call_when_well_under_budget() -> None:
    graph = _build_outer_graph()
    run_meta = make_run_meta(estimated_cost_usd=0.0, max_cost_usd=1.0)

    result = await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
        {"messages": [HumanMessage(content="hello")], "run_meta": run_meta}
    )

    assert result["run_meta"] == run_meta


async def test_budget_guard_middleware_raises_when_already_at_ceiling() -> None:
    """Proves `run_meta` set on the OUTER graph's initial state is visible
    inside the INNER `create_agent`-compiled subgraph's own middleware --
    the exact cross-subgraph-boundary mechanism `BudgetGuardMiddleware`
    depends on in production (`AgentSubgraph._middleware()`)."""
    graph = _build_outer_graph(node_name="researcher")
    run_meta = make_run_meta(estimated_cost_usd=1.0, max_cost_usd=1.0)

    with pytest.raises(BudgetExceededError) as exc_info:
        await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            {"messages": [HumanMessage(content="hello")], "run_meta": run_meta}
        )

    assert exc_info.value.node_name == "researcher"
    assert exc_info.value.dimension == "cost_usd"


async def test_budget_guard_middleware_raises_when_trajectory_would_push_over_budget() -> None:
    """A run under budget at subgraph entry, but whose in-flight trajectory
    (already-completed model turns this same loop invocation made) would
    push it over -- the specific mid-loop overrun the per-node-entry
    `check_budget` call can't see, which is this middleware's whole reason
    to exist."""
    usage: UsageMetadata = {
        "input_tokens": 10_000_000,
        "output_tokens": 5_000_000,
        "total_tokens": 15_000_000,
    }
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="hi", usage_metadata=usage, response_metadata={})]
    )
    inner_agent = create_agent(
        model, tools=[], middleware=[BudgetGuardMiddleware(node_name="drafter")]
    )
    outer = StateGraph(_OuterState)
    outer.add_node("agent", inner_agent)  # pyright: ignore[reportUnknownMemberType]
    outer.add_edge(START, "agent")
    outer.add_edge("agent", END)
    graph = outer.compile()  # pyright: ignore[reportUnknownMemberType]

    # A prior turn in this same trajectory already made a huge, expensive
    # call -- well under run_meta.estimated_cost_usd (which only reflects
    # *completed node* totals), but the projected trajectory cost trips the
    # middleware before a second turn is allowed.
    prior_expensive_message = AIMessage(
        content="",
        usage_metadata=usage,
        response_metadata={"model_name": "gpt-4o"},
    )
    run_meta = make_run_meta(estimated_cost_usd=0.0, max_cost_usd=0.01)

    with pytest.raises(BudgetExceededError) as exc_info:
        await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            {
                "messages": [HumanMessage(content="hello"), prior_expensive_message],
                "run_meta": run_meta,
            }
        )

    assert exc_info.value.dimension == "cost_usd"
