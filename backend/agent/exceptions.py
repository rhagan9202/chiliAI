"""Exception hierarchy for the agent module."""

from __future__ import annotations


class AgentError(Exception):
    """Base exception for agent module failures."""


class AgentConfigurationError(AgentError):
    """Raised when a workflow submission is invalid or incomplete."""


class AgentStateStoreError(AgentError):
    """Raised when workflow state cannot be persisted or loaded."""


class ConfigurationError(AgentError):
    """Raised when worker adapter wiring cannot satisfy ``DomainConfig``.

    The message identifies the subsystem and backend value that failed so
    operators can diagnose misconfiguration without needing a stack trace.
    """

    def __init__(self, *, subsystem: str, backend: str, message: str) -> None:
        self.subsystem = subsystem
        self.backend = backend
        super().__init__(
            f"{subsystem} backend '{backend}' is not available: {message}"
        )


__all__ = [
    "AgentConfigurationError",
    "AgentError",
    "AgentStateStoreError",
    "ConfigurationError",
]