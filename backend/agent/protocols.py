"""Service-level protocols for the agent module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.models import WorkflowRun, WorkflowRunStatus
from agent.service_models import WorkflowSubmissionRequest, WorkflowSubmissionResponse


@runtime_checkable
class AgentServiceProtocol(Protocol):
    """Service boundary for workflow orchestration requests."""

    # TODO(production): Add async variants of these methods for non-blocking
    # API integration once FastAPI handlers are wired through.

    def start_workflow(self, request: WorkflowSubmissionRequest) -> WorkflowSubmissionResponse: ...

    def get_workflow_status(self, workflow_id: str) -> WorkflowRun: ...

    def list_workflows(
        self,
        *,
        knowledge_base_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRun]: ...

    def cancel_workflow(self, workflow_id: str) -> WorkflowRun: ...


__all__ = [
    "AgentServiceProtocol",
]
