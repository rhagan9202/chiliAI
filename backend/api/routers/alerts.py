"""Alerts API router — list, detail, and acknowledge alert projections."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from api._alert_store import (
    AlertProjectionRepository,
    acknowledge_alert_projection,
    project_alert_detail,
    project_alert_feed,
)
from api.contracts import AlertDetailResponse, AlertListResponse, ApiEnvelope
from api.dependencies import get_alert_repository
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=AlertListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_alerts(
    repository: AlertProjectionRepository = Depends(get_alert_repository),
) -> AlertListResponse:
    """Return the alert feed in the api.contracts shape (items + page)."""
    return project_alert_feed(repository)


@router.get(
    "/{alert_id}",
    response_model=AlertDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_alert(
    alert_id: str = Path(..., description="Alert identifier."),
    repository: AlertProjectionRepository = Depends(get_alert_repository),
) -> AlertDetailResponse:
    """Return one alert detail with related entities and policy citations."""
    record = repository.get(alert_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' was not found.",
        )
    return project_alert_detail(record)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=ApiEnvelope,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("analyst"))],
)
async def acknowledge_alert(
    alert_id: str = Path(..., description="Alert identifier."),
    repository: AlertProjectionRepository = Depends(get_alert_repository),
) -> ApiEnvelope:
    """Acknowledge an alert; returns an ApiEnvelope status receipt."""
    updated = acknowledge_alert_projection(repository, alert_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' was not found.",
        )
    return ApiEnvelope(
        status="accepted",
        message=f"Alert '{updated.alert.id}' is now {updated.alert.status}.",
    )
