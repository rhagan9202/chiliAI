"""Policy intelligence router: rule-generated items + analyst triage (BL-011)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from api.contracts import (
    PolicyItemDetailResponse,
    PolicyItemListResponse,
    PolicyTriageRequest,
)
from api.dependencies import (
    _apply_policy_triage,
    get_case_service,
    get_policy_item_detail_payload,
    get_policy_item_list_payload,
    get_policy_service,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from cases.service import CaseService
from policy.service import PolicyService

__all__ = ["router"]

router = APIRouter(prefix="/policy", tags=["policy"])


@router.get(
    "/items",
    response_model=PolicyItemListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_policy_items(
    payload: PolicyItemListResponse = Depends(get_policy_item_list_payload),
) -> PolicyItemListResponse:
    """List KB-scoped policy items, optionally filtered by status."""
    return payload


@router.get(
    "/items/{item_id}",
    response_model=PolicyItemDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_policy_item(
    payload: PolicyItemDetailResponse = Depends(get_policy_item_detail_payload),
) -> PolicyItemDetailResponse:
    """Return one policy item detail payload."""
    return payload


@router.post(
    "/items/{item_id}/triage",
    response_model=PolicyItemDetailResponse,
)
async def triage_policy_item(
    payload: PolicyTriageRequest,
    item_id: str = Path(...),
    knowledge_base_id: str = Query(...),
    policy_service: PolicyService = Depends(get_policy_service),
    case_service: CaseService = Depends(get_case_service),
    user: User = Depends(require_role("analyst")),
) -> PolicyItemDetailResponse:
    """Triage a policy item (accept/reject/defer/escalate)."""
    return _apply_policy_triage(
        policy_service=policy_service,
        case_service=case_service,
        knowledge_base_id=knowledge_base_id,
        item_id=item_id,
        payload=payload,
        actor=user.user_id,
    )
