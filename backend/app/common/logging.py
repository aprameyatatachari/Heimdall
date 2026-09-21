"""Structured logging configuration.

Application code logs through structlog; structlog renders through the standard
library, so records from uvicorn, SQLAlchemy, and Alembic share one format.
Every record produced inside a request carries the request ID bound by
`RequestContextMiddleware`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# Header and log field names are referenced from middleware and tests.
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_LOG_KEY = "request_id"

# Keys whose values must never reach the logs.
_REDACTED_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "authorization",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "cookie",
        "set-cookie",
    }
)
_REDACTED_PLACEHOLDER = "[redacted]"


def _redact_sensitive(
    _logger: Any,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Replace the value of any obviously sensitive key."""
    for key in list(event_dict):
        if key.lower() in _REDACTED_KEYS:
            event_dict[key] = _REDACTED_PLACEHOLDER
    return event_dict


def _shared_processors() -> list[structlog.types.Processor]:
    """Processors applied to both structlog and standard-library records."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]


def configure_logging(*, level: str = "INFO", log_format: str = "console") -> None:
    """Configure structlog and the standard-library logging bridge.

    Safe to call more than once; the last call wins.
    """
    shared = _shared_processors()

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn installs its own handlers; let everything flow to the root handler.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(noisy)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_request_id(request_id: str) -> None:
    """Bind the request ID to the current logging context."""
    structlog.contextvars.bind_contextvars(**{REQUEST_ID_LOG_KEY: request_id})


def clear_request_context() -> None:
    """Clear all context variables bound for the current request."""
    structlog.contextvars.clear_contextvars()


__all__ = [
    "REQUEST_ID_HEADER",
    "REQUEST_ID_LOG_KEY",
    "bind_request_id",
    "clear_request_context",
    "configure_logging",
    "get_logger",
]
