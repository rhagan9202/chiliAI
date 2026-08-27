"""Workflow lifecycle tracking helpers for the worker coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.definitions import default_workflow_registry
from agent.exceptions import WorkflowRunNotFoundError
from agent.models import (
    TERMINAL_RUN_STATUSES,
    MetadataValue,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
    WorkflowStepStatus,
)
from events.types import (
    AnyEvent,
    DocumentsChunkedEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EmbeddingsCompleteEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    GraphUpdatedEvent,
    KnowledgeBaseReadyEvent,
    RecordsIngestedEvent,
    RiskScoredEvent,
    VectorsIndexedEvent,
)
from shared.utils import generate_id, utc_now

__all__ = [
    "RECONCILABLE_RUN_STATUSES",
    "WorkflowEventTracker",
    "default_steps_for_trigger",
]

_WORKFLOW_REGISTRY = default_workflow_registry()
_TERMINAL_SUCCESS_EVENT_TYPES: frozenset[str] = frozenset(
    {"vectors.indexed", "kb.ready", "risk.scored", "records.ingested"}
)
_TERMINAL_FAILURE_EVENT_TYPES: frozenset[str] = frozenset({"documents.failed"})
# Statuses in which a *pipeline* run accepts step transitions. Distinct from
# RECONCILABLE_RUN_STATUSES below despite listing the same two: this gates
# begin/complete_event for ingestion-triggered runs, which never reach
# AWAITING_APPROVAL — only the workflow-definition executor parks a run.
_ACTIVE_RUN_STATUSES: frozenset[WorkflowRunStatus] = frozenset(
    {WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING}
)


def default_steps_for_trigger(trigger_event_type: str) -> list[str]:
    """Return the declared step-name plan for a pipeline trigger event.

    Single source of truth (the same step maps the tracker uses) shared with
    the API: when a route starts a run via ``AgentService`` it declares these
    steps so a service-created run and a tracker fallback agree on shape. A
    document trigger expands to the full canonical sequence; a records trigger
    is a single step; an unknown trigger defaults to the full sequence.
    """

    first_step = _WORKFLOW_REGISTRY.step_for_event_type(trigger_event_type)
    if first_step is None:
        return _WORKFLOW_REGISTRY.default_step_names()
    if first_step in _WORKFLOW_REGISTRY.default_step_names():
        return _WORKFLOW_REGISTRY.default_step_names()
    return [first_step]


@dataclass(frozen=True, slots=True)
class _TrackedEvent:
    run: WorkflowRun
    step_name: str


# Statuses stale reconciliation may reap.
#
# AWAITING_APPROVAL is deliberately absent and must stay absent: a run parked
# on a human gate is alive and waiting for a person, so "has not progressed in
# an hour" is its normal condition, not a fault. Adding it here would fail work
# that is proceeding correctly, and the analyst who eventually approves would
# find the run already dead.
RECONCILABLE_RUN_STATUSES: tuple[WorkflowRunStatus, ...] = (
    WorkflowRunStatus.QUEUED,
    WorkflowRunStatus.RUNNING,
)


class WorkflowEventTracker:
    """Persist workflow lifecycle state while the worker handles events."""

    def __init__(self, run_store: WorkflowRunStoreProtocol) -> None:
        self._run_store = run_store

    def begin_event(self, event: AnyEvent) -> bool:
        """Mark the event's workflow step running.

        Returns ``False`` when the associated run is already terminal. The
        coordinator uses this to skip cancelled or already-finished workflows.
        """

        tracked = self._resolve_tracked_event(event)
        if tracked is None:
            return True
        if tracked.run.status in TERMINAL_RUN_STATUSES:
            # A FAILED run is not a processing gate: with per-document failure
            # isolation (BL-041) a `documents.failed` event fails the run
            # record while sibling documents in the same batch are still in
            # flight — their successor events must keep processing, with the
            # run record left frozen at FAILED. Cancelled runs stay gated
            # (user intent); completed runs stay gated (replay safety).
            return tracked.run.status is WorkflowRunStatus.FAILED
        updated_steps = _steps_with_status(
            tracked.run.steps,
            tracked.step_name,
            WorkflowStepStatus.RUNNING,
        )
        metadata = dict(tracked.run.metadata)
        metadata["last_event_type"] = event.event_type
        # CAS on non-terminal status so a cancel that lands between resolving
        # the run and this write is never clobbered: if the run is now CANCELLED
        # the update is a no-op and we report the step as skipped.
        updated = self._run_store.update_run_if_current(
            tracked.run.workflow_id,
            WorkflowRunUpdate(
                status=WorkflowRunStatus.RUNNING,
                steps=updated_steps,
                metadata=metadata,
                updated_at=utc_now(),
            ),
            expected_statuses=_ACTIVE_RUN_STATUSES,
        )
        return updated is not None

    def complete_event(self, event: AnyEvent) -> None:
        """Mark the current workflow step complete after handler success."""

        tracked = self._resolve_tracked_event(event)
        if tracked is None or tracked.run.status in TERMINAL_RUN_STATUSES:
            return
        updated_steps = _steps_with_status(
            tracked.run.steps,
            tracked.step_name,
            (
                WorkflowStepStatus.FAILED
                if event.event_type in _TERMINAL_FAILURE_EVENT_TYPES
                else WorkflowStepStatus.COMPLETED
            ),
        )
        metadata = dict(tracked.run.metadata)
        metadata["last_event_type"] = event.event_type
        metadata.update(_summary_metadata_for_event(event))
        if event.event_type in _TERMINAL_FAILURE_EVENT_TYPES:
            status = WorkflowRunStatus.FAILED
        elif event.event_type in _TERMINAL_SUCCESS_EVENT_TYPES:
            status = WorkflowRunStatus.COMPLETED
        else:
            status = WorkflowRunStatus.RUNNING
        # CAS on non-terminal status so a concurrent cancel is not overwritten.
        self._run_store.update_run_if_current(
            tracked.run.workflow_id,
            WorkflowRunUpdate(
                status=status,
                steps=updated_steps,
                metadata=metadata,
                updated_at=utc_now(),
            ),
            expected_statuses=_ACTIVE_RUN_STATUSES,
        )

    def fail_event(self, event: AnyEvent, error: BaseException) -> None:
        """Mark the associated workflow failed after retry exhaustion."""

        tracked = self._resolve_tracked_event(event)
        if tracked is None or tracked.run.status in TERMINAL_RUN_STATUSES:
            return
        updated_steps = _steps_with_status(
            tracked.run.steps,
            tracked.step_name,
            WorkflowStepStatus.FAILED,
        )
        metadata = dict(tracked.run.metadata)
        metadata["last_event_type"] = event.event_type
        metadata["last_error"] = str(error)
        # CAS on non-terminal status: a user cancel takes precedence over a
        # retry-exhaustion failure rather than being overwritten by it.
        self._run_store.update_run_if_current(
            tracked.run.workflow_id,
            WorkflowRunUpdate(
                status=WorkflowRunStatus.FAILED,
                steps=updated_steps,
                metadata=metadata,
                updated_at=utc_now(),
            ),
            expected_statuses=_ACTIVE_RUN_STATUSES,
        )

    def is_busy(self, knowledge_base_id: str) -> bool:
        """Return True when the KB has at least one non-terminal workflow run.

        Satisfies the ``WorkflowBusyTracker`` protocol in ``api._kb_busy`` so
        this tracker can be passed directly to ``ensure_kb_idle``.
        """
        for status in RECONCILABLE_RUN_STATUSES:
            runs = self._run_store.list_runs(
                knowledge_base_id=knowledge_base_id,
                status=status,
                limit=1,
            )
            if runs.items:
                return True
        return False

    def reconcile_stale_runs(
        self,
        *,
        max_age_seconds: int,
        batch_size: int = 1000,
    ) -> int:
        """Mark old queued/running runs failed so UI and busy checks do not hang."""
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be greater than 0.")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0.")
        now = utc_now()
        cutoff = now - timedelta(seconds=max_age_seconds)
        candidates: list[str] = []
        for status in (WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING):
            offset = 0
            while True:
                runs = self._run_store.list_runs(
                    status=status,
                    limit=batch_size,
                    offset=offset,
                )
                if not runs.items:
                    break
                candidates.extend(run.workflow_id for run in runs.items)
                if not runs.has_more or runs.next_offset is None:
                    break
                offset = runs.next_offset

        reconciled = 0
        for workflow_id in candidates:
            try:
                run = self._run_store.get_run(workflow_id)
            except WorkflowRunNotFoundError:
                continue
            if run.status not in RECONCILABLE_RUN_STATUSES:
                continue
            if run.updated_at >= cutoff:
                continue
            metadata = dict(run.metadata)
            metadata["reason"] = "stale_workflow_reconciled"
            updated = self._run_store.update_run_if_current(
                run.workflow_id,
                WorkflowRunUpdate(
                    status=WorkflowRunStatus.FAILED,
                    metadata=metadata,
                    updated_at=now,
                ),
                expected_statuses=set(RECONCILABLE_RUN_STATUSES),
                updated_before=cutoff,
            )
            if updated is not None:
                reconciled += 1
        return reconciled

    def _resolve_tracked_event(self, event: AnyEvent) -> _TrackedEvent | None:
        step_name = _WORKFLOW_REGISTRY.step_for_event_type(event.event_type)
        if step_name is None:
            return None
        run = self._find_by_correlation_id(event.correlation_id)
        if run is None:
            run = self._create_fallback_run(event)
            if run is None:
                return None
        return _TrackedEvent(run=run, step_name=step_name)

    def is_run_cancelled(self, correlation_id: str) -> bool:
        """Return True when the run for ``correlation_id`` has been cancelled.

        Used by long worker handlers to abort cooperatively at loop boundaries.
        """

        run = self._run_store.find_by_correlation_id(correlation_id)
        return run is not None and run.status is WorkflowRunStatus.CANCELLED

    def _find_by_correlation_id(self, correlation_id: str) -> WorkflowRun | None:
        return self._run_store.find_by_correlation_id(correlation_id)

    def _create_fallback_run(self, event: AnyEvent) -> WorkflowRun | None:
        knowledge_base_id = _knowledge_base_id_for_event(event)
        if knowledge_base_id is None:
            return None
        step_name = _WORKFLOW_REGISTRY.step_for_event_type(event.event_type)
        if step_name is None:
            return None
        default_step_sequence = _WORKFLOW_REGISTRY.default_step_names()
        if step_name in default_step_sequence and default_step_sequence.index(step_name):
            # A mid-pipeline step with no run behind it. Representing this as a
            # run would assert a whole multi-step pipeline that nothing
            # observed starting — and for a terminal-success event type
            # ``complete_event`` would immediately close it as a successful
            # end-to-end ingestion. ``risk.scored`` maps to the *last* step and
            # analytics emits one per entity, so accepting these manufactures a
            # phantom "successful ingestion" per scored entity, each of which
            # also counts as busy against ``is_busy`` and blocks uploads.
            #
            # Standalone steps (``records_ingest``) and genuine first steps are
            # still tracked: a one-step run records exactly what was seen.
            return None
        steps = _fallback_steps(step_name)
        metadata: dict[str, MetadataValue] = {
            "correlation_id": event.correlation_id,
            "source_event_type": event.event_type,
        }
        return self._run_store.save_run(
            WorkflowRun(
                workflow_id=generate_id(),
                knowledge_base_id=knowledge_base_id,
                trigger_event_type=event.event_type,
                status=WorkflowRunStatus.RUNNING,
                steps=steps,
                metadata=metadata,
            )
        )


def _steps_with_status(
    steps: list[WorkflowStepState],
    step_name: str,
    status: WorkflowStepStatus,
) -> list[WorkflowStepState]:
    if not any(step.step_name == step_name for step in steps):
        steps = [*steps, WorkflowStepState(step_name=step_name)]
    updated_steps: list[WorkflowStepState] = []
    target_index = next(
        index for index, step in enumerate(steps) if step.step_name == step_name
    )
    for index, step in enumerate(steps):
        next_status = step.status
        if index == target_index:
            next_status = status
        elif index < target_index and step.status is WorkflowStepStatus.PENDING:
            next_status = WorkflowStepStatus.COMPLETED
        updated_steps.append(step.model_copy(update={"status": next_status}))
    return updated_steps


def _fallback_steps(current_step: str) -> list[WorkflowStepState]:
    default_step_sequence = _WORKFLOW_REGISTRY.default_step_names()
    if current_step not in default_step_sequence:
        return [
            WorkflowStepState(
                step_name=current_step,
                status=WorkflowStepStatus.RUNNING,
            )
        ]
    steps: list[WorkflowStepState] = []
    for step_name in default_step_sequence:
        # Earlier steps stay PENDING. The run is a fallback precisely because
        # nothing tracked the events that would have completed them, so
        # marking them COMPLETED reports work that was never observed.
        status = (
            WorkflowStepStatus.RUNNING
            if step_name == current_step
            else WorkflowStepStatus.PENDING
        )
        steps.append(WorkflowStepState(step_name=step_name, status=status))
    return steps


def _summary_metadata_for_event(event: AnyEvent) -> dict[str, MetadataValue]:
    if isinstance(event, KnowledgeBaseReadyEvent) and event.knowledge_bases:
        first = event.knowledge_bases[0]
        return {
            "entity_count": first.entity_count,
            "relationship_count": first.relationship_count,
            "vector_count": first.vector_count,
        }
    return {}


def _knowledge_base_id_for_event(event: AnyEvent) -> str | None:
    if isinstance(
        event,
        (
            DocumentsUploadedEvent,
            DocumentsParsedEvent,
            DocumentsChunkedEvent,
            EntitiesExtractedEvent,
            EntitiesValidatedEvent,
            GraphUpdatedEvent,
            EmbeddingsCompleteEvent,
            VectorsIndexedEvent,
            DocumentsFailedEvent,
        ),
    ):
        references = event.documents
        if references:
            return references[0].knowledge_base_id
    if isinstance(event, RecordsIngestedEvent):
        return event.knowledge_base_id
    if isinstance(event, KnowledgeBaseReadyEvent) and event.knowledge_bases:
        return event.knowledge_bases[0].knowledge_base_id
    if isinstance(event, RiskScoredEvent) and event.assessments:
        return event.assessments[0].knowledge_base_id
    return None
