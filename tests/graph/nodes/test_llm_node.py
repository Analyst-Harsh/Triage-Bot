from typing import ClassVar

import pytest
from pydantic import BaseModel

from graph.nodes.llm_node import LLMNode
from graph.nodes.node_names import NodeName
from graph.state import TriageState, TriageStateUpdate
from llm.config import LLMEndpointConfig, NodeLLMConfig
from tests.graph.nodes.conftest import FakeStructuredChatModel, make_fake_chat_model


class _Answer(BaseModel):
    value: str


class _StubLLMNode(LLMNode):
    """Test double: overrides `__init__` (inherited from `LLMNode`, which
    normally builds its own models from `self.llm_config` + `Settings`) to
    accept chat models directly — this file only exercises
    `call_structured()` in isolation, never real `Settings`."""

    name: ClassVar[NodeName] = NodeName.PLANNER
    llm_config: ClassVar[NodeLLMConfig] = NodeLLMConfig(
        primary=LLMEndpointConfig(provider="openai", model="gpt-4o-mini"),
        fallback=LLMEndpointConfig(provider="anthropic", model="claude-haiku-4-5-20251001"),
    )

    def __init__(
        self, primary_model: FakeStructuredChatModel, fallback_model: FakeStructuredChatModel
    ) -> None:
        self._primary_model = primary_model
        self._fallback_model = fallback_model

    async def execute(self, state: TriageState) -> TriageStateUpdate:  # noqa: ARG002
        return TriageStateUpdate()


async def test_call_structured_returns_parsed_result_from_primary() -> None:
    primary = make_fake_chat_model(
        model_name="primary-model", parsed_result=_Answer(value="from primary")
    )
    fallback = make_fake_chat_model(model_name="fallback-model")
    node = _StubLLMNode(primary_model=primary, fallback_model=fallback)

    result = await node.call_structured([], _Answer)

    assert result.parsed == _Answer(value="from primary")
    assert result.models_invoked == ["primary-model"]


async def test_call_structured_computes_cost_from_usage() -> None:
    primary = make_fake_chat_model(
        model_name="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=1000,
        parsed_result=_Answer(value="x"),
    )
    fallback = make_fake_chat_model(model_name="claude-haiku-4-5-20251001")
    node = _StubLLMNode(primary_model=primary, fallback_model=fallback)

    result = await node.call_structured([], _Answer)

    assert result.total_input_tokens == 1000
    assert result.total_output_tokens == 1000
    # gpt-4o-mini: $0.15/$0.60 per Mtok -> 1000 tokens each = 0.00015 + 0.0006
    assert result.estimated_cost_usd == pytest.approx(0.00075)


async def test_call_structured_falls_back_on_primary_api_error() -> None:
    primary = make_fake_chat_model(model_name="primary-model", raise_on_generate=True)
    fallback = make_fake_chat_model(
        model_name="fallback-model", parsed_result=_Answer(value="from fallback")
    )
    node = _StubLLMNode(primary_model=primary, fallback_model=fallback)

    result = await node.call_structured([], _Answer)

    assert result.parsed == _Answer(value="from fallback")
    assert result.models_invoked == ["fallback-model"]


async def test_call_structured_falls_back_on_primary_parsing_failure() -> None:
    """The scenario `include_raw=False` specifically targets: the primary
    gets a real response (burning tokens) but fails to parse it into the
    schema — this must still trigger the fallback, not just a raw API
    error."""
    primary = make_fake_chat_model(model_name="primary-model", fail_parse=True)
    fallback = make_fake_chat_model(
        model_name="fallback-model", parsed_result=_Answer(value="from fallback")
    )
    node = _StubLLMNode(primary_model=primary, fallback_model=fallback)

    result = await node.call_structured([], _Answer)

    assert result.parsed == _Answer(value="from fallback")


async def test_call_structured_sums_cost_across_primary_and_fallback() -> None:
    """Every attempt that burns tokens before failing to parse must still be
    counted — its tokens were real spend, not free retries. `fail_parse=True`
    fails unconditionally, so primary exhausts both of its in-place repair
    attempts (call_structured's `_STRUCTURED_OUTPUT_MAX_ATTEMPTS`) before
    falling back, contributing 2x its per-attempt tokens/cost."""
    primary = make_fake_chat_model(
        model_name="gpt-4o-mini", input_tokens=1000, output_tokens=1000, fail_parse=True
    )
    fallback = make_fake_chat_model(
        model_name="claude-haiku-4-5-20251001",
        input_tokens=1000,
        output_tokens=1000,
        parsed_result=_Answer(value="from fallback"),
    )
    node = _StubLLMNode(primary_model=primary, fallback_model=fallback)

    result = await node.call_structured([], _Answer)

    assert result.models_invoked == ["gpt-4o-mini", "claude-haiku-4-5-20251001"]
    assert result.total_input_tokens == 3000
    assert result.total_output_tokens == 3000
    # 2x gpt-4o-mini (0.00015 + 0.0006) + 1x claude-haiku-4-5 (0.001 + 0.005)
    assert result.estimated_cost_usd == pytest.approx(0.0075)
