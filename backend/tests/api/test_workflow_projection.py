"""Tests for workflow projection helpers used by API read models."""

from __future__ import annotations

from datetime import datetime, timezone

from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState, WorkflowStepStatus
from api._workflow_projection import (
    count_running_workflows,
    project_workflow_run,
    project_workflow_runs,
)


def _run(
    *,
    workflow_id: str = "workflow-1",
    trigger_event_type: str = "documents.uploaded",
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING,
    steps: list[WorkflowStepState] | None = None,
) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=workflow_id,
        knowledge_base_id="kb-1",
        trigger_event_type=trigger_event_type,
        status=status,
        steps=steps or [WorkflowStepState(step_name="parse")],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def test_project_workflow_run_maps_statuses() -> None:
    expected = {
        WorkflowRunStatus.QUEUED: "queued",
        WorkflowRunStatus.RUNNING: "running",
        WorkflowRunStatus.COMPLETED: "completed",
        WorkflowRunStatus.FAILED: "failed",
        WorkflowRunStatus.CANCELLED: "cancelled",
    }

    for status, projected_status in expected.items():
        response = project_workflow_run(_run(status=status))
        assert response.status == projected_status


def test_project_workflow_run_maps_trigger_to_workflow_type() -> None:
    expected = {
        "documents.uploaded": "ingestion",
        "graph.updated": "graph_build",
        "analytics.started": "analytics",
        "risk.scored": "analytics",
        "timeseries.analyzed": "analytics",
        "gnn.analyzed": "analytics",
        "explainability.generated": "analytics",
        "monitoring.evaluated": "monitoring",
        "alerts.created": "monitoring",
        "unknown.event": "ingestion",
    }

    for trigger, workflow_type in expected.items():
        response = project_workflow_run(_run(trigger_event_type=trigger))
        assert response.workflow_type == workflow_type


def test_current_step_prefers_running_then_pending() -> None:
    running = _run(
        steps=[
            WorkflowStepState(step_name="parse", status=WorkflowStepStatus.COMPLETED),
            WorkflowStepState(step_name="chunk", status=WorkflowStepStatus.RUNNING),
            WorkflowStepState(step_name="extract", status=WorkflowStepStatus.PENDING),
        ]
    )
    pending = _run(
        steps=[
            WorkflowStepState(step_name="parse", status=WorkflowStepStatus.COMPLETED),
            WorkflowStepState(step_name="extract", status=WorkflowStepStatus.PENDING),
        ]
    )

    assert project_workflow_run(running).current_step == "chunk"
    assert project_workflow_run(pending).current_step == "extract"


def test_current_step_uses_terminal_labels() -> None:
    completed_steps = [
        WorkflowStepState(step_name="parse", status=WorkflowStepStatus.COMPLETED)
    ]
    failed_steps = [
        WorkflowStepState(step_name="parse", status=WorkflowStepStatus.FAILED)
    ]

    assert project_workflow_run(
        _run(status=WorkflowRunStatus.COMPLETED, steps=completed_steps)
    ).current_step == "completed"
    assert project_workflow_run(
        _run(status=WorkflowRunStatus.CANCELLED, steps=completed_steps)
    ).current_step == "cancelled"
    assert project_workflow_run(
        _run(status=WorkflowRunStatus.FAILED, steps=failed_steps)
    ).current_step == "failed"


def test_project_workflow_runs_wraps_items() -> None:
    response = project_workflow_runs([
        _run(workflow_id="workflow-1"),
        _run(workflow_id="workflow-2", status=WorkflowRunStatus.QUEUED),
    ])

    assert [item.id for item in response.items] == ["workflow-1", "workflow-2"]


def test_count_running_workflows_counts_only_running() -> None:
    runs = [
        _run(workflow_id="queued", status=WorkflowRunStatus.QUEUED),
        _run(workflow_id="running", status=WorkflowRunStatus.RUNNING),
        _run(workflow_id="failed", status=WorkflowRunStatus.FAILED),
    ]

    assert count_running_workflows(runs) == 1
