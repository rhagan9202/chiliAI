"""Workflow status router exposing pipeline run summaries and cancellation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from agent.exceptions import WorkflowAlreadyTerminalError, WorkflowRunNotFoundError
from agent.protocols import AgentServiceProtocol
from agent.service_models import WorkflowRunStatus
from api._workflow_projection import project_workflow_run, project_workflow_runs
from api.contracts import WorkflowRunListResponse, WorkflowRunResponse
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
    knowledge_base_id: str | None = Query(default=None),
    status: WorkflowRunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
) -> WorkflowRunListResponse:
    """Return recent workflow runs for the pipeline status UI."""
    return project_workflow_runs(
        agent_service.list_workflows(
            knowledge_base_id=knowledge_base_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRunResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_workflow(
    workflow_id: str = Path(...),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
) -> WorkflowRunResponse:
    """Return a single workflow run by id."""
    try:
        run = agent_service.get_workflow_status(workflow_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return project_workflow_run(run)


@router.post(
    "/{workflow_id}/cancel",
    response_model=WorkflowRunResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def cancel_workflow(
    workflow_id: str = Path(...),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
) -> WorkflowRunResponse:
    """Request cancellation of a non-terminal workflow run.

    Cancellation is cooperative: the worker honours it at the next stage / loop
    boundary, so an already-running synchronous stage may still finish.
    """
    try:
        run = agent_service.cancel_workflow(workflow_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except WorkflowAlreadyTerminalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return project_workflow_run(run)
