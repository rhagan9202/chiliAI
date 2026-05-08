"""Tests for the in-memory agent adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.exceptions import WorkflowRunNotFoundError
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
    WorkflowStepStatus,
)


def _run(
    *,
    workflow_id: str = "workflow-1",
    knowledge_base_id: str = "kb-1",
    trigger_event_type: str = "documents.uploaded",
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING,
    steps: list[WorkflowStepState] | None = None,
    created_at: datetime | None = None,
) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=workflow_id,
        knowledge_base_id=knowledge_base_id,
        trigger_event_type=trigger_event_type,
        status=status,
        steps=steps or [WorkflowStepState(step_name="parse")],
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_in_memory_workflow_run_store_returns_seeded_run() -> None:
    run = _run()
    store = InMemoryWorkflowRunStore(runs=[run])

    loaded = store.get_run("workflow-1")

    assert loaded == run


def test_get_run_raises_when_workflow_id_is_unknown() -> None:
    store = InMemoryWorkflowRunStore()

    with pytest.raises(WorkflowRunNotFoundError) as exc_info:
        store.get_run("missing")

    assert exc_info.value.workflow_id == "missing"


def test_list_runs_returns_newest_first() -> None:
    older = _run(
        workflow_id="older",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = _run(
        workflow_id="newer",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    store = InMemoryWorkflowRunStore(runs=[older, newer])

    listed = store.list_runs()

    assert [run.workflow_id for run in listed] == ["newer", "older"]


def test_list_runs_filters_by_knowledge_base_id() -> None:
    kb1 = _run(workflow_id="a", knowledge_base_id="kb-1")
    kb2 = _run(workflow_id="b", knowledge_base_id="kb-2")
    store = InMemoryWorkflowRunStore(runs=[kb1, kb2])

    listed = store.list_runs(knowledge_base_id="kb-2")

    assert [run.workflow_id for run in listed] == ["b"]


def test_list_runs_filters_by_status() -> None:
    running = _run(workflow_id="a", status=WorkflowRunStatus.RUNNING)
    completed = _run(workflow_id="b", status=WorkflowRunStatus.COMPLETED)
    store = InMemoryWorkflowRunStore(runs=[running, completed])

    listed = store.list_runs(status=WorkflowRunStatus.COMPLETED)

    assert [run.workflow_id for run in listed] == ["b"]


def test_list_runs_combines_filters() -> None:
    target = _run(
        workflow_id="target",
        knowledge_base_id="kb-1",
        status=WorkflowRunStatus.COMPLETED,
    )
    other_status = _run(
        workflow_id="wrong-status",
        knowledge_base_id="kb-1",
        status=WorkflowRunStatus.RUNNING,
    )
    other_kb = _run(
        workflow_id="wrong-kb",
        knowledge_base_id="kb-2",
        status=WorkflowRunStatus.COMPLETED,
    )
    store = InMemoryWorkflowRunStore(runs=[target, other_status, other_kb])

    listed = store.list_runs(
        knowledge_base_id="kb-1", status=WorkflowRunStatus.COMPLETED
    )

    assert [run.workflow_id for run in listed] == ["target"]


def test_list_runs_honours_limit_and_offset() -> None:
    runs = [
        _run(
            workflow_id=f"w-{i}",
            created_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
        )
        for i in range(5)
    ]
    store = InMemoryWorkflowRunStore(runs=runs)

    page = store.list_runs(limit=2, offset=1)

    # Newest-first: w-4, w-3, w-2, w-1, w-0 → offset 1, limit 2 → w-3, w-2
    assert [run.workflow_id for run in page] == ["w-3", "w-2"]


def test_list_runs_with_zero_limit_returns_empty() -> None:
    store = InMemoryWorkflowRunStore(runs=[_run()])

    assert store.list_runs(limit=0) == []


def test_list_runs_rejects_negative_limit() -> None:
    store = InMemoryWorkflowRunStore()

    with pytest.raises(ValueError):
        store.list_runs(limit=-1)


def test_list_runs_rejects_negative_offset() -> None:
    store = InMemoryWorkflowRunStore()

    with pytest.raises(ValueError):
        store.list_runs(offset=-1)


def test_update_run_patches_status() -> None:
    store = InMemoryWorkflowRunStore(runs=[_run()])

    updated = store.update_run(
        "workflow-1", WorkflowRunUpdate(status=WorkflowRunStatus.COMPLETED)
    )

    assert updated.status == WorkflowRunStatus.COMPLETED
    assert store.get_run("workflow-1").status == WorkflowRunStatus.COMPLETED


def test_update_run_replaces_steps() -> None:
    store = InMemoryWorkflowRunStore(runs=[_run()])
    new_steps = [
        WorkflowStepState(step_name="parse", status=WorkflowStepStatus.COMPLETED),
        WorkflowStepState(step_name="embed", status=WorkflowStepStatus.RUNNING),
    ]

    updated = store.update_run("workflow-1", WorkflowRunUpdate(steps=new_steps))

    assert [step.step_name for step in updated.steps] == ["parse", "embed"]
    assert updated.steps[0].status == WorkflowStepStatus.COMPLETED


def test_update_run_replaces_metadata() -> None:
    seeded = _run()
    seeded.metadata["origin"] = "ingest"
    store = InMemoryWorkflowRunStore(runs=[seeded])

    updated = store.update_run(
        "workflow-1", WorkflowRunUpdate(metadata={"origin": "manual", "retry": 1})
    )

    assert updated.metadata == {"origin": "manual", "retry": 1}


def test_update_run_no_op_patch_returns_existing_run() -> None:
    seeded = _run()
    store = InMemoryWorkflowRunStore(runs=[seeded])

    updated = store.update_run("workflow-1", WorkflowRunUpdate())

    assert updated == seeded


def test_update_run_raises_when_workflow_id_is_unknown() -> None:
    store = InMemoryWorkflowRunStore()

    with pytest.raises(WorkflowRunNotFoundError):
        store.update_run("missing", WorkflowRunUpdate(status=WorkflowRunStatus.FAILED))


def test_update_run_rejects_invariant_violations() -> None:
    store = InMemoryWorkflowRunStore(runs=[_run()])

    with pytest.raises(ValidationError):
        store.update_run("workflow-1", WorkflowRunUpdate(steps=[]))

    duplicate = [
        WorkflowStepState(step_name="parse"),
        WorkflowStepState(step_name="parse"),
    ]
    with pytest.raises(ValidationError):
        store.update_run("workflow-1", WorkflowRunUpdate(steps=duplicate))


def test_delete_run_removes_workflow_run() -> None:
    store = InMemoryWorkflowRunStore(runs=[_run()])

    store.delete_run("workflow-1")

    with pytest.raises(WorkflowRunNotFoundError):
        store.get_run("workflow-1")


def test_delete_run_is_idempotent_for_missing_id() -> None:
    store = InMemoryWorkflowRunStore()

    store.delete_run("missing")  # should not raise


def test_delete_run_repeat_call_is_silent_noop() -> None:
    store = InMemoryWorkflowRunStore(runs=[_run()])

    store.delete_run("workflow-1")
    store.delete_run("workflow-1")  # second call is silent


def test_find_by_idempotency_key_returns_persisted_run() -> None:
    run = WorkflowRun(
        workflow_id="workflow-1",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        steps=[WorkflowStepState(step_name="parse")],
        idempotency_key="abc-123",
    )
    store = InMemoryWorkflowRunStore(runs=[run])

    found = store.find_by_idempotency_key(
        knowledge_base_id="kb-1", idempotency_key="abc-123"
    )

    assert found == run


def test_find_by_idempotency_key_returns_none_for_unknown_key() -> None:
    store = InMemoryWorkflowRunStore(runs=[_run()])

    assert (
        store.find_by_idempotency_key(knowledge_base_id="kb-1", idempotency_key="missing")
        is None
    )


def test_find_by_idempotency_key_is_scoped_per_knowledge_base() -> None:
    run = WorkflowRun(
        workflow_id="workflow-1",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        steps=[WorkflowStepState(step_name="parse")],
        idempotency_key="shared-key",
    )
    store = InMemoryWorkflowRunStore(runs=[run])

    # Same key under different kb is invisible.
    assert (
        store.find_by_idempotency_key(
            knowledge_base_id="kb-2", idempotency_key="shared-key"
        )
        is None
    )


def test_delete_run_clears_idempotency_index() -> None:
    run = WorkflowRun(
        workflow_id="workflow-1",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        steps=[WorkflowStepState(step_name="parse")],
        idempotency_key="abc-123",
    )
    store = InMemoryWorkflowRunStore(runs=[run])

    store.delete_run("workflow-1")

    assert (
        store.find_by_idempotency_key(
            knowledge_base_id="kb-1", idempotency_key="abc-123"
        )
        is None
    )


def test_save_run_overwrite_drops_previous_idempotency_mapping() -> None:
    original = WorkflowRun(
        workflow_id="workflow-1",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        steps=[WorkflowStepState(step_name="parse")],
        idempotency_key="old-key",
    )
    store = InMemoryWorkflowRunStore(runs=[original])

    replacement = WorkflowRun(
        workflow_id="workflow-1",
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        steps=[WorkflowStepState(step_name="parse")],
        idempotency_key="new-key",
    )
    store.save_run(replacement)

    assert (
        store.find_by_idempotency_key(
            knowledge_base_id="kb-1", idempotency_key="old-key"
        )
        is None
    )
    assert (
        store.find_by_idempotency_key(
            knowledge_base_id="kb-1", idempotency_key="new-key"
        )
        == replacement
    )
