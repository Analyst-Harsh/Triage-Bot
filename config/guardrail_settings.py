from pydantic import BaseModel, Field


class GuardrailSettings(BaseModel):
    """Every safety/cost cap the pipeline enforces, centralized in one place
    for ops tuning -- previously scattered across module-level constants in
    `graph/nodes/researcher.py`, `graph/nodes/drafter.py`, `tools/sandbox.py`,
    and `llm/structured.py`, each built on a different day with no shared
    review. Unlike `Settings`' own optional-feature fields (unset -> a module
    degrades to a no-op), every field here has a real, always-enforced
    default -- there is no valid "off" state for a cost/runaway-loop
    guardrail, so each gets a `Field` constraint (`ge=1` for the int caps,
    `gt=0.0` for the float budget/timeout fields) that fails fast at
    `Settings()` construction rather than silently disabling a cap via a
    misconfigured `0`.
    """

    researcher_max_tool_calls: int = Field(default=5, ge=1)
    # Default derived from the Drafter's own exploration budget: discover
    # language/manifest/test command (4) + dependency install (2) + baseline
    # run_tests (1) + repro write+run (2) + 3 fix cycles x (read+edit+run,
    # budget 4 each = 12) = 21, rounded up for margin.
    drafter_max_tool_calls: int = Field(default=50, ge=1)
    sandbox_max_fix_attempts: int = Field(default=6, ge=1)
    sandbox_max_baseline_attempts: int = Field(default=3, ge=1)
    sandbox_max_repro_attempts: int = Field(default=3, ge=1)
    structured_output_max_attempts: int = Field(default=2, ge=1)

    default_max_iterations: int = Field(default=10, ge=1)
    default_max_cost_usd: float = Field(default=1.0, gt=0.0)

    llm_request_timeout_seconds: float = Field(default=30.0, gt=0.0)
    llm_max_retries: int = Field(default=2, ge=1)

    e2b_sandbox_session_timeout_seconds: float = Field(default=900.0, gt=0.0)
    e2b_install_timeout_seconds: float = Field(default=300.0, gt=0.0)
    e2b_test_command_timeout_seconds: float = Field(default=180.0, gt=0.0)
    e2b_max_billed_seconds_per_run: float = Field(default=600.0, gt=0.0)
