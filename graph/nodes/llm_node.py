from abc import ABC
from collections.abc import Sequence
from typing import ClassVar, cast

from langchain_core.callbacks.usage import get_usage_metadata_callback
from langchain_core.messages import BaseMessage

from config.settings import get_settings
from graph.nodes.base import TriageNode
from llm.config import NodeLLMConfig
from llm.factory import create_chat_model
from llm.pricing import estimate_cost_usd
from llm.result import LLMResult


class LLMNode(TriageNode, ABC):
    """Shared seam for every LLM-backed node: call a model for structured
    output, with an automatic cross-provider fallback and cost accounting,
    without each concrete node re-deriving it.

    `execute()` stays abstract, inherited from `TriageNode` — this class
    only adds `call_structured()`.
    """

    llm_config: ClassVar[NodeLLMConfig]
    """Primary/fallback model choice for this node. Set on the concrete
    subclass"""

    def __init__(self) -> None:
        """Self-contained: builds its own primary/fallback chat models from
        `self.llm_config` + the global `Settings`, so a concrete node
        constructs with zero args, exactly like every other `TriageNode`
        (e.g. `ResearcherNode()`). Tests that need fake models inject them
        via a test-only subclass overriding `__init__` (see
        `tests/graph/nodes/conftest.py`), not via constructor params here —
        keeping this the one, unambiguous production construction path."""
        settings = get_settings()
        self._primary_model = create_chat_model(self.llm_config.primary, settings)
        self._fallback_model = create_chat_model(self.llm_config.fallback, settings)

    async def call_structured[T](
        self, messages: Sequence[BaseMessage], schema: type[T]
    ) -> LLMResult[T]:
        """Calls the primary model for `schema`-shaped structured output,
        falling back to the secondary model on ANY failure — a raw API
        error (rate limit, timeout, ...) or a structured-output parsing
        failure alike.

        Deliberately does NOT pass `include_raw=True`: with the default
        `include_raw=False`, a parsing failure is *raised* rather than
        swallowed into a result dict, which is what lets `.with_fallbacks()`
        (whose default `exceptions_to_handle` is `(Exception,)`) actually
        catch it and retry via the fallback model — parsing failures are the
        more likely failure mode for structured output than a raw API
        error, so this matters. Usage/cost is instead read via
        `get_usage_metadata_callback()`, which records `AIMessage.usage_metadata`
        as soon as each raw API response lands — before output parsing — so
        a primary call that burns tokens and then fails to parse still has
        its cost counted before the fallback takes over.
        """
        primary = self._primary_model.with_structured_output(schema)
        fallback = self._fallback_model.with_structured_output(schema)
        runnable = primary.with_fallbacks([fallback])
        with get_usage_metadata_callback() as cb:
            # with_structured_output()'s return type is loosely
            # `dict[str, Any] | BaseModel`; we know at runtime (include_raw
            # defaults False, schema is always a Pydantic class here) it's
            # exactly `T`, which pyright can't infer through the generic.
            parsed = cast(T, await runnable.ainvoke(messages))
        total_in = sum(usage["input_tokens"] for usage in cb.usage_metadata.values())
        total_out = sum(usage["output_tokens"] for usage in cb.usage_metadata.values())
        cost = sum(
            estimate_cost_usd(model_name, usage["input_tokens"], usage["output_tokens"])
            for model_name, usage in cb.usage_metadata.items()
        )
        return LLMResult(
            parsed=parsed,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            estimated_cost_usd=cost,
            models_invoked=list(cb.usage_metadata.keys()),
        )
