"""Audit ledger query router."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import AuditEventListResponse
from api.dependencies import get_audit_event_list_payload
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "/events",
    response_model=AuditEventListResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def list_audit_events(
    events: AuditEventListResponse = Depends(get_audit_event_list_payload),
) -> AuditEventListResponse:
    """Return a filtered page of immutable audit ledger events."""
    return events
