"""Tests for the agent service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.exceptions import (
    AgentStateStoreError,
    IdempotencyKeyConflictError,
    WorkflowAlreadyTerminalError,
    WorkflowRunNotFoundError,
)
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
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


def test_agent_service_records_failed_run_when_publish_fails() -> None:
    run_store = InMemoryWorkflowRunStore()
    service = create_agent_service(run_store, event_bus=_FailingEventBus())

    with pytest.raises(AgentStateStoreError):
        service.start_workflow(
            WorkflowSubmissionRequest(
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                requested_steps=["parse"],
            )
        )

    [stored_run] = run_store.list_runs()
    assert stored_run.status is WorkflowRunStatus.FAILED
    assert stored_run.metadata["publish_error"] == "publish unavailable"


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

    assert [run.workflow_id for run in listed] == ["newer", "older"]


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

    assert [run.workflow_id for run in listed] == ["target"]


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
    assert [run.workflow_id for run in page] == ["w-2", "w-1"]


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
) -> WorkflowSubmissionRequest:
    return WorkflowSubmissionRequest(
        knowledge_base_id=knowledge_base_id,
        trigger_event_type=trigger_event_type,
        requested_steps=requested_steps or ["parse", "chunk"],
        metadata=metadata or {"priority": "high"},
        idempotency_key=idempotency_key,
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
    assert len(run_store.list_runs()) == 1
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
    assert len(run_store.list_runs()) == 2
    started_events = [
        e for e in event_bus.published_events if isinstance(e, AgentWorkflowStartedEvent)
    ]
    assert len(started_events) == 2
