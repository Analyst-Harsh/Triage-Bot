from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from graph.schemas.actions import SandboxResult


class SandboxAttempt(BaseModel):
    """One atomic (diff, test-result) bundle, snapshotted back-to-back
    inside SandboxHandle.run_tests() so a pass/fail is never separated from
    the exact diff that produced it. System-derived only, same principle as
    ToolCallRecord — never constructed from anything the model says."""

    kind: Literal["baseline", "repro", "fix_attempt"]
    attempt_number: int
    diff: str
    changed_files: list[str]
    result: SandboxResult
    recorded_at: datetime
