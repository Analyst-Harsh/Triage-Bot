from dataclasses import dataclass


@dataclass
class LLMResult[T]:
    """Internal-only — never crosses a serialization boundary, so per this
    repo's "validate at boundaries, trust internals" rule it doesn't need to
    be a Pydantic model."""

    parsed: T
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    models_invoked: list[str]
