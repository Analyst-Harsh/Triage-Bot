import litellm
import structlog
from litellm.types.utils import PromptTokensDetails, Usage

log = structlog.get_logger(__name__)


def estimate_cost_usd(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
) -> float:
    """Delegates to `litellm`'s maintained pricing table rather than a
    hand-rolled dict — keeping current on a provider price change becomes a
    dependency bump, not a hand-edited dollar amount someone has to remember.
    `litellm` is used purely for this lookup; it never issues an API call.

    `cache_read_tokens` (default 0, i.e. today's uncached behavior
    unchanged) is the count of `input_tokens` served from a provider-side
    prompt cache -- OpenAI's automatic caching reports these at a steep
    discount (verified: ~10x cheaper than a regular input token for the
    `gpt-5-nano`/`gpt-5.4-nano` family). Must be routed through
    `usage_object=Usage(..., prompt_tokens_details=...)`, never passed as a
    bare `cache_read_input_tokens` kwarg: litellm's cost helper treats a bare
    kwarg as Anthropic's convention (`prompt_tokens` excludes cache tokens)
    and adds it back onto `prompt_tokens`, double-counting for OpenAI-style
    providers where `input_tokens` already includes the cached portion.

    Deliberately no `cache_creation_tokens` parameter: litellm's own
    `cache_creation_tokens` field is documented as "used for Anthropic
    prompt caching" -- OpenAI cache-write cost is 0 for this model family,
    so there is nothing correct to feed it here. Cache-creation tokens are
    still tracked end-to-end as an observability counter (`LLMResult`,
    `RunMeta`), just never plugged into this cost calculation.

    Never raises: cost estimation must never be why a node fails. An
    unmapped model (e.g. brand new) logs a warning and contributes 0.0 to
    the guardrail total rather than crashing the run.
    """
    try:
        if cache_read_tokens:
            usage = Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                prompt_tokens_details=PromptTokensDetails(cached_tokens=cache_read_tokens),
            )
            input_cost, output_cost = litellm.cost_per_token(
                model=model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                usage_object=usage,
            )
        else:
            input_cost, output_cost = litellm.cost_per_token(
                model=model_name, prompt_tokens=input_tokens, completion_tokens=output_tokens
            )
    except Exception:
        log.warning("llm_cost_lookup_failed", model=model_name)
        return 0.0
    return input_cost + output_cost
