"""Alerts API router — list, detail, and acknowledge from the durable store.

Serves every route from the durable ``alert_history`` table via
``AlertFeedStoreProtocol`` (alerts.36); response shaping lives in
``api.dependencies`` alongside the rest of the payload-builder factories.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from api.contracts import AlertDetailResponse, AlertListResponse, ApiEnvelope
from api.dependencies import (
    get_alert_acknowledge_payload,
    get_alert_detail_payload,
    get_alert_list_payload,
)
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=AlertListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_alerts(
    alerts: AlertListResponse = Depends(get_alert_list_payload),
) -> AlertListResponse:
    """Return the alert feed in the api.contracts shape (items + page)."""
    return alerts


@router.get(
    "/{alert_id}",
    response_model=AlertDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_alert(
    alert: AlertDetailResponse = Depends(get_alert_detail_payload),
) -> AlertDetailResponse:
    """Return one alert detail with related entities and policy citations."""
    return alert


@router.post(
    "/{alert_id}/acknowledge",
    response_model=ApiEnvelope,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("analyst"))],
)
async def acknowledge_alert(
    receipt: ApiEnvelope = Depends(get_alert_acknowledge_payload),
) -> ApiEnvelope:
    """Acknowledge an alert; returns an ApiEnvelope status receipt."""
    return receipt
