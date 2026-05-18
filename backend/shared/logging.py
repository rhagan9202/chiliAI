"""Structured logging configuration using structlog.

Configures structlog once for the process. Output format is controlled by
the ``LOG_FORMAT`` environment variable: ``json`` produces a JSON renderer
suitable for centralized log aggregation, anything else produces the console
renderer used during development.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger
    from structlog.types import EventDict, Processor, WrappedLogger

__all__ = [
    "bind_correlation_id",
    "clear_correlation_id",
    "configure_logging",
    "get_logger",
]


_CORRELATION_ID_CTX: ContextVar[str | None] = ContextVar(
    "chili_correlation_id", default=None
)
_configured: bool = False


def _resolve_log_level(level: int | str | None) -> int:
    """Resolve an explicit or environment-driven log level."""

    value = level if level is not None else os.environ.get("LOG_LEVEL", "INFO")
    if isinstance(value, int):
        return value

    normalized = value.strip().upper()
    if normalized.isdigit():
        return int(normalized)
    resolved = logging.getLevelName(normalized)
    return resolved if isinstance(resolved, int) else logging.INFO


def _correlation_id_processor(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Inject the current correlation_id from contextvar when present."""

    if "correlation_id" not in event_dict:
        current = _CORRELATION_ID_CTX.get()
        if current is not None:
            event_dict["correlation_id"] = current
    return event_dict


def configure_logging(
    *,
    log_format: str | None = None,
    level: int | str | None = None,
) -> None:
    """Configure structlog and stdlib logging.

    Idempotent: subsequent calls are no-ops, so both API and worker entry
    points may invoke this safely.
    """

    global _configured
    if _configured:
        return

    import structlog

    chosen_format = (log_format or os.environ.get("LOG_FORMAT") or "console").lower()

    logging.basicConfig(
        level=_resolve_log_level(level),
        format="%(message)s",
        force=True,
    )

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        _correlation_id_processor,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    final_processor: Processor
    if chosen_format == "json":
        final_processor = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            final_processor,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> BoundLogger:
    """Return a structlog logger bound to ``name``.

    Configures logging on first use to keep import order tolerant.
    """

    if not _configured:
        configure_logging()
    import structlog

    return structlog.stdlib.get_logger(name)


def bind_correlation_id(correlation_id: str | None) -> None:
    """Bind a correlation id into structlog and the context variable."""

    from structlog.contextvars import bind_contextvars, clear_contextvars

    if correlation_id is None:
        clear_contextvars()
        _CORRELATION_ID_CTX.set(None)
        return
    _CORRELATION_ID_CTX.set(correlation_id)
    bind_contextvars(correlation_id=correlation_id)


def clear_correlation_id() -> None:
    """Clear the correlation id from structlog and the context variable."""

    from structlog.contextvars import clear_contextvars

    _CORRELATION_ID_CTX.set(None)
    clear_contextvars()
