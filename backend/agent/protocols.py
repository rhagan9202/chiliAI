"""Service-level protocols for the agent module."""

from __future__ import annotations

from collections.abc import Sequence

from typing import Protocol, runtime_checkable

from agent.adapters.protocols import WorkflowRunPage
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
    ) -> WorkflowRunPage: ...

    def approve_step(
        self,
        workflow_id: str,
        step_id: str,
        *,
        actor_user_id: str,
        actor_roles: Sequence[str],
    ) -> WorkflowRun:
        """Approve a parked step and resume the run.

        Records the decision **and** republishes the step event: the parking
        event was already acked, so recording alone leaves the run stuck.
        """
        ...

    def reject_step(
        self,
        workflow_id: str,
        step_id: str,
        *,
        actor_user_id: str,
        actor_roles: Sequence[str],
        reason: str,
    ) -> WorkflowRun:
        """Reject a parked step, failing the run with the reason recorded."""
        ...

    def cancel_workflow(self, workflow_id: str) -> WorkflowRun: ...


__all__ = [
    "AgentServiceProtocol",
]
