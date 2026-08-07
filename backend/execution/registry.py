"""Typed handler registry for executor events.

The worker keeps owning the Redis loop — consume, reclaim, retry, DLQ, ack —
and delegates here. This module only routes.
"""

from __future__ import annotations

from collections.abc import Callable

from events.types import AnyEvent
from execution.deps import ExecutionDeps

__all__ = ["ExecutionHandler", "dispatch", "register_handler", "registered_event_types"]

ExecutionHandler = Callable[[AnyEvent, ExecutionDeps], int]

_HANDLERS: dict[str, ExecutionHandler] = {}


def register_handler(event_type: str, handler: ExecutionHandler) -> None:
    """Route ``event_type`` to ``handler``. Last registration wins."""

    _HANDLERS[event_type] = handler


def registered_event_types() -> frozenset[str]:
    """Event types with a handler.

    The worker's subscription list must be a superset of this, or a registered
    executor never receives its events.
    """

    return frozenset(_HANDLERS)


def dispatch(event: AnyEvent, deps: ExecutionDeps) -> int:
    """Route one event to its executor. Returns 0 when nothing is registered.

    Exceptions deliberately propagate: ``run_handler_with_retry`` owns retry
    and dead-lettering. An executor that swallowed its own failure would report
    success, skip the DLQ, and make the failure invisible.
    """

    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        return 0
    return handler(event, deps)
