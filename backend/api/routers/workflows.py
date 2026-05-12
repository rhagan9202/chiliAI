"""Workflow status router exposing pipeline run summaries."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent.protocols import AgentServiceProtocol
from api._workflow_projection import project_workflow_runs
from api.contracts import WorkflowRunListResponse
from api.dependencies import get_agent_service
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get(
    "",
    response_model=WorkflowRunListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_workflows(
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
) -> WorkflowRunListResponse:
    """Return recent workflow runs for the pipeline status UI."""
    return project_workflow_runs(agent_service.list_workflows())
