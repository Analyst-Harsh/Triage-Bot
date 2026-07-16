"""Structured logging setup: the first of observability/'s cross-cutting
systems (see docs/summary.md's "Observability" section) — OpenTelemetry +
Langfuse tracing will join this package later, but that's out of scope here.

`configure_logging()` wires structlog's own processor chain AND routes
stdlib `logging` (used internally by langgraph, langchain-core, and
eventually uvicorn) through the *same* chain via
`structlog.stdlib.ProcessorFormatter`, so third-party library logs come out
in the same structured format instead of unstyled plain text interleaved
with JSON — a log stream that's part-JSON, part-plain-text defeats log
aggregation, which is the whole point of doing this.
"""

import logging
import os
import sys

import structlog

_configured = False


def configure_logging() -> None:
    """Configure structlog + stdlib logging for the whole process.

    Idempotent — safe to call more than once without raising or
    duplicating handlers; a second call is a no-op.

    Env vars (read directly via `os.environ.get`, matching the
    no-settings-framework precedent set by `api/github_client.py`'s
    `GITHUB_TOKEN` handling):
      LOG_LEVEL: stdlib level name, default "INFO". Unrecognized values
        fall back to INFO rather than raising.
      LOG_FORMAT: "json" for production, anything else (default: unset,
        i.e. "console") renders human-readable output.
    """
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
    use_json = os.environ.get("LOG_FORMAT", "console").lower() == "json"

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)
