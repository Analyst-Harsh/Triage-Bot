import structlog
from structlog.testing import capture_logs

from llm.pricing import estimate_cost_usd


def test_estimate_cost_usd_known_openai_model() -> None:
    # gpt-4o-mini: $0.15/$0.60 per Mtok
    cost = estimate_cost_usd("gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == 0.15 + 0.60


def test_estimate_cost_usd_known_anthropic_model() -> None:
    # claude-haiku-4-5-20251001: $1/$5 per Mtok
    cost = estimate_cost_usd(
        "claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000
    )
    assert cost == 1.0 + 5.0


def test_estimate_cost_usd_unmapped_model_falls_back_to_zero() -> None:
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        cost = estimate_cost_usd("totally-fake-model-xyz", input_tokens=1000, output_tokens=1000)

    assert cost == 0.0
    warning = next(entry for entry in cap_logs if entry["event"] == "llm_cost_lookup_failed")
    assert warning["model"] == "totally-fake-model-xyz"
