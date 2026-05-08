"""Alerts API router — list, acknowledge, and resolve alerts."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.middleware.rbac import require_role
from monitoring.adapters.in_memory import InMemoryAlertRepository
from monitoring.exceptions import AlertAlreadyResolvedError, AlertNotFoundError
from monitoring.protocols import AlertsServiceProtocol
from monitoring.service import create_alerts_service
from monitoring.service_models import (
    AlertActionResponse,
    AlertListRequest,
    AlertListResponse,
    ResolutionRequest,
)

__all__ = ["get_alerts_service", "router"]


@lru_cache(maxsize=1)
def get_alerts_service() -> AlertsServiceProtocol:
    """Return the default alerts service.

    Wired against an in-memory alert repository — the integration agent will
    swap this for the production wiring once `api/dependencies.py` is updated
    in E5-S14. Tests override this factory via ``app.dependency_overrides``.
    """

    return create_alerts_service(InMemoryAlertRepository())


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse, dependencies=[Depends(require_role("viewer"))])
async def list_alerts(
    severity: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    alerts_service: AlertsServiceProtocol = Depends(get_alerts_service),
) -> AlertListResponse:
    """List alerts filtered by severity, entity type, and status."""

    request = AlertListRequest(
        severity=severity,
        entity_type=entity_type,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return alerts_service.list_alerts(request)


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("analyst"))],
)
async def acknowledge_alert(
    alert_id: str,
    alerts_service: AlertsServiceProtocol = Depends(get_alerts_service),
) -> AlertActionResponse:
    """Acknowledge an alert and return the updated record."""

    try:
        alert = alerts_service.acknowledge_alert(alert_id)
    except AlertNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AlertAlreadyResolvedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AlertActionResponse(alert=alert)


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("analyst"))],
)
async def resolve_alert(
    alert_id: str,
    request: ResolutionRequest,
    alerts_service: AlertsServiceProtocol = Depends(get_alerts_service),
) -> AlertActionResponse:
    """Resolve an alert with the supplied resolution metadata."""

    try:
        alert = alerts_service.resolve_alert(alert_id, request)
    except AlertNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AlertAlreadyResolvedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AlertActionResponse(alert=alert)
