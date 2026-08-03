"""Alerts API router — list, detail, and acknowledge from the durable store.

Serves every route from the durable ``alert_history`` table via
``AlertFeedStoreProtocol`` (alerts.36); response shaping lives in
``api.dependencies`` alongside the rest of the payload-builder factories.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status

from api.contracts import (
    AlertAssignmentRequest,
    AlertBulkStatusUpdateRequest,
    AlertBulkStatusUpdateResponse,
    AlertDetailResponse,
    AlertListResponse,
    AlertOperationResponse,
    AlertStatusUpdateRequest,
)
from api.dependencies import (
    build_alert_acknowledge_payload,
    build_alert_assignment_payload,
    build_alert_bulk_status_update_payload,
    build_alert_status_update_payload,
    get_alert_detail_payload,
    get_alert_feed_store,
    get_alert_list_payload,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from monitoring.adapters.protocols import AlertFeedStoreProtocol

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
    response_model=AlertOperationResponse,
    status_code=status.HTTP_200_OK,
)
async def acknowledge_alert(
    alert_id: str = Path(..., description="Alert identifier."),
    knowledge_base_id: str = Query(
        ..., min_length=1, description="Knowledge base identifier."
    ),
    store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    user: User = Depends(require_role("analyst")),
) -> AlertOperationResponse:
    """Acknowledge an alert; returns the updated row and audit receipt."""
    return build_alert_acknowledge_payload(
        alert_id=alert_id,
        knowledge_base_id=knowledge_base_id,
        store=store,
        actor=user.user_id,
    )


@router.patch(
    "/{alert_id}/assignment",
    response_model=AlertOperationResponse,
    status_code=status.HTTP_200_OK,
)
async def assign_alert(
    payload: AlertAssignmentRequest,
    alert_id: str = Path(..., description="Alert identifier."),
    store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    user: User = Depends(require_role("analyst")),
) -> AlertOperationResponse:
    """Assign or clear one KB-scoped alert and return an audit receipt."""
    return build_alert_assignment_payload(
        alert_id=alert_id,
        payload=payload,
        store=store,
        actor=user.user_id,
    )


@router.patch(
    "/{alert_id}/status",
    response_model=AlertOperationResponse,
    status_code=status.HTTP_200_OK,
)
async def update_alert_status(
    payload: AlertStatusUpdateRequest,
    alert_id: str = Path(..., description="Alert identifier."),
    store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    user: User = Depends(require_role("analyst")),
) -> AlertOperationResponse:
    """Transition one KB-scoped alert and return an audit receipt."""
    return build_alert_status_update_payload(
        alert_id=alert_id,
        payload=payload,
        store=store,
        actor=user.user_id,
    )


@router.post(
    "/bulk/status",
    response_model=AlertBulkStatusUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_alert_status_bulk(
    payload: AlertBulkStatusUpdateRequest,
    store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    user: User = Depends(require_role("analyst")),
) -> AlertBulkStatusUpdateResponse:
    """Transition selected KB-scoped alerts and report skipped rows."""
    return build_alert_bulk_status_update_payload(
        payload=payload,
        store=store,
        actor=user.user_id,
    )
