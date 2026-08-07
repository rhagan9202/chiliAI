"""Capability id → callable map.

The registry describes what a capability *is*; this says what actually runs
when one is invoked. Keeping the two apart is what lets a manifest be
registered, browsed and authorized before an implementation exists — and what
makes "registered but not executable" a distinct, reportable state rather than
a crash.

Registration is a module-level side effect, the same pattern the execution
seam uses. That has a failure mode worth naming: if nothing imports the module
that registers an executor, the capability is authorized and then refused as
not executable. `capabilities/__init__.py` imports the built-in executors for
exactly that reason.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

__all__ = [
    "CapabilityExecutor",
    "ExecutionContext",
    "clear_executors",
    "get_executor",
    "register_executor",
    "registered_capability_ids",
]

@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Who is calling, and under what authorization — separate from tool input.

    ``execute()`` has already authorized the call using exactly these values, so
    an executor reading them is re-checking rather than deciding. The point is
    that a capability needing to know its caller has a channel that is not the
    business payload: the actor previously travelled *inside* the payload,
    because the signature had nowhere else to put it, and every capability saw
    ``actor_roles`` as a business field it had to know to ignore.

    Frozen, with ``actor_roles`` as a tuple: an executor must not be able to
    edit the authorization it was handed, and a mutable field on a frozen
    dataclass is a lie about immutability.
    """

    actor_user_id: str
    actor_roles: tuple[str, ...]
    domain_name: str | None
    environment_tag: str | None
    knowledge_base_id: str | None


CapabilityExecutor = Callable[
    [Mapping[str, object], ExecutionContext], Mapping[str, object]
]

_EXECUTORS: dict[str, CapabilityExecutor] = {}


def register_executor(capability_id: str, executor: CapabilityExecutor) -> None:
    """Bind a capability id to the callable that runs it.

    Re-registering replaces, so a domain pack or test can override a built-in
    without unregistering first.
    """

    _EXECUTORS[capability_id] = executor


def get_executor(capability_id: str) -> CapabilityExecutor | None:
    return _EXECUTORS.get(capability_id)


def registered_capability_ids() -> frozenset[str]:
    """Ids with an executor bound — the capabilities that can actually run."""

    return frozenset(_EXECUTORS)


def clear_executors() -> None:
    """Empty the map.

    For tests only. The map is module-level state, so a test that registers an
    executor and does not clear it changes the behaviour of every later test in
    the same interpreter.
    """

    _EXECUTORS.clear()
