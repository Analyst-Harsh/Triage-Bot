from collections.abc import Sequence
from typing import Any, Literal, cast

import structlog
from langchain_core.callbacks.usage import get_usage_metadata_callback
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.runnables import Runnable
from pydantic import ValidationError

from llm.pricing import estimate_cost_usd
from llm.result import LLMResult

log = structlog.get_logger(__name__)


async def _invoke_with_repair(
    structured_runnable: Runnable[Sequence[BaseMessage], Any],
    messages: Sequence[BaseMessage],
    *,
    max_attempts: int,
) -> Any:
    """Invokes `structured_runnable` against `messages`, up to `max_attempts`
    times.

    A `pydantic.ValidationError` (the model's tool-call args didn't satisfy
    the schema) gets fed back to the model as a corrective follow-up
    `HumanMessage` quoting the exact validation error before the next
    attempt -- since the model can often fix a schema-compliance mistake
    once told precisely what it got wrong, which a blind resend of the exact
    same prompt cannot reliably do. Any other exception (a raw API error:
    rate limit, timeout, ...) has nothing for the model to correct, so it's
    retried unchanged.

    Never touches the caller's own `messages` list -- corrective turns are
    appended to a local copy, same "don't mutate the caller's trajectory"
    precedent as `graph/nodes/trajectory.py`'s helpers.
    """
    current_messages: list[BaseMessage] = list(messages)
    for attempt in range(1, max_attempts + 1):
        try:
            return await structured_runnable.ainvoke(current_messages)
        except Exception as exc:
            log.warning(
                "structured_output_attempt_failed",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
            )
            if attempt >= max_attempts:
                raise
            if isinstance(exc, ValidationError):
                current_messages = [
                    *current_messages,
                    HumanMessage(
                        content=(
                            "Your previous response did not match the required "
                            f"schema:\n{exc}\n\nRespond again with a complete, "
                            "schema-valid answer -- every field listed as required "
                            "must be present, including on every item of any list."
                        )
                    ),
                ]
    # Unreachable: the loop above always either returns (on success) or
    # re-raises (once `attempt >= max_attempts`).
    raise RuntimeError("unreachable")


async def call_structured[T](
    primary: BaseChatModel,
    fallback: BaseChatModel,
    messages: Sequence[BaseMessage],
    schema: type[T],
    *,
    max_attempts: int,
    method: Literal["function_calling", "json_schema"] = "function_calling",
) -> LLMResult[T]:
    """Calls `primary` for `schema`-shaped structured output, falling back to
    `fallback` on ANY failure — a raw API error (rate limit, timeout, ...) or
    a structured-output parsing failure alike. Each model gets its own
    `max_attempts` attempts (see `_invoke_with_repair`, and
    `Settings.guardrails.structured_output_max_attempts` for the production
    default) before the next model in the chain is tried, rather than giving
    up on a model after a single bad sample.

    `max_attempts` is a required, explicit parameter rather than this
    function reading `get_settings()` itself: this keeps `call_structured`
    pure and trivially testable in isolation (see `tests/llm/test_structured.py`,
    which constructs fake models directly with no `Settings` dependency at
    all) — callers that already have `Settings` cached (`LLMNode.__init__`,
    `AgentSubgraph.__init__`) resolve the value once and pass it through.

    Deliberately does NOT pass `include_raw=True`: with the default
    `include_raw=False`, a parsing failure is *raised* rather than swallowed
    into a result dict, which is what lets `_invoke_with_repair` (and the
    primary -> fallback handoff) actually catch it. Usage/cost is instead
    read via `get_usage_metadata_callback()`, which records
    `AIMessage.usage_metadata` as soon as each raw API response lands —
    before output parsing — so every attempt that burned tokens (even ones
    that failed to parse) still has its cost counted.

    Extracted from `LLMNode.call_structured` so agent-subgraph nodes (e.g.
    the Researcher's post-loop summarize step) get the same
    fallback+cost-accounting guarantees without going through `TriageNode`.

    `method` defaults to `"function_calling"` rather than the newer default
    strict `"json_schema"` mode because OpenAI's strict Structured Outputs
    schema validation rejects `oneOf` outright — which is exactly what a
    Pydantic discriminated union (e.g. `DraftAction`) compiles to.
    Tool/function-call based structured output has no such restriction and
    is supported uniformly across providers, so it's the only method that
    works for every schema shape this function is asked to handle. Callers
    whose `schema` has no discriminated union (e.g. `PlannerClassification`,
    `RiskJudgmentBatch`) may pass `method="json_schema"` explicitly to get a
    real provider-side conformance guarantee instead of best-effort bias —
    see "Structured-output validation" in `docs/agent/architecture-conventions.md`
    for which call sites do.
    """
    primary_structured = primary.with_structured_output(schema, method=method)
    fallback_structured = fallback.with_structured_output(schema, method=method)
    with get_usage_metadata_callback() as cb:
        # _invoke_with_repair()'s return type is untyped (Any): it forwards
        # whatever with_structured_output() produces, which is itself only
        # loosely `dict[str, Any] | BaseModel`; we know at runtime
        # (include_raw defaults False, schema is always a Pydantic class
        # here) it's exactly `T`, which pyright can't infer through either
        # generic.
        try:
            parsed = cast(
                T,
                await _invoke_with_repair(primary_structured, messages, max_attempts=max_attempts),
            )
        except Exception:
            parsed = cast(
                T,
                await _invoke_with_repair(fallback_structured, messages, max_attempts=max_attempts),
            )
    total_in = sum(usage["input_tokens"] for usage in cb.usage_metadata.values())
    total_out = sum(usage["output_tokens"] for usage in cb.usage_metadata.values())
    total_cache_read = sum(_cache_read_tokens(usage) for usage in cb.usage_metadata.values())
    total_cache_creation = sum(
        _cache_creation_tokens(usage) for usage in cb.usage_metadata.values()
    )
    # Discount is priced per-model (each model in models_invoked has its own
    # cache_read_input_token_cost) -- must be applied inside this
    # per-model comprehension, never by summing cache_read tokens globally
    # first and calling estimate_cost_usd once against a mixed total.
    cost = sum(
        estimate_cost_usd(
            model_name,
            usage["input_tokens"],
            usage["output_tokens"],
            cache_read_tokens=_cache_read_tokens(usage),
        )
        for model_name, usage in cb.usage_metadata.items()
    )
    return LLMResult(
        parsed=parsed,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        estimated_cost_usd=cost,
        models_invoked=list(cb.usage_metadata.keys()),
        cache_read_tokens=total_cache_read,
        cache_creation_tokens=total_cache_creation,
    )


def _cache_read_tokens(usage: UsageMetadata) -> int:
    return usage.get("input_token_details", {}).get("cache_read", 0) or 0


def _cache_creation_tokens(usage: UsageMetadata) -> int:
    return usage.get("input_token_details", {}).get("cache_creation", 0) or 0
