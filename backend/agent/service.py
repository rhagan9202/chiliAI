"""Service entry point for agent workflow submission flows."""

from __future__ import annotations

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.exceptions import (
    AgentConfigurationError,
    AgentStateStoreError,
    IdempotencyKeyConflictError,
    WorkflowAlreadyTerminalError,
)
from agent.models import (
    TERMINAL_RUN_STATUSES,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
)
from agent.service_models import WorkflowSubmissionRequest, WorkflowSubmissionResponse
from events.protocols import EventBus
from events.types import AgentWorkflowStartedEvent, AgentWorkflowStartedReference
from shared.utils import generate_id, utc_now


class AgentService:
    """Coordinate workflow submission, persistence, and event publication."""

    # TODO(production): Add async variants for non-blocking API integration.
    # cancel_workflow is still soft until the worker coordinator checks run
    # status before each expensive stage. Idempotency keys have no TTL today;
    # revisit once durable retention policies land.

    def __init__(self, run_store: WorkflowRunStoreProtocol, *, event_bus: EventBus) -> None:
        self._run_store = run_store
        self._event_bus = event_bus

    def start_workflow(self, request: WorkflowSubmissionRequest) -> WorkflowSubmissionResponse:
        if request.idempotency_key is not None:
            cached = self._run_store.find_by_idempotency_key(
                knowledge_base_id=request.knowledge_base_id,
                idempotency_key=request.idempotency_key,
            )
            if cached is not None:
                self._verify_idempotency_match(cached, request)
                return self._response_from_run(cached)

        workflow_id = generate_id()
        correlation_id = generate_id()
        metadata = dict(request.metadata)
        metadata["correlation_id"] = correlation_id

        try:
            run = self._run_store.save_run(
                WorkflowRun(
                    workflow_id=workflow_id,
                    knowledge_base_id=request.knowledge_base_id,
                    trigger_event_type=request.trigger_event_type,
                    status=WorkflowRunStatus.QUEUED,
                    steps=[WorkflowStepState(step_name=step_name) for step_name in request.requested_steps],
                    metadata=metadata,
                    idempotency_key=request.idempotency_key,
                )
            )
        except ValueError as exc:
            raise AgentConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise AgentStateStoreError("Failed to persist workflow run.") from exc

        try:
            self._event_bus.publish(
                AgentWorkflowStartedEvent(
                    correlation_id=correlation_id,
                    workflows=[
                        AgentWorkflowStartedReference(
                            workflow_id=run.workflow_id,
                            knowledge_base_id=run.knowledge_base_id,
                            trigger_event_type=run.trigger_event_type,
                            step_count=len(run.steps),
                            status=WorkflowRunStatus.RUNNING.value,
                        )
                    ],
                )
            )
        except Exception as exc:
            failed_metadata = dict(run.metadata)
            failed_metadata["publish_error"] = str(exc)
            try:
                self._run_store.update_run(
                    run.workflow_id,
                    WorkflowRunUpdate(
                        status=WorkflowRunStatus.FAILED,
                        updated_at=utc_now(),
                        metadata=failed_metadata,
                    ),
                )
            except Exception as update_exc:
                raise AgentStateStoreError(
                    "Failed to publish workflow event and record failure state."
                ) from update_exc
            raise AgentStateStoreError("Failed to publish workflow event.") from exc

        run = self._run_store.update_run(
            run.workflow_id,
            WorkflowRunUpdate(
                status=WorkflowRunStatus.RUNNING,
                updated_at=utc_now(),
            )
        )
        return self._response_from_run(run)

    def get_workflow_status(self, workflow_id: str) -> WorkflowRun:
        return self._run_store.get_run(workflow_id)

    def list_workflows(
        self,
        *,
        knowledge_base_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRun]:
        return self._run_store.list_runs(
            knowledge_base_id=knowledge_base_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def cancel_workflow(self, workflow_id: str) -> WorkflowRun:
        existing = self._run_store.get_run(workflow_id)
        if existing.status is WorkflowRunStatus.CANCELLED:
            return existing
        if existing.status in TERMINAL_RUN_STATUSES:
            raise WorkflowAlreadyTerminalError(workflow_id, existing.status)
        return self._run_store.update_run(
            workflow_id,
            WorkflowRunUpdate(status=WorkflowRunStatus.CANCELLED, updated_at=utc_now()),
        )

    @staticmethod
    def _verify_idempotency_match(
        run: WorkflowRun, request: WorkflowSubmissionRequest
    ) -> None:
        assert request.idempotency_key is not None  # caller-checked
        if run.trigger_event_type != request.trigger_event_type:
            raise IdempotencyKeyConflictError(
                request.idempotency_key, conflicting_field="trigger_event_type"
            )
        if [step.step_name for step in run.steps] != list(request.requested_steps):
            raise IdempotencyKeyConflictError(
                request.idempotency_key, conflicting_field="requested_steps"
            )
        user_metadata = {
            key: value
            for key, value in run.metadata.items()
            if key not in {"correlation_id", "publish_error"}
        }
        if user_metadata != request.metadata:
            raise IdempotencyKeyConflictError(
                request.idempotency_key, conflicting_field="metadata"
            )

    @staticmethod
    def _response_from_run(run: WorkflowRun) -> WorkflowSubmissionResponse:
        return WorkflowSubmissionResponse(
            workflow_id=run.workflow_id,
            knowledge_base_id=run.knowledge_base_id,
            trigger_event_type=run.trigger_event_type,
            status=run.status,
            step_count=len(run.steps),
            queued_steps=[step.step_name for step in run.steps],
        )


def create_agent_service(
    run_store: WorkflowRunStoreProtocol,
    *,
    event_bus: EventBus,
) -> AgentService:
    """Create the default agent workflow service."""

    return AgentService(run_store, event_bus=event_bus)


__all__ = ["AgentService", "create_agent_service"]
