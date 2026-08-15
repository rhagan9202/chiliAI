"""Service entry point for agent workflow submission flows."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from agent.adapters.protocols import WorkflowRunPage, WorkflowRunStoreProtocol
from agent.definitions import default_workflow_registry
from agent.exceptions import (
    AgentConfigurationError,
    AgentStateStoreError,
    IdempotencyKeyConflictError,
    WorkflowAlreadyTerminalError,
    WorkflowApprovalError,
)
from agent.models import (
    SYSTEM_METADATA_KEYS,
    TERMINAL_RUN_STATUSES,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
)
from agent.service_models import WorkflowSubmissionRequest, WorkflowSubmissionResponse
from events.protocols import EventBus
from events.types import (
    AgentWorkflowStartedEvent,
    AgentWorkflowStartedReference,
    WorkflowStepQueuedEvent,
)
from shared.utils import generate_id, utc_now

logger = logging.getLogger(__name__)


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
        try:
            default_workflow_registry().validate_step_names(request.requested_steps)
        except ValueError as exc:
            raise AgentConfigurationError(str(exc)) from exc

        if request.idempotency_key is not None:
            cached = self._run_store.find_by_idempotency_key(
                knowledge_base_id=request.knowledge_base_id,
                idempotency_key=request.idempotency_key,
            )
            if cached is not None:
                self._verify_idempotency_match(cached, request)
                return self._response_from_run(cached)

        # Create-or-get by correlation id: if the worker's tracker already minted
        # a fallback run for this correlation (it won the race), adopt it instead
        # of creating a duplicate. This makes call ordering relative to the
        # pipeline event publish irrelevant.
        correlation_id = request.correlation_id or generate_id()
        existing = self._run_store.find_by_correlation_id(correlation_id)
        if existing is not None:
            self._verify_correlation_match(existing, request, correlation_id)
            return self._response_from_run(self._backfill_metadata(existing, request))

        workflow_id = generate_id()
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
            # The find-then-save window is not atomic: a worker consuming the
            # pipeline event may fallback-create the run between our find and
            # save. On the store's uniqueness rejection, re-find and adopt the
            # winner instead of surfacing a spurious configuration error.
            existing = self._run_store.find_by_correlation_id(correlation_id)
            if existing is not None:
                self._verify_correlation_match(existing, request, correlation_id)
                return self._response_from_run(self._backfill_metadata(existing, request))
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
        except Exception:
            publish_warning_metadata = dict(run.metadata)
            publish_warning_metadata["workflow_started_publish_error"] = "publish_failed"
            try:
                run = self._run_store.update_run(
                    run.workflow_id,
                    WorkflowRunUpdate(
                        status=WorkflowRunStatus.RUNNING,
                        updated_at=utc_now(),
                        metadata=publish_warning_metadata,
                    ),
                )
            except Exception as update_exc:
                raise AgentStateStoreError(
                    "Failed to record workflow started publish warning."
                ) from update_exc
            return self._response_from_run(run)

        try:
            run = self._run_store.update_run(
                run.workflow_id,
                WorkflowRunUpdate(
                    status=WorkflowRunStatus.RUNNING,
                    updated_at=utc_now(),
                )
            )
        except Exception as exc:
            raise AgentStateStoreError("Failed to mark workflow run as running.") from exc
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
    ) -> WorkflowRunPage:
        return self._run_store.list_runs(
            knowledge_base_id=knowledge_base_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def approve_step(
        self,
        workflow_id: str,
        step_id: str,
        *,
        actor_user_id: str,
        actor_roles: Sequence[str],
    ) -> WorkflowRun:
        """Approve a parked step and resume the run.

        Both halves are required. The workflow executor parks a run by setting
        ``AWAITING_APPROVAL`` and returning, and the worker acks that event
        regardless — so recording the approval without republishing leaves the
        run exactly as stuck as before, with no event in flight to resume from.
        """

        approval_key = f"approved.{step_id}"
        # Checked before the parked-state guard, not after: a successful
        # approval releases the run to QUEUED, so a client retry would
        # otherwise be rejected as "not awaiting approval" — a 409 for an
        # operation that already succeeded.
        already = self._run_store.get_run(workflow_id)
        if already.metadata.get(approval_key):
            return already

        run = self._require_parked_run(workflow_id, step_id)
        if run.actor_user_id is not None and run.actor_user_id == actor_user_id:
            # A gate an actor can satisfy for their own run is not a gate.
            raise WorkflowApprovalError(
                f"Actor '{actor_user_id}' requested run '{workflow_id}' and may "
                "not approve their own step."
            )

        metadata = dict(run.metadata)
        metadata[approval_key] = actor_user_id
        metadata[f"approved_at.{step_id}"] = utc_now().isoformat()
        updated = self._run_store.update_run(
            workflow_id,
            WorkflowRunUpdate(
                # QUEUED, not RUNNING: the executor claims the step itself, and
                # pre-setting RUNNING would make this indistinguishable from a
                # run already in flight.
                status=WorkflowRunStatus.QUEUED,
                metadata=metadata,
                updated_at=utc_now(),
            ),
        )
        self._publish_step(updated, step_id)
        logger.info(
            "Workflow step approved run=%s step=%s approver=%s",
            workflow_id,
            step_id,
            actor_user_id,
        )
        return updated

    def reject_step(
        self,
        workflow_id: str,
        step_id: str,
        *,
        actor_user_id: str,
        actor_roles: Sequence[str],
        reason: str,
    ) -> WorkflowRun:
        """Reject a parked step, failing the run with the reason recorded.

        No step event is published: a rejected run is terminal, and the reason
        is the only useful artifact a reviewer leaves behind.
        """

        run = self._require_parked_run(workflow_id, step_id)
        metadata = dict(run.metadata)
        metadata[f"rejected.{step_id}"] = actor_user_id
        metadata["last_error"] = reason
        updated = self._run_store.update_run(
            workflow_id,
            WorkflowRunUpdate(
                status=WorkflowRunStatus.FAILED,
                metadata=metadata,
                updated_at=utc_now(),
            ),
        )
        logger.info(
            "Workflow step rejected run=%s step=%s approver=%s reason=%s",
            workflow_id,
            step_id,
            actor_user_id,
            reason,
        )
        return updated

    def _require_parked_run(self, workflow_id: str, step_id: str) -> WorkflowRun:
        """Load a run that is genuinely awaiting approval on this step.

        Raises ``WorkflowRunNotFoundError`` for a missing run and
        ``WorkflowApprovalError`` for one in the wrong state — the router maps
        those to 404 and 409, which are different things to an operator acting
        on a stale page.
        """

        run = self._run_store.get_run(workflow_id)
        if run.status is not WorkflowRunStatus.AWAITING_APPROVAL:
            raise WorkflowApprovalError(
                f"Workflow run '{workflow_id}' is not awaiting approval "
                f"(status: {run.status.value})."
            )
        if not any(state.step_name == step_id for state in run.steps):
            raise WorkflowApprovalError(
                f"Workflow run '{workflow_id}' has no step '{step_id}'."
            )
        return run

    def _publish_step(self, run: WorkflowRun, step_id: str) -> None:
        """Re-enqueue the parked step so the executor picks it back up."""

        definition_id = run.metadata.get("definition_id")
        version = run.metadata.get("definition_version")
        if not isinstance(definition_id, str) or not isinstance(version, str):
            # Without the snapshot identity the executor cannot resolve the
            # step, so publishing would dead-letter rather than resume.
            raise WorkflowApprovalError(
                f"Workflow run '{run.workflow_id}' does not record the workflow "
                "definition it started against, so it cannot be resumed."
            )
        self._event_bus.publish(
            WorkflowStepQueuedEvent(
                correlation_id=run.workflow_id,
                knowledge_base_id=run.knowledge_base_id,
                workflow_id=run.workflow_id,
                definition_id=definition_id,
                version=version,
                step_id=step_id,
            )
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
            if key not in SYSTEM_METADATA_KEYS
        }
        if user_metadata != request.metadata:
            raise IdempotencyKeyConflictError(
                request.idempotency_key, conflicting_field="metadata"
            )

    def _backfill_metadata(
        self,
        run: WorkflowRun,
        request: WorkflowSubmissionRequest,
    ) -> WorkflowRun:
        """Write request metadata keys the adopted run does not already carry.

        A caller that adopts a fallback-created run still has facts the worker
        never had — the records API carries its ingest receipt this way. Losing
        them because the worker won the race would make the receipt's survival
        a coin flip. Existing keys are left alone: the run's own record of what
        happened outranks the request's account of what was asked for.
        """

        missing = {
            key: value
            for key, value in request.metadata.items()
            if key not in run.metadata
        }
        if not missing:
            return run
        try:
            return self._run_store.update_run(
                run.workflow_id,
                WorkflowRunUpdate(metadata={**run.metadata, **missing}, updated_at=utc_now()),
            )
        except Exception as exc:
            raise AgentStateStoreError("Failed to record workflow metadata.") from exc

    @staticmethod
    def _verify_correlation_match(
        run: WorkflowRun,
        request: WorkflowSubmissionRequest,
        correlation_id: str,
    ) -> None:
        if run.knowledge_base_id != request.knowledge_base_id:
            raise AgentConfigurationError(
                f"Workflow correlation id '{correlation_id}' already belongs to a "
                "different value for 'knowledge_base_id'."
            )
        if run.trigger_event_type != request.trigger_event_type:
            raise AgentConfigurationError(
                f"Workflow correlation id '{correlation_id}' already belongs to a "
                "different value for 'trigger_event_type'."
            )
        if [step.step_name for step in run.steps] != list(request.requested_steps):
            raise AgentConfigurationError(
                f"Workflow correlation id '{correlation_id}' already belongs to a "
                "different value for 'requested_steps'."
            )
        if run.idempotency_key != request.idempotency_key:
            raise AgentConfigurationError(
                f"Workflow correlation id '{correlation_id}' already belongs to a "
                "different value for 'idempotency_key'."
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
