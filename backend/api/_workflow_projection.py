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

WorkflowStatusValue = Literal[
    "queued", "running", "awaiting_approval", "completed", "failed", "cancelled"
]
WorkflowTypeValue = Literal["ingestion", "graph_build", "analytics", "monitoring"]


def project_workflow_runs(
    runs: list[WorkflowRun],
    *,
    has_more: bool = False,
    next_offset: int | None = None,
) -> WorkflowRunListResponse:
    """Project workflow run models into the frontend collection contract."""

    return WorkflowRunListResponse(
        items=[project_workflow_run(run) for run in runs],
        has_more=has_more,
        next_offset=next_offset,
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
    """Return the number of workflow runs currently active."""

    active_statuses = {WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING}
    return sum(1 for run in runs if run.status in active_statuses)


_STATUS_PROJECTION: dict[WorkflowRunStatus, WorkflowStatusValue] = {
    WorkflowRunStatus.QUEUED: "queued",
    WorkflowRunStatus.RUNNING: "running",
    WorkflowRunStatus.AWAITING_APPROVAL: "awaiting_approval",
    WorkflowRunStatus.COMPLETED: "completed",
    WorkflowRunStatus.FAILED: "failed",
    WorkflowRunStatus.CANCELLED: "cancelled",
}


def _workflow_status(status: WorkflowRunStatus) -> WorkflowStatusValue:
    """Project a run status, exhaustively.

    This was a chain of `if`s ending in `return "failed"`, so any status it did
    not recognise was reported as a failure. When AWAITING_APPROVAL arrived,
    a run waiting for a human's approval was shown to that human as failed —
    they would see a dead workflow and never approve it. An explicit map raises
    on an unmapped status instead of inventing a plausible-looking lie.
    """

    projected = _STATUS_PROJECTION.get(status)
    if projected is None:
        raise ValueError(f"WorkflowRunStatus '{status}' has no API projection.")
    return projected


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
