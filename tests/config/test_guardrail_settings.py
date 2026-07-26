import pytest
from pydantic import ValidationError

from config.guardrail_settings import GuardrailSettings
from config.settings import Settings


def test_guardrail_settings_defaults_match_audited_values() -> None:
    guardrails = GuardrailSettings()

    assert guardrails.researcher_max_tool_calls == 5
    assert guardrails.drafter_max_tool_calls == 50
    assert guardrails.sandbox_max_fix_attempts == 6
    assert guardrails.sandbox_max_baseline_attempts == 3
    assert guardrails.sandbox_max_repro_attempts == 3
    assert guardrails.structured_output_max_attempts == 2
    assert guardrails.default_max_iterations == 10
    assert guardrails.default_max_cost_usd == 1.0
    assert guardrails.llm_request_timeout_seconds == 30.0
    assert guardrails.llm_max_retries == 2
    assert guardrails.e2b_sandbox_session_timeout_seconds == 900.0
    assert guardrails.e2b_install_timeout_seconds == 300.0
    assert guardrails.e2b_test_command_timeout_seconds == 180.0
    assert guardrails.e2b_max_billed_seconds_per_run == 600.0


def test_settings_guardrails_field_populated_with_defaults() -> None:
    settings = Settings()

    assert settings.guardrails == GuardrailSettings()


def test_settings_guardrails_overridden_via_nested_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GUARDRAILS__RESEARCHER_MAX_TOOL_CALLS", "9")

    settings = Settings()

    assert settings.guardrails.researcher_max_tool_calls == 9
    # Every other field stays at its own default -- the override is scoped
    # to exactly the one env var set above.
    assert settings.guardrails.drafter_max_tool_calls == 50


@pytest.mark.parametrize(
    "field",
    [
        "researcher_max_tool_calls",
        "drafter_max_tool_calls",
        "sandbox_max_fix_attempts",
        "sandbox_max_baseline_attempts",
        "sandbox_max_repro_attempts",
        "structured_output_max_attempts",
        "default_max_iterations",
        "llm_max_retries",
    ],
)
def test_guardrail_settings_rejects_zero_int_caps(field: str) -> None:
    """A `0` cap would either silently disable enforcement (if read as
    "no limit") or make every run instantly fail (if read as "already at
    the limit") -- neither is a coherent config value, so it's rejected at
    construction rather than accepted and misbehaving at runtime.

    Uses `model_validate` over a plain dict rather than `**{field: 0}`:
    with a dynamic (non-literal) `field` name, pyright checks a keyword
    splat against every parameter's own type, which spuriously flags int
    fields when the same parametrization is reused for float fields below."""
    with pytest.raises(ValidationError):
        GuardrailSettings.model_validate({field: 0})


@pytest.mark.parametrize(
    "field",
    [
        "default_max_cost_usd",
        "llm_request_timeout_seconds",
        "e2b_sandbox_session_timeout_seconds",
        "e2b_install_timeout_seconds",
        "e2b_test_command_timeout_seconds",
        "e2b_max_billed_seconds_per_run",
    ],
)
def test_guardrail_settings_rejects_zero_float_budgets(field: str) -> None:
    with pytest.raises(ValidationError):
        GuardrailSettings.model_validate({field: 0.0})
