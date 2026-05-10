"""Workflow status router exposing pipeline run summaries."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import WorkflowRunListResponse
from api.dependencies import get_workflow_runs_payload
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get(
    "",
    response_model=WorkflowRunListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_workflows(
    workflows: WorkflowRunListResponse = Depends(get_workflow_runs_payload),
) -> WorkflowRunListResponse:
    """Return recent workflow runs for the pipeline status UI."""
    return workflows