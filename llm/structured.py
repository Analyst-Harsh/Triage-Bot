from collections.abc import Sequence
from typing import cast

from langchain_core.callbacks.usage import get_usage_metadata_callback
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from llm.pricing import estimate_cost_usd
from llm.result import LLMResult


async def call_structured[T](
    primary: BaseChatModel,
    fallback: BaseChatModel,
    messages: Sequence[BaseMessage],
    schema: type[T],
) -> LLMResult[T]:
    """Calls `primary` for `schema`-shaped structured output, falling back to
    `fallback` on ANY failure — a raw API error (rate limit, timeout, ...) or
    a structured-output parsing failure alike.

    Deliberately does NOT pass `include_raw=True`: with the default
    `include_raw=False`, a parsing failure is *raised* rather than swallowed
    into a result dict, which is what lets `.with_fallbacks()` (whose default
    `exceptions_to_handle` is `(Exception,)`) actually catch it and retry via
    the fallback model — parsing failures are the more likely failure mode
    for structured output than a raw API error, so this matters. Usage/cost
    is instead read via `get_usage_metadata_callback()`, which records
    `AIMessage.usage_metadata` as soon as each raw API response lands —
    before output parsing — so a primary call that burns tokens and then
    fails to parse still has its cost counted before the fallback takes over.

    Extracted from `LLMNode.call_structured` so agent-subgraph nodes (e.g.
    the Researcher's post-loop summarize step) get the same
    fallback+cost-accounting guarantees without going through `TriageNode`.
    """
    primary_structured = primary.with_structured_output(schema)
    fallback_structured = fallback.with_structured_output(schema)
    runnable = primary_structured.with_fallbacks([fallback_structured])
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
