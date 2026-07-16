"""Tests for `observability.logging_config`: env-driven structlog + stdlib
logging setup (format toggle, level, idempotency).

TriageNode.__call__'s contextvar binding (the actual production consumer of
this module) is proven in tests/graph/nodes/test_base.py, and the
error-path log call is proven in tests/graph/test_builder.py — both exist
alongside the code they cover, per this repo's 1:1 test-mirrors-source
convention, rather than duplicated here.
"""

import json
import logging
from collections.abc import Generator

import pytest

from observability import logging_config


@pytest.fixture(autouse=True)
def reset_logging_state(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """`configure_logging()` is deliberately idempotent for production use
    (safe to call repeatedly without reconfiguring) — that same guard would
    make every test after the first a no-op, so force a fresh reconfigure
    per test here, and restore the root logger's real state afterwards so
    this file doesn't leak a handler into the rest of the test session.
    """
    monkeypatch.setattr(logging_config, "_configured", False)
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    yield
    root_logger.handlers = original_handlers
    root_logger.setLevel(original_level)


def test_configure_logging_does_not_raise() -> None:
    logging_config.configure_logging()


def test_configure_logging_is_idempotent() -> None:
    logging_config.configure_logging()
    logging_config.configure_logging()

    assert len(logging.getLogger().handlers) == 1


def test_configure_logging_defaults_to_console_format_when_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    logging_config.configure_logging()
    # A stdlib logger, not a structlog one — this exercises the
    # foreign_pre_chain wiring, i.e. proves third-party library logs
    # (langgraph/langchain-core today) actually render through the same
    # format, not just structlog-native calls.
    logging.getLogger("test.console").info("console_event")

    output = capsys.readouterr().out.strip()
    assert "console_event" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)


def test_configure_logging_renders_json_when_log_format_is_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")

    logging_config.configure_logging()
    logging.getLogger("test.json").info("json_event")

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["event"] == "json_event"
    assert payload["level"] == "info"
    assert payload["logger"] == "test.json"


def test_configure_logging_respects_log_level_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    logging_config.configure_logging()

    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_defaults_log_level_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    logging_config.configure_logging()

    assert logging.getLogger().level == logging.INFO
