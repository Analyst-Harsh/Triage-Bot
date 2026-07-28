from pydantic import BaseModel


class GraderCheck(BaseModel):
    """One hand-labeled/deterministic check result from a grader -- see
    `evals.graders`. No LLM, no network: a grader is a pure function over a
    `GoldenCase` plus reconstructed run data."""

    name: str
    passed: bool
    detail: str
