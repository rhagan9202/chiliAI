"""Executor dispatch seam.

Importing this package registers every executor handler, so the worker only
needs to import ``execution`` for dispatch to be wired.
"""

from __future__ import annotations

from execution.deps import ExecutionDeps
from execution.registry import (
    ExecutionHandler,
    dispatch,
    register_handler,
    registered_event_types,
)

__all__ = [
    "ExecutionDeps",
    "ExecutionHandler",
    "dispatch",
    "register_handler",
    "registered_event_types",
]
