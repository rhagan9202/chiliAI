"""Tests for worker workflow lifecycle tracking."""

from __future__ import annotations

from datetime import datetime, timedelta

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.adapters.protocols import WorkflowRunPage
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
from agent.definitions import default_workflow_registry
from agent.workflow_tracking import WorkflowEventTracker, default_steps_for_trigger
from events.types import (
    AgentWorkflowStartedEvent,
    DocumentFailureReference,
    DocumentReference,
    DocumentsFailedEvent,
    DocumentsUploadedEvent,
    KnowledgeBaseReadyEvent,
    KnowledgeBaseReadyReference,
    RecordsIngestedEvent,
    RiskScoredEvent,
    RiskScoredReference,
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


def test_default_steps_for_trigger_matches_registered_default_plan() -> None:
    registry = default_workflow_registry()

    assert default_steps_for_trigger("documents.uploaded") == registry.default_step_names()
    assert default_steps_for_trigger("documents.parsed") == registry.default_step_names()
    assert default_steps_for_trigger("records.ingested") == ["records_ingest"]
    assert default_steps_for_trigger("unknown.event") == registry.default_step_names()


def test_tracker_creates_fallback_run_for_untracked_pipeline_event() -> None:
    run_store = InMemoryWorkflowRunStore()
    tracker = WorkflowEventTracker(run_store)

    assert tracker.begin_event(_uploaded_event(correlation_id="new-corr")) is True

    [run] = run_store.list_runs().items
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

    [run] = run_store.list_runs().items
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

    [run] = run_store.list_runs().items
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


def test_tracker_last_error_falls_back_to_the_exception_type() -> None:
    """``str(RuntimeError())`` is ``''``; ``last_error`` is what the UI shows.

    A failed run whose only explanation is an empty string tells an operator
    nothing. This is the same exception, arriving via the same ``on_failure``
    callback from the same failure block as the DLQ record's ``error_message``,
    so the two must not disagree about what the failure was.
    """

    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-empty-error",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    tracker.fail_event(_uploaded_event(), RuntimeError())

    run = run_store.get_run("workflow-empty-error")
    assert run.status is WorkflowRunStatus.FAILED
    assert run.metadata["last_error"] == "RuntimeError"


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


def test_tracker_skips_completed_workflow() -> None:
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    assert tracker.begin_event(_uploaded_event()) is False


def test_tracker_processes_surviving_documents_after_per_document_failure() -> None:
    """A run failed by a per-document ``documents.failed`` must not swallow
    the batch's surviving documents (BL-041 failure isolation): successor
    events keep processing while the run record stays frozen at FAILED."""
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.FAILED,
                steps=[
                    WorkflowStepState(
                        step_name="parse", status=WorkflowStepStatus.FAILED
                    ),
                    WorkflowStepState(step_name="chunk"),
                ],
                metadata={"correlation_id": "corr-1"},
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    assert tracker.begin_event(_uploaded_event()) is True
    run = run_store.get_run("workflow-1")
    assert run.status is WorkflowRunStatus.FAILED
    assert run.steps[0].status is WorkflowStepStatus.FAILED


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
        ) -> WorkflowRunPage:
            if status is WorkflowRunStatus.RUNNING and offset == 0:
                return WorkflowRunPage(
                    items=[listed_run],
                    has_more=False,
                    next_offset=None,
                )
            return WorkflowRunPage(items=[], has_more=False, next_offset=None)

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
        run.status is WorkflowRunStatus.FAILED
        for run in run_store.list_runs(limit=10).items
    )


def test_reconcile_does_not_fail_a_run_awaiting_approval() -> None:
    """An approval left overnight is not a stalled run.

    A run parked on a human gate is alive and waiting for a person, by design.
    Reaping it would fail work that was proceeding correctly, and the analyst
    who eventually clicks approve would find the run already dead.
    """
    old_time = utc_now() - timedelta(hours=48)
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-parked",
                knowledge_base_id="kb-1",
                trigger_event_type="workflow_definition.requested",
                status=WorkflowRunStatus.AWAITING_APPROVAL,
                steps=[
                    WorkflowStepState(
                        step_name="notify",
                        status=WorkflowStepStatus.PENDING,
                    )
                ],
                updated_at=old_time,
            )
        ]
    )
    tracker = WorkflowEventTracker(run_store)

    reconciled = tracker.reconcile_stale_runs(max_age_seconds=3600)

    assert reconciled == 0
    assert (
        run_store.get_run("workflow-parked").status
        == WorkflowRunStatus.AWAITING_APPROVAL
    )


def test_reconcilable_statuses_exclude_awaiting_approval() -> None:
    """A structural guard, so a later edit cannot quietly reintroduce it.

    The behavioural test above passes today because the scan happens to iterate
    two statuses. This asserts the *intent*, so adding AWAITING_APPROVAL to the
    set fails here with an explanation rather than silently reaping parked runs
    in production.
    """
    from agent.workflow_tracking import RECONCILABLE_RUN_STATUSES

    assert WorkflowRunStatus.AWAITING_APPROVAL not in RECONCILABLE_RUN_STATUSES
    assert RECONCILABLE_RUN_STATUSES == (
        WorkflowRunStatus.QUEUED,
        WorkflowRunStatus.RUNNING,
    )


def _risk_scored_event(*, correlation_id: str = "corr-orphan") -> RiskScoredEvent:
    return RiskScoredEvent(
        correlation_id=correlation_id,
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="req-1",
                entity_id="provider:1",
                overall_score=0.9,
                risk_level="high",
                factor_count=1,
                factors=[],
            )
        ],
    )


class TestOrphanTerminalEventsDoNotFabricateHistory:
    """A late terminal event whose run is unknown must not invent one.

    ``risk.scored`` maps to the last step in the default sequence, so a
    fallback run built for it marks every preceding step COMPLETED and is then
    closed as COMPLETED — a run claiming a full successful ingestion that
    never happened. Analytics scoring emits one of these per entity, so a
    single batch can manufacture thousands of them.
    """

    def test_an_orphan_risk_scored_event_does_not_report_earlier_steps_complete(
        self,
    ) -> None:
        store = InMemoryWorkflowRunStore()
        tracker = WorkflowEventTracker(store)

        tracker.begin_event(_risk_scored_event())

        runs = store.list_runs(knowledge_base_id="kb-1").items
        fabricated_completions = [
            step.step_name
            for run in runs
            for step in run.steps
            if step.status is WorkflowStepStatus.COMPLETED
        ]
        assert fabricated_completions == [], (
            "a fallback run reported steps as COMPLETED that never ran: "
            f"{fabricated_completions}"
        )

    def test_an_orphan_risk_scored_event_does_not_complete_a_whole_run(self) -> None:
        store = InMemoryWorkflowRunStore()
        tracker = WorkflowEventTracker(store)
        event = _risk_scored_event()

        tracker.begin_event(event)
        tracker.complete_event(event)

        completed = [
            run
            for run in store.list_runs(knowledge_base_id="kb-1").items
            if run.status is WorkflowRunStatus.COMPLETED
        ]
        assert completed == [], (
            "an orphan risk.scored event closed a run as a successful full pipeline"
        )


def _risk_scored_fan_out_event(
    *, correlation_id: str, entity_id: str
) -> RiskScoredEvent:
    return RiskScoredEvent(
        correlation_id=correlation_id,
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id=f"risk:{correlation_id}:kb-1:{entity_id}",
                entity_id=entity_id,
                overall_score=0.9,
                risk_level="high",
                factor_count=1,
                factors=[],
            )
        ],
    )


def _pipeline_run(
    *,
    correlation_id: str = "corr-fanout",
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING,
) -> WorkflowRun:
    return WorkflowRun(
        workflow_id="workflow-fanout",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        status=status,
        steps=[
            WorkflowStepState(step_name=step_name)
            for step_name in default_steps_for_trigger("documents.uploaded")
        ],
        metadata={"correlation_id": correlation_id},
    )


def _vectors_indexed_event(*, correlation_id: str) -> VectorsIndexedEvent:
    return VectorsIndexedEvent(
        correlation_id=correlation_id,
        documents=[
            VectorsIndexedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extraction-1",
                validation_report_id="validation-1",
                vector_count=3,
                embeddings_storage_key="embeddings.json",
            )
        ],
    )


class TestPerEntityRiskScoredFanOut:
    """``risk.scored`` is emitted once per entity under one correlation id.

    Analytics fans out one event per scored entity on the triggering
    pipeline's correlation id, so the run they resolve to is shared by all of
    them. A shared run must not be closed — nor its siblings gated — by any
    single per-entity event.
    """

    def test_every_entity_in_a_fan_out_begins_not_only_the_first(self) -> None:
        store = InMemoryWorkflowRunStore(runs=[_pipeline_run()])
        tracker = WorkflowEventTracker(store)

        began: list[bool] = []
        for entity_id in ("provider:1", "provider:2", "provider:3"):
            event = _risk_scored_fan_out_event(
                correlation_id="corr-fanout", entity_id=entity_id
            )
            began.append(tracker.begin_event(event))
            tracker.complete_event(event)

        assert began == [True, True, True], (
            "the first per-entity risk.scored closed the shared run, so every "
            f"later entity was skipped: {began}"
        )

    def test_a_fan_out_event_completes_the_monitoring_step(self) -> None:
        store = InMemoryWorkflowRunStore(runs=[_pipeline_run()])
        tracker = WorkflowEventTracker(store)
        event = _risk_scored_fan_out_event(
            correlation_id="corr-fanout", entity_id="provider:1"
        )

        assert tracker.begin_event(event) is True
        tracker.complete_event(event)

        run = store.get_run("workflow-fanout")
        monitoring = next(
            step for step in run.steps if step.step_name == "monitoring"
        )
        assert monitoring.status is WorkflowStepStatus.COMPLETED

    def test_a_fan_out_event_does_not_close_the_shared_pipeline_run(self) -> None:
        store = InMemoryWorkflowRunStore(runs=[_pipeline_run()])
        tracker = WorkflowEventTracker(store)
        event = _risk_scored_fan_out_event(
            correlation_id="corr-fanout", entity_id="provider:1"
        )

        tracker.begin_event(event)
        tracker.complete_event(event)

        assert store.get_run("workflow-fanout").status is WorkflowRunStatus.RUNNING

    def test_a_fan_out_event_does_not_report_unrun_steps_as_completed(self) -> None:
        store = InMemoryWorkflowRunStore(runs=[_pipeline_run()])
        tracker = WorkflowEventTracker(store)
        event = _risk_scored_fan_out_event(
            correlation_id="corr-fanout", entity_id="provider:1"
        )

        tracker.begin_event(event)
        tracker.complete_event(event)

        statuses = {
            step.step_name: step.status for step in store.get_run("workflow-fanout").steps
        }
        assert statuses["vector_index"] is WorkflowStepStatus.PENDING
        assert statuses["ready"] is WorkflowStepStatus.PENDING

    def test_the_run_still_completes_on_its_terminal_event_after_a_fan_out(
        self,
    ) -> None:
        """The original defect must not come back: runs must not hang.

        ``risk.scored`` reaches the worker before ``vectors.indexed`` (it is
        published from the ``graph.updated`` handler), so the pipeline's own
        terminal event has to survive the fan-out and still close the run.
        """

        store = InMemoryWorkflowRunStore(runs=[_pipeline_run()])
        tracker = WorkflowEventTracker(store)
        fan_out = _risk_scored_fan_out_event(
            correlation_id="corr-fanout", entity_id="provider:1"
        )
        tracker.begin_event(fan_out)
        tracker.complete_event(fan_out)

        terminal = _vectors_indexed_event(correlation_id="corr-fanout")
        assert tracker.begin_event(terminal) is True
        tracker.complete_event(terminal)

        run = store.get_run("workflow-fanout")
        assert run.status is WorkflowRunStatus.COMPLETED
        assert run.workflow_id not in [
            stale.workflow_id
            for stale in store.list_runs(status=WorkflowRunStatus.RUNNING).items
        ]

    def test_fan_out_after_a_records_run_completed_is_still_processed(self) -> None:
        """``records.ingested`` closes its one-step run before its fan-out lands.

        The records path publishes ``risk.scored`` from inside the
        ``records.ingested`` handler, so every one of them arrives after that
        run is already COMPLETED. They must still be handled.
        """

        store = InMemoryWorkflowRunStore(
            runs=[
                WorkflowRun(
                    workflow_id="workflow-records",
                    knowledge_base_id="kb-1",
                    trigger_event_type="records.ingested",
                    status=WorkflowRunStatus.RUNNING,
                    steps=[WorkflowStepState(step_name="records_ingest")],
                    metadata={"correlation_id": "corr-records"},
                )
            ]
        )
        tracker = WorkflowEventTracker(store)
        records_event = RecordsIngestedEvent(
            correlation_id="corr-records",
            knowledge_base_id="kb-1",
            feed_name="claims",
            record_type="claim_record",
            record_count=3,
        )
        tracker.begin_event(records_event)
        tracker.complete_event(records_event)
        assert store.get_run("workflow-records").status is WorkflowRunStatus.COMPLETED

        began = [
            tracker.begin_event(
                _risk_scored_fan_out_event(
                    correlation_id="corr-records", entity_id=entity_id
                )
            )
            for entity_id in ("provider:1", "provider:2", "provider:3")
        ]

        assert began == [True, True, True], (
            "every risk.scored from the records fan-out was dropped because the "
            f"records run had already completed: {began}"
        )

    def test_a_cancelled_run_still_gates_the_fan_out(self) -> None:
        store = InMemoryWorkflowRunStore(
            runs=[_pipeline_run(status=WorkflowRunStatus.CANCELLED)]
        )
        tracker = WorkflowEventTracker(store)

        assert (
            tracker.begin_event(
                _risk_scored_fan_out_event(
                    correlation_id="corr-fanout", entity_id="provider:1"
                )
            )
            is False
        )
