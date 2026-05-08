"""Shared exception types used across backend module boundaries."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Raised when configuration references an unsupported or unavailable backend."""


__all__ = ["ConfigurationError"]