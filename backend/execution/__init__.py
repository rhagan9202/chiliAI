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

# Importing the executor modules is what registers their handlers. Without
# this, `dispatch` finds an empty registry and silently returns 0 for every
# event — the seam would be wired and dead. Imported last so the registry and
# deps modules are fully initialised first, and re-exported nowhere: these are
# imported for their import side effect.
from analytics.score_runs import executor as _score_runs_executor  # noqa: E402,F401
from connectors import executor as _connectors_executor  # noqa: E402,F401
from workflow_definitions import executor as _workflow_executor  # noqa: E402,F401

__all__ = [
    "ExecutionDeps",
    "ExecutionHandler",
    "dispatch",
    "register_handler",
    "registered_event_types",
]
