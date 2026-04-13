"""Exception hierarchy for the llm module."""

from __future__ import annotations


class LlmError(Exception):
    """Base exception for llm module failures."""


class LlmConfigurationError(LlmError):
    """Raised when an llm request is invalid or incomplete."""


class LlmProviderError(LlmError):
    """Raised when the configured llm provider cannot complete a request."""


__all__ = [
    "LlmConfigurationError",
    "LlmError",
    "LlmProviderError",
]