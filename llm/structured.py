from collections.abc import Sequence
from typing import Any, cast

import structlog
from langchain_core.callbacks.usage import get_usage_metadata_callback
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from pydantic import ValidationError

from llm.pricing import estimate_cost_usd
from llm.result import LLMResult

log = structlog.get_logger(__name__)

# A structured-output call fails in two very different ways: a raw API error
# (rate limit, timeout, ...), or the model's own response not conforming to
# the schema (e.g. a required field silently omitted from the tool-call args
# -- observed in production: every action in a multi-action DraftProposal
# missing ProposedAction.rationale, right after ToolCallLimitMiddleware cut
# the tool-calling loop short). The latter is often a systematic
# instruction-following gap, not random sampling noise -- simply resending
# the same prompt is unlikely to fix it, but telling the model exactly what
# it got wrong (see `_invoke_with_repair`) often does. Each model gets this
# many attempts before the next model in the fallback chain is tried. Kept
# small: this only runs on the failure path, but each attempt is a real,
# billed LLM call.
_STRUCTURED_OUTPUT_MAX_ATTEMPTS = 2


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
) -> LLMResult[T]:
    """Calls `primary` for `schema`-shaped structured output, falling back to
    `fallback` on ANY failure — a raw API error (rate limit, timeout, ...) or
    a structured-output parsing failure alike. Each model gets its own
    `_STRUCTURED_OUTPUT_MAX_ATTEMPTS` attempts (see `_invoke_with_repair`)
    before the next model in the chain is tried, rather than giving up on a
    model after a single bad sample.

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

    `method="function_calling"` (rather than the newer default strict
    `"json_schema"` mode) because OpenAI's strict Structured Outputs schema
    validation rejects `oneOf` outright — which is exactly what a Pydantic
    discriminated union (e.g. `DraftAction`) compiles to. Tool/function-call
    based structured output has no such restriction and is supported
    uniformly across providers, so this is the one method that works for
    every schema shape this function is asked to handle, not just the flat
    ones used before the Drafter's discriminated-union schemas existed.
    """
    primary_structured = primary.with_structured_output(schema, method="function_calling")
    fallback_structured = fallback.with_structured_output(schema, method="function_calling")
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
                await _invoke_with_repair(
                    primary_structured, messages, max_attempts=_STRUCTURED_OUTPUT_MAX_ATTEMPTS
                ),
            )
        except Exception:
            parsed = cast(
                T,
                await _invoke_with_repair(
                    fallback_structured, messages, max_attempts=_STRUCTURED_OUTPUT_MAX_ATTEMPTS
                ),
            )
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
