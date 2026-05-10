"""Alerts API router — list, detail, and acknowledge over the api.contracts shape.

Wires through ApiState (see ``api.dependencies``) so the router shares the
seeded alert/evidence/case data the rest of the Phase 5 read models use. The
``monitoring.service`` AlertsService remains as the per-domain alert lifecycle
service for production wiring; it is not currently wired here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from api.contracts import AlertDetailResponse, AlertListResponse, ApiEnvelope
from api.dependencies import (
    get_alert_detail_payload,
    get_alert_list_payload,
    get_alert_mutation_payload,
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
    payload: AlertListResponse = Depends(get_alert_list_payload),
) -> AlertListResponse:
    """Return the alert feed in the api.contracts shape (items + page)."""
    return payload


@router.get(
    "/{alert_id}",
    response_model=AlertDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_alert(
    payload: AlertDetailResponse = Depends(get_alert_detail_payload),
) -> AlertDetailResponse:
    """Return one alert detail with related entities and policy citations."""
    return payload


@router.post(
    "/{alert_id}/acknowledge",
    response_model=ApiEnvelope,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("analyst"))],
)
async def acknowledge_alert(
    payload: ApiEnvelope = Depends(get_alert_mutation_payload),
) -> ApiEnvelope:
    """Acknowledge an alert; returns an ApiEnvelope status receipt."""
    return payload
