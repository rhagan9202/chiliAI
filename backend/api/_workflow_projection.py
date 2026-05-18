"""Projection helpers for API workflow read models.

The agent module owns workflow state and lifecycle rules. This module only
maps ``agent.models.WorkflowRun`` records into the existing frontend-facing
``api.contracts`` DTOs so routers can remain thin.
"""

from __future__ import annotations

from typing import Literal

from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepStatus
from api.contracts import WorkflowRunListResponse, WorkflowRunResponse

__all__ = [
    "count_running_workflows",
    "project_workflow_run",
    "project_workflow_runs",
]

WorkflowStatusValue = Literal["queued", "running", "completed", "failed", "cancelled"]
WorkflowTypeValue = Literal["ingestion", "graph_build", "analytics", "monitoring"]


def project_workflow_runs(runs: list[WorkflowRun]) -> WorkflowRunListResponse:
    """Project workflow run models into the frontend collection contract."""

    return WorkflowRunListResponse(
        items=[project_workflow_run(run) for run in runs]
    )


def project_workflow_run(run: WorkflowRun) -> WorkflowRunResponse:
    """Project one workflow run model into the frontend summary contract."""

    return WorkflowRunResponse(
        id=run.workflow_id,
        workflow_type=_workflow_type_for_trigger(run.trigger_event_type),
        status=_workflow_status(run.status),
        knowledge_base_id=run.knowledge_base_id,
        started_at=run.created_at,
        updated_at=run.updated_at,
        current_step=_current_step(run),
        last_error=_last_error(run),
    )


def count_running_workflows(runs: list[WorkflowRun]) -> int:
    """Return the number of non-terminal workflow runs currently running."""

    return sum(1 for run in runs if run.status is WorkflowRunStatus.RUNNING)


def _workflow_status(status: WorkflowRunStatus) -> WorkflowStatusValue:
    if status is WorkflowRunStatus.QUEUED:
        return "queued"
    if status is WorkflowRunStatus.RUNNING:
        return "running"
    if status is WorkflowRunStatus.COMPLETED:
        return "completed"
    if status is WorkflowRunStatus.CANCELLED:
        return "cancelled"
    return "failed"


def _current_step(run: WorkflowRun) -> str:
    if run.status is WorkflowRunStatus.COMPLETED:
        return "completed"
    if run.status is WorkflowRunStatus.CANCELLED:
        return "cancelled"
    if run.status is WorkflowRunStatus.FAILED:
        return "failed"
    for step in run.steps:
        if step.status is WorkflowStepStatus.RUNNING:
            return step.step_name
    for step in run.steps:
        if step.status is WorkflowStepStatus.PENDING:
            return step.step_name
    return run.steps[-1].step_name


def _last_error(run: WorkflowRun) -> str | None:
    value = run.metadata.get("last_error")
    return value if isinstance(value, str) and value else None


def _workflow_type_for_trigger(trigger_event_type: str) -> WorkflowTypeValue:
    normalized = trigger_event_type.lower()
    if normalized.startswith("graph."):
        return "graph_build"
    if normalized.startswith(
        ("analytics.", "risk.", "timeseries.", "gnn.", "explainability.")
    ):
        return "analytics"
    if normalized.startswith(("monitoring.", "alerts.")):
        return "monitoring"
    return "ingestion"
