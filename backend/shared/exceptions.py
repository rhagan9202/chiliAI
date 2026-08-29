"""Shared exception types used across backend module boundaries."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Raised when configuration references an unsupported or unavailable backend."""


class ConcurrentModificationError(Exception):
    """Raised when a write lost an optimistic-concurrency race against another writer.

    A cross-module marker base, not a type raised directly. Each module that
    guards a compare-and-write defines its own subclass (for example
    ``monitoring.exceptions.AlertConcurrentModificationError``) that inherits
    from both its module's own error hierarchy *and* this type -- callers
    inside the module keep catching the module-specific error, while a
    caller at the API gateway (or anywhere else that only needs to know "was
    this a lost race") can catch this one type regardless of which module
    raised it, without importing every module's exception module.

    A lost race is always safe to retry: reload and resubmit. That is what
    distinguishes it from a persistence/source failure (the underlying store
    itself is unavailable or errored), which is not safe to retry blindly
    and must never be raised as -- or caught as -- this type.

    ``cases.exceptions.CaseConcurrentModificationError`` predates this base
    and has not (yet) been retrofitted to inherit from it; new
    concurrency-conflict exceptions should inherit from it from the start.
    """


__all__ = ["ConcurrentModificationError", "ConfigurationError"]