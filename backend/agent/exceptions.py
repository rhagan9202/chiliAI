"""Exception hierarchy for the agent module."""

from __future__ import annotations

from agent.models import WorkflowRunStatus


class AgentError(Exception):
    """Base exception for agent module failures."""


class AgentConfigurationError(AgentError):
    """Raised when a workflow submission is invalid or incomplete."""


class AgentStateStoreError(AgentError):
    """Raised when workflow state cannot be persisted or loaded."""


class WorkflowRunNotFoundError(AgentStateStoreError):
    """Raised when a workflow run id is not present in the store."""

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"No workflow run registered for workflow_id='{workflow_id}'.")


class WorkflowAlreadyTerminalError(AgentError):
    """Raised when an operation requires a non-terminal workflow run."""

    def __init__(self, workflow_id: str, status: WorkflowRunStatus) -> None:
        self.workflow_id = workflow_id
        self.status = status
        super().__init__(
            f"Workflow '{workflow_id}' is already in terminal state '{status.value}'."
        )


class IdempotencyKeyConflictError(AgentConfigurationError):
    """Raised when an idempotency key is reused with a different request body."""

    def __init__(self, idempotency_key: str, *, conflicting_field: str) -> None:
        self.idempotency_key = idempotency_key
        self.conflicting_field = conflicting_field
        super().__init__(
            f"Idempotency key '{idempotency_key}' was already used with a different "
            f"value for '{conflicting_field}'."
        )


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
    "IdempotencyKeyConflictError",
    "WorkflowAlreadyTerminalError",
    "WorkflowRunNotFoundError",
]