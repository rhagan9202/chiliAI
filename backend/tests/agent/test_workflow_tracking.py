"""Tests for worker workflow lifecycle tracking."""

from __future__ import annotations

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStepState,
    WorkflowStepStatus,
)
from agent.service import create_agent_service
from agent.service_models import WorkflowSubmissionRequest
from events.adapters.in_memory import InMemoryEventBus
from agent.workflow_tracking import WorkflowEventTracker
from events.types import (
    AgentWorkflowStartedEvent,
    DocumentFailureReference,
    DocumentReference,
    DocumentsFailedEvent,
    DocumentsUploadedEvent,
    RecordsIngestedEvent,
    VectorsIndexedDocumentReference,
    VectorsIndexedEvent,
)


def _uploaded_event(*, correlation_id: str = "corr-1") -> DocumentsUploadedEvent:
    return DocumentsUploadedEvent(
        correlation_id=correlation_id,
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                filename="claims.json",
            )
        ],
    )


def test_tracker_marks_existing_run_step_running_then_completed() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.QUEUED,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)
    event = _uploaded_event()

    assert tracker.begin_event(event) is True
    running = run_store.get_run("workflow-1")
    assert running.status is WorkflowRunStatus.RUNNING
    assert running.steps[0].status is WorkflowStepStatus.RUNNING

    tracker.complete_event(event)
    completed_step = run_store.get_run("workflow-1")
    assert completed_step.status is WorkflowRunStatus.RUNNING
    assert completed_step.steps[0].status is WorkflowStepStatus.COMPLETED


def test_tracker_creates_fallback_run_for_untracked_pipeline_event() -> None:
    run_store = InMemoryWorkflowRunStore()
    tracker = WorkflowEventTracker(run_store)

    assert tracker.begin_event(_uploaded_event(correlation_id="new-corr")) is True

    [run] = run_store.list_runs()
    assert run.knowledge_base_id == "kb-1"
    assert run.metadata["correlation_id"] == "new-corr"
    assert run.steps[0].step_name == "parse"
    assert run.steps[0].status is WorkflowStepStatus.RUNNING


def test_tracker_uses_service_published_correlation_without_fallback() -> None:
    run_store = InMemoryWorkflowRunStore()
    event_bus = InMemoryEventBus()
    service = create_agent_service(run_store, event_bus=event_bus)
    response = service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=["parse"],
        )
    )
    [started_event] = event_bus.published_events
    assert isinstance(started_event, AgentWorkflowStartedEvent)

    tracker = WorkflowEventTracker(run_store)
    assert tracker.begin_event(
        _uploaded_event(correlation_id=started_event.correlation_id)
    ) is True

    [run] = run_store.list_runs()
    assert run.workflow_id == response.workflow_id
    assert run.metadata["correlation_id"] == started_event.correlation_id
    assert run.status is WorkflowRunStatus.RUNNING
    assert run.steps[0].step_name == "parse"
    assert run.steps[0].status is WorkflowStepStatus.RUNNING


def test_tracker_marks_terminal_success_for_vector_indexed_event() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="ready")],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)
    event = VectorsIndexedEvent(
        correlation_id="corr-1",
        documents=[
            VectorsIndexedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extraction-1",
                validation_report_id="validation-1",
                vector_count=1,
                embeddings_storage_key="embeddings.json",
            )
        ],
    )

    tracker.begin_event(event)
    tracker.complete_event(event)

    run = run_store.get_run("workflow-1")
    assert run.status is WorkflowRunStatus.COMPLETED
    assert run.steps[0].status is WorkflowStepStatus.COMPLETED


def test_tracker_marks_document_failure_event_terminal() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)
    event = DocumentsFailedEvent(
        correlation_id="corr-1",
        documents=[
            DocumentFailureReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                error_message="Could not parse document.",
            )
        ],
    )

    assert tracker.begin_event(event) is True
    tracker.complete_event(event)

    run = run_store.get_run("workflow-1")
    assert run.status is WorkflowRunStatus.FAILED
    assert run.steps[0].status is WorkflowStepStatus.FAILED
    assert run.metadata["last_event_type"] == "documents.failed"


def test_tracker_creates_completed_records_workflow_for_untracked_event() -> None:
    run_store = InMemoryWorkflowRunStore()
    tracker = WorkflowEventTracker(run_store)
    event = RecordsIngestedEvent(
        correlation_id="records-corr-1",
        knowledge_base_id="kb-1",
        feed_name="claims",
        record_type="Claim",
        record_count=2,
    )

    assert tracker.begin_event(event) is True
    tracker.complete_event(event)

    [run] = run_store.list_runs()
    assert run.knowledge_base_id == "kb-1"
    assert run.status is WorkflowRunStatus.COMPLETED
    assert run.trigger_event_type == "records.ingested"
    assert run.metadata["correlation_id"] == "records-corr-1"
    assert run.steps[0].step_name == "records_ingest"
    assert run.steps[0].status is WorkflowStepStatus.COMPLETED


def test_tracker_marks_run_failed_after_retry_exhaustion() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    tracker.fail_event(_uploaded_event(), RuntimeError("boom"))

    run = run_store.get_run("workflow-1")
    assert run.status is WorkflowRunStatus.FAILED
    assert run.steps[0].status is WorkflowStepStatus.FAILED
    assert run.metadata["last_error"] == "boom"


def test_tracker_skips_cancelled_workflow() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.CANCELLED,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    assert tracker.begin_event(_uploaded_event()) is False
    run = run_store.get_run("workflow-1")
    assert run.status is WorkflowRunStatus.CANCELLED
    assert run.steps[0].status is WorkflowStepStatus.PENDING
