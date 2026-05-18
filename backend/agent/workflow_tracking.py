"""Workflow lifecycle tracking helpers for the worker coordinator."""

from __future__ import annotations

from dataclasses import dataclass

from agent.adapters.protocols import WorkflowRunStoreProtocol
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
    RecordsIngestedEvent,
    RiskScoredEvent,
    VectorsIndexedEvent,
)
from shared.utils import generate_id, utc_now

__all__ = ["WorkflowEventTracker"]

_STEP_BY_EVENT_TYPE: dict[str, str] = {
    "documents.uploaded": "parse",
    "documents.parsed": "chunk",
    "documents.failed": "parse",
    "records.ingested": "records_ingest",
    "documents.chunked": "extract",
    "entities.extracted": "validate",
    "entities.validated": "graph_build",
    "graph.updated": "embed",
    "embeddings.complete": "vector_index",
    "vectors.indexed": "ready",
    "risk.scored": "monitoring",
}
_DEFAULT_STEP_SEQUENCE: tuple[str, ...] = (
    "parse",
    "chunk",
    "extract",
    "validate",
    "graph_build",
    "embed",
    "vector_index",
    "ready",
    "monitoring",
)
_TERMINAL_SUCCESS_EVENT_TYPES: frozenset[str] = frozenset(
    {"vectors.indexed", "risk.scored", "records.ingested"}
)
_TERMINAL_FAILURE_EVENT_TYPES: frozenset[str] = frozenset({"documents.failed"})
_SYSTEM_METADATA_KEYS: frozenset[str] = frozenset(
    {"correlation_id", "source_event_type", "last_event_type", "last_error"}
)


@dataclass(frozen=True, slots=True)
class _TrackedEvent:
    run: WorkflowRun
    step_name: str


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
            return False
        updated_steps = _steps_with_status(
            tracked.run.steps,
            tracked.step_name,
            WorkflowStepStatus.RUNNING,
        )
        metadata = dict(tracked.run.metadata)
        metadata["last_event_type"] = event.event_type
        self._run_store.update_run(
            tracked.run.workflow_id,
            WorkflowRunUpdate(
                status=WorkflowRunStatus.RUNNING,
                steps=updated_steps,
                metadata=metadata,
                updated_at=utc_now(),
            ),
        )
        return True

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
        if event.event_type in _TERMINAL_FAILURE_EVENT_TYPES:
            status = WorkflowRunStatus.FAILED
        elif event.event_type in _TERMINAL_SUCCESS_EVENT_TYPES:
            status = WorkflowRunStatus.COMPLETED
        else:
            status = WorkflowRunStatus.RUNNING
        self._run_store.update_run(
            tracked.run.workflow_id,
            WorkflowRunUpdate(
                status=status,
                steps=updated_steps,
                metadata=metadata,
                updated_at=utc_now(),
            ),
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
        self._run_store.update_run(
            tracked.run.workflow_id,
            WorkflowRunUpdate(
                status=WorkflowRunStatus.FAILED,
                steps=updated_steps,
                metadata=metadata,
                updated_at=utc_now(),
            ),
        )

    def _resolve_tracked_event(self, event: AnyEvent) -> _TrackedEvent | None:
        step_name = _STEP_BY_EVENT_TYPE.get(event.event_type)
        if step_name is None:
            return None
        run = self._find_by_correlation_id(event.correlation_id)
        if run is None:
            run = self._create_fallback_run(event)
            if run is None:
                return None
        return _TrackedEvent(run=run, step_name=step_name)

    def _find_by_correlation_id(self, correlation_id: str) -> WorkflowRun | None:
        for run in self._run_store.list_runs(limit=1000):
            if run.metadata.get("correlation_id") == correlation_id:
                return run
        return None

    def _create_fallback_run(self, event: AnyEvent) -> WorkflowRun | None:
        knowledge_base_id = _knowledge_base_id_for_event(event)
        if knowledge_base_id is None:
            return None
        step_name = _STEP_BY_EVENT_TYPE[event.event_type]
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
    if current_step not in _DEFAULT_STEP_SEQUENCE:
        return [
            WorkflowStepState(
                step_name=current_step,
                status=WorkflowStepStatus.RUNNING,
            )
        ]
    steps: list[WorkflowStepState] = []
    for step_name in _DEFAULT_STEP_SEQUENCE:
        status = WorkflowStepStatus.PENDING
        if step_name == current_step:
            status = WorkflowStepStatus.RUNNING
        elif _DEFAULT_STEP_SEQUENCE.index(step_name) < _DEFAULT_STEP_SEQUENCE.index(current_step):
            status = WorkflowStepStatus.COMPLETED
        steps.append(WorkflowStepState(step_name=step_name, status=status))
    return steps


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
    if isinstance(event, RiskScoredEvent) and event.assessments:
        return event.assessments[0].knowledge_base_id
    return None
