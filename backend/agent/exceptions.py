"""Exception hierarchy for the agent module."""

from __future__ import annotations


class AgentError(Exception):
    """Base exception for agent module failures."""


class AgentConfigurationError(AgentError):
    """Raised when a workflow submission is invalid or incomplete."""


class AgentStateStoreError(AgentError):
    """Raised when workflow state cannot be persisted or loaded."""