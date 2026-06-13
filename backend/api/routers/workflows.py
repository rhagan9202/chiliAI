"""Workflow status router exposing pipeline run summaries and cancellation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from agent.exceptions import WorkflowAlreadyTerminalError, WorkflowRunNotFoundError
from agent.models import WorkflowRun
from agent.protocols import AgentServiceProtocol
from agent.service_models import WorkflowRunStatus
from api._workflow_projection import project_workflow_run, project_workflow_runs
from api.contracts import WorkflowRunListResponse, WorkflowRunResponse
from api.dependencies import get_agent_service
from api.middleware.auth import User
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _can_access_workflow(user: User, knowledge_base_id: str) -> bool:
    allowed = getattr(user, "knowledge_base_ids", None)
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


def _list_accessible_workflows(
    agent_service: AgentServiceProtocol,
    *,
    user: User,
    knowledge_base_id: str | None,
    status: WorkflowRunStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[WorkflowRun], bool, int | None]:
    runs: list[WorkflowRun] = []
    scan_offset = offset
    has_more = False
    next_offset: int | None = None

    while len(runs) < limit:
        page = agent_service.list_workflows(
            knowledge_base_id=knowledge_base_id,
            status=status,
            limit=limit,
            offset=scan_offset,
        )
        for run in page.items:
            if _can_access_workflow(user, run.knowledge_base_id):
                runs.append(run)
                if len(runs) == limit:
                    break

        has_more = page.has_more
        next_offset = page.next_offset if page.has_more else None
        if len(runs) == limit or not page.has_more:
            break
        if (
            not page.items
            or page.next_offset is None
            or page.next_offset <= scan_offset
        ):
            has_more = False
            next_offset = None
            break
        scan_offset = page.next_offset

    return runs, has_more, next_offset


@router.get(
    "",
    response_model=WorkflowRunListResponse,
)
async def list_workflows(
    knowledge_base_id: str | None = Query(default=None),
    status: WorkflowRunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=0, le=500),
    offset: int = Query(default=0, ge=0),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
    user: User = Depends(require_role("viewer")),
) -> WorkflowRunListResponse:
    """Return recent workflow runs for the pipeline status UI."""
    if limit == 0:
        page = agent_service.list_workflows(
            knowledge_base_id=knowledge_base_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return project_workflow_runs(
            [],
            has_more=page.has_more,
            next_offset=page.next_offset if page.has_more else None,
        )
    runs, has_more, next_offset = _list_accessible_workflows(
        agent_service,
        user=user,
        knowledge_base_id=knowledge_base_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return project_workflow_runs(
        runs,
        has_more=has_more,
        next_offset=next_offset,
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRunResponse,
)
async def get_workflow(
    workflow_id: str = Path(...),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
    user: User = Depends(require_role("viewer")),
) -> WorkflowRunResponse:
    """Return a single workflow run by id."""
    try:
        run = agent_service.get_workflow_status(workflow_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if not _can_access_workflow(user, run.knowledge_base_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{workflow_id}' was not found.",
        )
    return project_workflow_run(run)


@router.post(
    "/{workflow_id}/cancel",
    response_model=WorkflowRunResponse,
)
async def cancel_workflow(
    workflow_id: str = Path(...),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
    user: User = Depends(require_role("analyst")),
) -> WorkflowRunResponse:
    """Request cancellation of a non-terminal workflow run.

    Cancellation is cooperative: the worker honours it at the next stage / loop
    boundary, so an already-running synchronous stage may still finish.
    """
    try:
        existing_run = agent_service.get_workflow_status(workflow_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if not _can_access_workflow(user, existing_run.knowledge_base_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{workflow_id}' was not found.",
        )
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
