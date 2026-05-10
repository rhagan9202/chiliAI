"""Policy intelligence router exposing policy gap read models and brief generation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import (
    PolicyBriefResponse,
    PolicyGapCaseListResponse,
    PolicyGapDetailResponse,
    PolicyGapListResponse,
)
from api.dependencies import (
    get_policy_brief_payload,
    get_policy_gap_cases_payload,
    get_policy_gap_detail_payload,
    get_policy_gap_list_payload,
)
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/policy", tags=["policy"])


@router.get(
    "/gaps",
    response_model=PolicyGapListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_policy_gaps(
    gaps: PolicyGapListResponse = Depends(get_policy_gap_list_payload),
) -> PolicyGapListResponse:
    """Return policy gaps for supervisor and policy-intelligence views."""
    return gaps


@router.get(
    "/gaps/{gap_id}",
    response_model=PolicyGapDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_policy_gap(
    gap: PolicyGapDetailResponse = Depends(get_policy_gap_detail_payload),
) -> PolicyGapDetailResponse:
    """Return one policy gap detail payload."""
    return gap


@router.get(
    "/gaps/{gap_id}/cases",
    response_model=PolicyGapCaseListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_policy_gap_cases(
    cases: PolicyGapCaseListResponse = Depends(get_policy_gap_cases_payload),
) -> PolicyGapCaseListResponse:
    """Return affected cases for one policy gap."""
    return cases


@router.post(
    "/briefs",
    response_model=PolicyBriefResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def create_policy_brief(
    brief: PolicyBriefResponse = Depends(get_policy_brief_payload),
) -> PolicyBriefResponse:
    """Generate a policy brief from one policy gap."""
    return brief