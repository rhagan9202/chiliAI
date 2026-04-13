"""Service entry point for agent workflow submission flows."""

from __future__ import annotations

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.exceptions import AgentConfigurationError, AgentStateStoreError
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from agent.service_models import WorkflowSubmissionRequest, WorkflowSubmissionResponse
from events.protocols import EventBus
from events.types import AgentWorkflowStartedEvent, AgentWorkflowStartedReference
from shared.utils import generate_id


class AgentService:
    """Coordinate workflow submission, persistence, and event publication."""

    def __init__(self, run_store: WorkflowRunStoreProtocol, *, event_bus: EventBus) -> None:
        self._run_store = run_store
        self._event_bus = event_bus

    def start_workflow(self, request: WorkflowSubmissionRequest) -> WorkflowSubmissionResponse:
        try:
            run = self._run_store.save_run(
                WorkflowRun(
                    workflow_id=generate_id(),
                    knowledge_base_id=request.knowledge_base_id,
                    trigger_event_type=request.trigger_event_type,
                    status=WorkflowRunStatus.RUNNING,
                    steps=[WorkflowStepState(step_name=step_name) for step_name in request.requested_steps],
                    metadata=request.metadata,
                )
            )
        except ValueError as exc:
            raise AgentConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise AgentStateStoreError("Failed to persist workflow run.") from exc

        response = WorkflowSubmissionResponse(
            workflow_id=run.workflow_id,
            knowledge_base_id=run.knowledge_base_id,
            trigger_event_type=run.trigger_event_type,
            status=run.status,
            step_count=len(run.steps),
            queued_steps=[step.step_name for step in run.steps],
        )
        self._event_bus.publish(
            AgentWorkflowStartedEvent(
                workflows=[
                    AgentWorkflowStartedReference(
                        workflow_id=response.workflow_id,
                        knowledge_base_id=response.knowledge_base_id,
                        trigger_event_type=response.trigger_event_type,
                        step_count=response.step_count,
                        status=response.status.value,
                    )
                ]
            )
        )
        return response


def create_agent_service(
    run_store: WorkflowRunStoreProtocol,
    *,
    event_bus: EventBus,
) -> AgentService:
    """Create the default agent workflow service."""

    return AgentService(run_store, event_bus=event_bus)


__all__ = ["AgentService", "create_agent_service"]