"""Tests for the agent service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.exceptions import (
    AgentConfigurationError,
    IdempotencyKeyConflictError,
    WorkflowAlreadyTerminalError,
    WorkflowRunNotFoundError,
)
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
)
from agent.service import AgentService, create_agent_service
from agent.service_models import WorkflowSubmissionRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import AgentWorkflowStartedEvent, AnyEvent


class _FailingEventBus(InMemoryEventBus):
    def publish(self, event: AnyEvent) -> str | None:
        del event
        raise RuntimeError("publish unavailable")


class _SnapshottingWorkflowRunStore(InMemoryWorkflowRunStore):
    """Workflow store that captures persisted snapshots after writes."""

    def __init__(self) -> None:
        super().__init__()
        self.saved_runs: list[WorkflowRun] = []
        self.updated_runs: list[WorkflowRun] = []

    def save_run(self, run: WorkflowRun) -> WorkflowRun:
        saved = super().save_run(run)
        self.saved_runs.append(saved.model_copy(deep=True))
        return saved

    def update_run(
        self,
        workflow_id: str,
        update: WorkflowRunUpdate,
    ) -> WorkflowRun:
        updated = super().update_run(workflow_id, update)
        self.updated_runs.append(updated.model_copy(deep=True))
        return updated


def _service(runs: list[WorkflowRun] | None = None) -> tuple[AgentService, InMemoryWorkflowRunStore, InMemoryEventBus]:
    run_store = InMemoryWorkflowRunStore(runs=runs)
    event_bus = InMemoryEventBus()
    service = create_agent_service(run_store, event_bus=event_bus)
    return service, run_store, event_bus


def _run(
    *,
    workflow_id: str = "workflow-1",
    knowledge_base_id: str = "kb-1",
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING,
    created_at: datetime | None = None,
) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=workflow_id,
        knowledge_base_id=knowledge_base_id,
        trigger_event_type="documents.uploaded",
        status=status,
        steps=[WorkflowStepState(step_name="parse")],
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_agent_service_starts_workflow_persists_run_and_publishes_event() -> None:
    service, run_store, event_bus = _service()

    response = service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=["parse", "chunk", "extract"],
            metadata={"priority": "high"},
        )
    )

    stored_run = run_store.get_run(response.workflow_id)

    assert response.status.value == "running"
    assert response.step_count == 3
    assert stored_run.workflow_id == response.workflow_id
    assert stored_run.status is WorkflowRunStatus.RUNNING
    assert stored_run.metadata["priority"] == "high"
    assert "correlation_id" in stored_run.metadata
    assert isinstance(event_bus.published_events[-1], AgentWorkflowStartedEvent)
    started_event = event_bus.published_events[-1]
    assert isinstance(started_event, AgentWorkflowStartedEvent)
    assert started_event.correlation_id == stored_run.metadata["correlation_id"]


def test_agent_service_persists_queued_state_before_running() -> None:
    run_store = _SnapshottingWorkflowRunStore()
    service = create_agent_service(run_store, event_bus=InMemoryEventBus())

    response = service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=["parse"],
        )
    )

    assert run_store.saved_runs[0].status is WorkflowRunStatus.QUEUED
    assert run_store.updated_runs[-1].status is WorkflowRunStatus.RUNNING
    assert run_store.get_run(response.workflow_id).status is WorkflowRunStatus.RUNNING


def test_agent_service_keeps_run_running_when_started_publish_fails() -> None:
    run_store = InMemoryWorkflowRunStore()
    service = create_agent_service(run_store, event_bus=_FailingEventBus())

    response = service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=["parse"],
        )
    )

    [stored_run] = run_store.list_runs().items
    assert response.status is WorkflowRunStatus.RUNNING
    assert stored_run.status is WorkflowRunStatus.RUNNING
    assert stored_run.metadata["workflow_started_publish_error"] == "publish_failed"
    assert "publish unavailable" not in stored_run.metadata.values()


def test_agent_service_rejects_unknown_requested_step_name() -> None:
    service, run_store, event_bus = _service()

    with pytest.raises(AgentConfigurationError, match="Unknown workflow step"):
        service.start_workflow(
            WorkflowSubmissionRequest(
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                requested_steps=["parse", "invented_step"],
            )
        )

    assert run_store.list_runs().items == []
    assert event_bus.published_events == []


def test_get_workflow_status_returns_persisted_run() -> None:
    seeded = _run()
    service, _, _ = _service(runs=[seeded])

    assert service.get_workflow_status("workflow-1") == seeded


def test_get_workflow_status_raises_when_workflow_id_is_unknown() -> None:
    service, _, _ = _service()

    with pytest.raises(WorkflowRunNotFoundError):
        service.get_workflow_status("missing")


def test_list_workflows_returns_runs_newest_first() -> None:
    older = _run(workflow_id="older", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _run(workflow_id="newer", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    service, _, _ = _service(runs=[older, newer])

    listed = service.list_workflows()

    assert [run.workflow_id for run in listed.items] == ["newer", "older"]
    assert listed.has_more is False
    assert listed.next_offset is None


def test_list_workflows_filters_by_knowledge_base_and_status() -> None:
    target = _run(
        workflow_id="target",
        knowledge_base_id="kb-1",
        status=WorkflowRunStatus.COMPLETED,
    )
    other = _run(
        workflow_id="other",
        knowledge_base_id="kb-2",
        status=WorkflowRunStatus.COMPLETED,
    )
    service, _, _ = _service(runs=[target, other])

    listed = service.list_workflows(
        knowledge_base_id="kb-1", status=WorkflowRunStatus.COMPLETED
    )

    assert [run.workflow_id for run in listed.items] == ["target"]


def test_list_workflows_honours_limit_and_offset() -> None:
    runs = [
        _run(
            workflow_id=f"w-{i}",
            created_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
        )
        for i in range(4)
    ]
    service, _, _ = _service(runs=runs)

    page = service.list_workflows(limit=2, offset=1)

    # newest-first: w-3, w-2, w-1, w-0 → offset 1 limit 2 → w-2, w-1
    assert [run.workflow_id for run in page.items] == ["w-2", "w-1"]
    assert page.has_more is True
    assert page.next_offset == 3


def test_cancel_workflow_transitions_running_to_cancelled() -> None:
    seeded = _run(status=WorkflowRunStatus.RUNNING)
    service, run_store, _ = _service(runs=[seeded])

    cancelled = service.cancel_workflow("workflow-1")

    assert cancelled.status is WorkflowRunStatus.CANCELLED
    assert run_store.get_run("workflow-1").status is WorkflowRunStatus.CANCELLED


def test_cancel_workflow_is_idempotent_when_already_cancelled() -> None:
    seeded = _run(status=WorkflowRunStatus.CANCELLED)
    service, _, _ = _service(runs=[seeded])

    result = service.cancel_workflow("workflow-1")

    assert result.status is WorkflowRunStatus.CANCELLED


def test_cancelled_workflow_is_terminal() -> None:
    seeded = _run(status=WorkflowRunStatus.CANCELLED)
    service, _, _ = _service(runs=[seeded])

    result = service.cancel_workflow("workflow-1")

    assert result.status is WorkflowRunStatus.CANCELLED


def test_cancel_workflow_raises_when_run_is_completed() -> None:
    seeded = _run(status=WorkflowRunStatus.COMPLETED)
    service, _, _ = _service(runs=[seeded])

    with pytest.raises(WorkflowAlreadyTerminalError) as exc_info:
        service.cancel_workflow("workflow-1")

    assert exc_info.value.status is WorkflowRunStatus.COMPLETED
    assert exc_info.value.workflow_id == "workflow-1"


def test_cancel_workflow_raises_when_run_is_failed() -> None:
    seeded = _run(status=WorkflowRunStatus.FAILED)
    service, _, _ = _service(runs=[seeded])

    with pytest.raises(WorkflowAlreadyTerminalError):
        service.cancel_workflow("workflow-1")


def test_cancel_workflow_raises_when_workflow_id_is_unknown() -> None:
    service, _, _ = _service()

    with pytest.raises(WorkflowRunNotFoundError):
        service.cancel_workflow("missing")


def _submit(
    knowledge_base_id: str = "kb-1",
    trigger_event_type: str = "documents.uploaded",
    requested_steps: list[str] | None = None,
    metadata: dict[str, str | int | float | bool] | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> WorkflowSubmissionRequest:
    return WorkflowSubmissionRequest(
        knowledge_base_id=knowledge_base_id,
        trigger_event_type=trigger_event_type,
        requested_steps=requested_steps or ["parse", "chunk"],
        metadata=metadata or {"priority": "high"},
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


def test_start_workflow_persists_idempotency_key_on_run() -> None:
    service, run_store, _ = _service()

    response = service.start_workflow(_submit(idempotency_key="abc-123"))

    assert run_store.get_run(response.workflow_id).idempotency_key == "abc-123"


def test_start_workflow_with_repeated_key_returns_original_response() -> None:
    service, run_store, event_bus = _service()

    first = service.start_workflow(_submit(idempotency_key="abc-123"))
    second = service.start_workflow(_submit(idempotency_key="abc-123"))

    assert second.workflow_id == first.workflow_id
    assert len(run_store.list_runs().items) == 1
    # Only one StartedEvent should have been published — retries must not re-fire it.
    started_events = [
        e for e in event_bus.published_events if isinstance(e, AgentWorkflowStartedEvent)
    ]
    assert len(started_events) == 1


def test_start_workflow_conflict_on_trigger_event_type() -> None:
    service, _, _ = _service()
    service.start_workflow(
        _submit(trigger_event_type="documents.uploaded", idempotency_key="abc-123")
    )

    with pytest.raises(IdempotencyKeyConflictError) as exc_info:
        service.start_workflow(
            _submit(trigger_event_type="documents.deleted", idempotency_key="abc-123")
        )

    assert exc_info.value.conflicting_field == "trigger_event_type"
    assert exc_info.value.idempotency_key == "abc-123"


def test_start_workflow_conflict_on_requested_steps() -> None:
    service, _, _ = _service()
    service.start_workflow(
        _submit(requested_steps=["parse", "chunk"], idempotency_key="abc-123")
    )

    with pytest.raises(IdempotencyKeyConflictError) as exc_info:
        service.start_workflow(
            _submit(requested_steps=["parse", "embed"], idempotency_key="abc-123")
        )

    assert exc_info.value.conflicting_field == "requested_steps"


def test_start_workflow_conflict_on_metadata() -> None:
    service, _, _ = _service()
    service.start_workflow(
        _submit(metadata={"priority": "high"}, idempotency_key="abc-123")
    )

    with pytest.raises(IdempotencyKeyConflictError) as exc_info:
        service.start_workflow(
            _submit(metadata={"priority": "low"}, idempotency_key="abc-123")
        )

    assert exc_info.value.conflicting_field == "metadata"


def test_start_workflow_same_key_under_different_kb_creates_independent_runs() -> None:
    service, run_store, event_bus = _service()

    first = service.start_workflow(
        _submit(knowledge_base_id="kb-1", idempotency_key="shared")
    )
    second = service.start_workflow(
        _submit(knowledge_base_id="kb-2", idempotency_key="shared")
    )

    assert first.workflow_id != second.workflow_id
    assert len(run_store.list_runs().items) == 2
    started_events = [
        e for e in event_bus.published_events if isinstance(e, AgentWorkflowStartedEvent)
    ]
    assert len(started_events) == 2


def test_start_workflow_honors_supplied_correlation_id() -> None:
    service, run_store, _ = _service()

    response = service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=["parse"],
            correlation_id="corr-supplied",
        )
    )

    stored = run_store.get_run(response.workflow_id)
    assert stored.metadata["correlation_id"] == "corr-supplied"
    found = run_store.find_by_correlation_id("corr-supplied")
    assert found is not None
    assert found.workflow_id == response.workflow_id


def test_start_workflow_adopts_existing_run_for_same_correlation() -> None:
    # Simulates the worker's tracker winning the race and fallback-creating a
    # run before the API calls start_workflow: the service must adopt it, not
    # create a duplicate or re-publish a started event.
    existing = WorkflowRun(
        workflow_id="fallback-1",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        status=WorkflowRunStatus.RUNNING,
        steps=[WorkflowStepState(step_name="parse"), WorkflowStepState(step_name="chunk")],
        metadata={"correlation_id": "corr-pre", "source_event_type": "documents.uploaded"},
    )
    service, run_store, event_bus = _service(runs=[existing])

    response = service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id="kb-1",
            trigger_event_type="documents.uploaded",
            requested_steps=["parse", "chunk"],
            correlation_id="corr-pre",
        )
    )

    assert response.workflow_id == "fallback-1"
    assert len(run_store.list_runs().items) == 1
    assert [
        e for e in event_bus.published_events if isinstance(e, AgentWorkflowStartedEvent)
    ] == []


def test_start_workflow_rejects_correlation_reuse_for_different_knowledge_base() -> None:
    service, _, _ = _service(
        runs=[
            WorkflowRun(
                workflow_id="fallback-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(step_name="parse"),
                    WorkflowStepState(step_name="chunk"),
                ],
                metadata={"correlation_id": "corr-pre"},
            )
        ]
    )

    with pytest.raises(AgentConfigurationError, match="knowledge_base_id"):
        service.start_workflow(_submit(knowledge_base_id="kb-2", correlation_id="corr-pre"))


def test_start_workflow_rejects_correlation_reuse_for_different_trigger_event_type() -> None:
    service, _, _ = _service(
        runs=[
            WorkflowRun(
                workflow_id="fallback-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(step_name="parse"),
                    WorkflowStepState(step_name="chunk"),
                ],
                metadata={"correlation_id": "corr-pre"},
            )
        ]
    )

    with pytest.raises(AgentConfigurationError, match="trigger_event_type"):
        service.start_workflow(
            _submit(trigger_event_type="documents.deleted", correlation_id="corr-pre")
        )


def test_start_workflow_rejects_correlation_reuse_for_different_idempotency_key() -> None:
    service, _, _ = _service(
        runs=[
            WorkflowRun(
                workflow_id="fallback-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(step_name="parse"),
                    WorkflowStepState(step_name="chunk"),
                ],
                metadata={"correlation_id": "corr-pre"},
                idempotency_key="original-key",
            )
        ]
    )

    with pytest.raises(AgentConfigurationError, match="idempotency_key"):
        service.start_workflow(
            _submit(idempotency_key="replacement-key", correlation_id="corr-pre")
        )


def test_start_workflow_rejects_correlation_reuse_for_different_requested_steps() -> None:
    service, _, _ = _service(
        runs=[
            WorkflowRun(
                workflow_id="fallback-1",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(step_name="parse"),
                    WorkflowStepState(step_name="chunk"),
                ],
                metadata={"correlation_id": "corr-pre"},
            )
        ]
    )

    with pytest.raises(AgentConfigurationError, match="requested_steps"):
        service.start_workflow(
            _submit(requested_steps=["chunk", "parse"], correlation_id="corr-pre")
        )


def test_start_workflow_checks_idempotency_key_before_correlation_conflict() -> None:
    service, _, _ = _service()
    first = service.start_workflow(
        _submit(idempotency_key="abc-123", correlation_id="corr-original")
    )

    second = service.start_workflow(
        _submit(idempotency_key="abc-123", correlation_id="corr-different")
    )

    assert second.workflow_id == first.workflow_id


def test_idempotency_match_ignores_tracker_written_metadata() -> None:
    service, run_store, _ = _service()
    first = service.start_workflow(
        _submit(metadata={"priority": "high"}, idempotency_key="abc-123")
    )

    # Tracker annotates the run with system metadata as events flow.
    run_store.update_run(
        first.workflow_id,
        WorkflowRunUpdate(
            metadata={
                "priority": "high",
                "correlation_id": "corr-x",
                "last_event_type": "documents.chunked",
            }
        ),
    )

    # Re-submitting the same logical request must return the original, not conflict.
    second = service.start_workflow(
        _submit(metadata={"priority": "high"}, idempotency_key="abc-123")
    )
    assert second.workflow_id == first.workflow_id
