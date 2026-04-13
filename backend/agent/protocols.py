"""Service-level protocols for the agent module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.service_models import WorkflowSubmissionRequest, WorkflowSubmissionResponse


@runtime_checkable
class AgentServiceProtocol(Protocol):
    """Service boundary for workflow orchestration requests."""

    # TODO(production): Add workflow lifecycle methods:
    # - get_workflow_status(workflow_id: str) -> WorkflowRun
    # - list_workflows(kb_id: str, limit, offset) -> list[WorkflowRun]
    # - cancel_workflow(workflow_id: str) -> None
    # Add async variants for non-blocking API calls.

    def start_workflow(self, request: WorkflowSubmissionRequest) -> WorkflowSubmissionResponse: ...


__all__ = [
    "AgentServiceProtocol",
]