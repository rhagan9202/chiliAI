"""Service-level protocols for the agent module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.service_models import WorkflowSubmissionRequest, WorkflowSubmissionResponse


@runtime_checkable
class AgentServiceProtocol(Protocol):
    """Service boundary for workflow orchestration requests."""

    def start_workflow(self, request: WorkflowSubmissionRequest) -> WorkflowSubmissionResponse: ...


__all__ = [
    "AgentServiceProtocol",
]