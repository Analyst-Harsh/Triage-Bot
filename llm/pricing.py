import litellm
import structlog

log = structlog.get_logger(__name__)


def estimate_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Delegates to `litellm`'s maintained pricing table rather than a
    hand-rolled dict — keeping current on a provider price change becomes a
    dependency bump, not a hand-edited dollar amount someone has to remember.
    `litellm` is used purely for this lookup; it never issues an API call.

    Never raises: cost estimation must never be why a node fails. An
    unmapped model (e.g. brand new) logs a warning and contributes 0.0 to
    the guardrail total rather than crashing the run.
    """
    try:
        input_cost, output_cost = litellm.cost_per_token(
            model=model_name, prompt_tokens=input_tokens, completion_tokens=output_tokens
        )
    except Exception:
        log.warning("llm_cost_lookup_failed", model=model_name)
        return 0.0
    return input_cost + output_cost
