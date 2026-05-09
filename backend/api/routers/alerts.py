"""Alert feed router exposing frontend-facing alert read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import AlertDetailResponse, AlertListResponse, ApiEnvelope
from api.dependencies import get_alert_detail_payload, get_alert_list_payload, get_alert_mutation_payload

__all__ = ["router"]

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    alerts: AlertListResponse = Depends(get_alert_list_payload),
) -> AlertListResponse:
    """Return the alert feed read model."""
    return alerts


@router.get("/{alert_id}", response_model=AlertDetailResponse)
async def get_alert(
    alert: AlertDetailResponse = Depends(get_alert_detail_payload),
) -> AlertDetailResponse:
    """Return one alert detail read model."""
    return alert


@router.post("/{alert_id}/acknowledge", response_model=ApiEnvelope)
async def acknowledge_alert(
    result: ApiEnvelope = Depends(get_alert_mutation_payload),
) -> ApiEnvelope:
    """Queue an alert acknowledgement action."""
    return result