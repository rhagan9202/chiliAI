"""Tests for worker workflow lifecycle tracking."""

from __future__ import annotations

from datetime import datetime, timedelta

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
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
    KnowledgeBaseReadyEvent,
    KnowledgeBaseReadyReference,
    RecordsIngestedEvent,
    VectorsIndexedDocumentReference,
    VectorsIndexedEvent,
)
from shared.utils import utc_now


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


def test_is_run_cancelled_reflects_store_state() -> None:
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

    assert tracker.is_run_cancelled("corr-1") is False
    assert tracker.is_run_cancelled("missing") is False

    run_store.update_run(
        "workflow-1", WorkflowRunUpdate(status=WorkflowRunStatus.CANCELLED)
    )
    assert tracker.is_run_cancelled("corr-1") is True


def test_complete_event_does_not_clobber_cancelled_run() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.CANCELLED,
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
                embeddings_storage_key="ek",
                record_ids=["r-1"],
            )
        ],
    )

    tracker.complete_event(event)

    assert run_store.get_run("workflow-1").status is WorkflowRunStatus.CANCELLED


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


def test_tracker_marks_kb_ready_event_terminal_for_zero_vector_workflow() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-ready",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(step_name="ready"),
                    WorkflowStepState(step_name="monitoring"),
                ],
                metadata={"correlation_id": "corr-ready"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)
    event = KnowledgeBaseReadyEvent(
        correlation_id="corr-ready",
        knowledge_bases=[
            KnowledgeBaseReadyReference(
                knowledge_base_id="kb-1",
                entity_count=0,
                relationship_count=0,
                vector_count=0,
            )
        ],
    )

    assert tracker.begin_event(event) is True
    tracker.complete_event(event)

    run = run_store.get_run("workflow-ready")
    assert run.status is WorkflowRunStatus.COMPLETED
    assert run.steps[0].status is WorkflowStepStatus.COMPLETED
    assert run.metadata["last_event_type"] == "kb.ready"
    assert run.metadata["entity_count"] == 0
    assert run.metadata["vector_count"] == 0


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


# ---------------------------------------------------------------------------
# is_busy tests
# ---------------------------------------------------------------------------


def test_is_busy_returns_false_when_no_workflows_for_kb() -> None:
    run_store = InMemoryWorkflowRunStore()
    tracker = WorkflowEventTracker(run_store)

    assert tracker.is_busy("kb-99") is False


def test_is_busy_returns_true_when_queued_workflow_exists() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-queued",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.QUEUED,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-queued"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    assert tracker.is_busy("kb-1") is True


def test_is_busy_returns_true_when_running_workflow_exists() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-running",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-running"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    assert tracker.is_busy("kb-1") is True


def test_is_busy_returns_false_when_only_terminal_workflows_exist() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-completed",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[WorkflowStepState(step_name="ready")],
                metadata={"correlation_id": "corr-completed"},
            ),
            WorkflowRun(
                workflow_id="workflow-failed",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.FAILED,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-failed"},
            ),
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    assert tracker.is_busy("kb-1") is False


def test_reconcile_stale_runs_marks_old_running_workflow_failed() -> None:
    old_time = utc_now() - timedelta(hours=3)
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-stale",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(
                        step_name="vector_index",
                        status=WorkflowStepStatus.RUNNING,
                    )
                ],
                updated_at=old_time,
                metadata={"correlation_id": "corr-stale"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    reconciled = tracker.reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 1
    run = run_store.get_run("workflow-stale")
    assert run.status is WorkflowRunStatus.FAILED
    assert run.metadata["reason"] == "stale_workflow_reconciled"


def test_reconcile_stale_runs_keeps_recent_queued_and_running_workflows() -> None:
    recent_time = utc_now()
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-recent-queued",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.QUEUED,
                steps=[WorkflowStepState(step_name="parse")],
                updated_at=recent_time,
                metadata={"correlation_id": "corr-recent-queued"},
            ),
            WorkflowRun(
                workflow_id="workflow-recent-running",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(
                        step_name="vector_index",
                        status=WorkflowStepStatus.RUNNING,
                    )
                ],
                updated_at=recent_time,
                metadata={"correlation_id": "corr-recent-running"},
            ),
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    reconciled = tracker.reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 0
    assert run_store.get_run("workflow-recent-queued").status is WorkflowRunStatus.QUEUED
    assert (
        run_store.get_run("workflow-recent-running").status
        is WorkflowRunStatus.RUNNING
    )


def test_reconcile_stale_runs_keeps_terminal_workflows() -> None:
    old_time = utc_now() - timedelta(hours=3)
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-completed-old",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[WorkflowStepState(step_name="ready")],
                updated_at=old_time,
                metadata={"correlation_id": "corr-completed-old"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    reconciled = tracker.reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 0
    run = run_store.get_run("workflow-completed-old")
    assert run.status is WorkflowRunStatus.COMPLETED
    assert "reason" not in run.metadata


def test_reconcile_stale_runs_does_not_overwrite_completed_run_after_listing() -> None:
    old_time = utc_now() - timedelta(hours=3)
    listed_run = WorkflowRun(
        workflow_id="workflow-raced",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        status=WorkflowRunStatus.RUNNING,
        steps=[
            WorkflowStepState(
                step_name="vector_index",
                status=WorkflowStepStatus.RUNNING,
            )
        ],
        updated_at=old_time,
        metadata={"correlation_id": "corr-raced"},
    )
    class RaceWorkflowRunStore(InMemoryWorkflowRunStore):
        def list_runs(
            self,
            *,
            knowledge_base_id: str | None = None,
            status: WorkflowRunStatus | None = None,
            limit: int = 50,
            offset: int = 0,
        ) -> list[WorkflowRun]:
            if status is WorkflowRunStatus.RUNNING and offset == 0:
                return [listed_run]
            return []

        def get_run(self, workflow_id: str) -> WorkflowRun:
            assert workflow_id == "workflow-raced"
            return listed_run

        def update_run_if_current(
            self,
            workflow_id: str,
            update: WorkflowRunUpdate,
            *,
            expected_statuses: set[WorkflowRunStatus] | frozenset[WorkflowRunStatus],
            updated_before: datetime | None = None,
        ) -> WorkflowRun | None:
            assert workflow_id == "workflow-raced"
            assert expected_statuses == {
                WorkflowRunStatus.QUEUED,
                WorkflowRunStatus.RUNNING,
            }
            assert update.status is WorkflowRunStatus.FAILED
            assert updated_before is not None
            assert listed_run.updated_at < updated_before
            return None

        def update_run(
            self,
            workflow_id: str,
            update: WorkflowRunUpdate,
        ) -> WorkflowRun:
            raise AssertionError("completed workflow must not be overwritten")

    tracker = WorkflowEventTracker(RaceWorkflowRunStore())

    reconciled = tracker.reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 0


def test_reconcile_stale_runs_pages_through_all_stale_workflows() -> None:
    old_time = utc_now() - timedelta(hours=3)
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id=f"workflow-stale-{index}",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(
                        step_name="vector_index",
                        status=WorkflowStepStatus.RUNNING,
                    )
                ],
                updated_at=old_time,
                metadata={"correlation_id": f"corr-stale-{index}"},
            )
            for index in range(3)
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    reconciled = tracker.reconcile_stale_runs(max_age_seconds=3600, batch_size=2)

    assert reconciled == 3
    assert all(
        run.status is WorkflowRunStatus.FAILED for run in run_store.list_runs(limit=10)
    )
