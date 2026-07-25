import pytest
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


def test_estimate_cost_usd_with_cache_read_tokens_is_cheaper() -> None:
    # gpt-5-nano: input $5e-8/tok, cache_read $5e-9/tok (10x cheaper), output $4e-7/tok.
    uncached = estimate_cost_usd("gpt-5-nano", input_tokens=2000, output_tokens=100)
    cached = estimate_cost_usd(
        "gpt-5-nano", input_tokens=2000, output_tokens=100, cache_read_tokens=1500
    )

    assert uncached == pytest.approx(9.999999999999999e-05 + 3.9999999999999996e-05)
    assert cached == pytest.approx(3.25e-05 + 3.9999999999999996e-05)
    assert cached < uncached


def test_estimate_cost_usd_without_cache_params_matches_current_behavior() -> None:
    # Same assertion as test_estimate_cost_usd_known_openai_model, called via
    # the exact no-kwargs signature every existing call site already uses --
    # proves the default path is unchanged by the new cache_read_tokens param.
    cost = estimate_cost_usd("gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == 0.15 + 0.60


def test_estimate_cost_usd_unmapped_model_with_cache_tokens_still_falls_back_to_zero() -> None:
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as cap_logs:
        cost = estimate_cost_usd(
            "totally-fake-model-xyz", input_tokens=1000, output_tokens=1000, cache_read_tokens=500
        )

    assert cost == 0.0
    warning = next(entry for entry in cap_logs if entry["event"] == "llm_cost_lookup_failed")
    assert warning["model"] == "totally-fake-model-xyz"
