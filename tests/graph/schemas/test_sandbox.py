from datetime import UTC, datetime
from typing import Any

from graph.schemas.actions import SandboxResult
from graph.schemas.sandbox import SandboxAttempt


def make_sandbox_result(**overrides: Any) -> SandboxResult:
    defaults: dict[str, Any] = {
        "passed": True,
        "logs": "1 passed",
        "test_command": "pytest tests/test_foo.py",
        "duration_seconds": 1.23,
    }
    defaults.update(overrides)
    return SandboxResult(**defaults)


def make_sandbox_attempt(**overrides: Any) -> SandboxAttempt:
    defaults: dict[str, Any] = {
        "kind": "baseline",
        "attempt_number": 1,
        "diff": "",
        "changed_files": [],
        "result": make_sandbox_result(),
        "recorded_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return SandboxAttempt(**defaults)


def test_baseline_sandbox_attempt_construction() -> None:
    attempt = make_sandbox_attempt(kind="baseline")
    assert attempt.kind == "baseline"
    assert attempt.attempt_number == 1


def test_baseline_sandbox_attempt_json_round_trip() -> None:
    attempt = make_sandbox_attempt(kind="baseline")
    restored = SandboxAttempt.model_validate_json(attempt.model_dump_json())
    assert restored == attempt


def test_repro_sandbox_attempt_construction() -> None:
    attempt = make_sandbox_attempt(
        kind="repro",
        attempt_number=2,
        diff="--- a/foo.py\n+++ b/foo.py\n",
        changed_files=["foo.py"],
        result=make_sandbox_result(passed=False, logs="1 failed"),
    )
    assert attempt.kind == "repro"
    assert attempt.result.passed is False


def test_repro_sandbox_attempt_json_round_trip() -> None:
    attempt = make_sandbox_attempt(
        kind="repro",
        attempt_number=2,
        diff="--- a/foo.py\n+++ b/foo.py\n",
        changed_files=["foo.py"],
        result=make_sandbox_result(passed=False, logs="1 failed"),
    )
    restored = SandboxAttempt.model_validate_json(attempt.model_dump_json())
    assert restored == attempt


def test_fix_attempt_sandbox_attempt_construction() -> None:
    attempt = make_sandbox_attempt(
        kind="fix_attempt",
        attempt_number=3,
        diff="--- a/foo.py\n+++ b/foo.py\n",
        changed_files=["foo.py"],
        result=make_sandbox_result(passed=True),
    )
    assert attempt.kind == "fix_attempt"
    assert attempt.result.passed is True


def test_fix_attempt_sandbox_attempt_json_round_trip() -> None:
    attempt = make_sandbox_attempt(
        kind="fix_attempt",
        attempt_number=3,
        diff="--- a/foo.py\n+++ b/foo.py\n",
        changed_files=["foo.py"],
    )
    restored = SandboxAttempt.model_validate_json(attempt.model_dump_json())
    assert restored == attempt
