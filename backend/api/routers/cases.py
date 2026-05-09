"""Case management router exposing human-review read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import (
    CaseCreateRequest,
    CaseDetailResponse,
    CaseFeedbackCreateRequest,
    CaseListResponse,
    CaseUpdateRequest,
)
from api.dependencies import (
    get_case_create_payload,
    get_case_detail_payload,
    get_case_feedback_payload,
    get_case_list_payload,
    get_case_update_payload,
)

__all__ = ["router"]

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=CaseListResponse)
async def list_cases(
    cases: CaseListResponse = Depends(get_case_list_payload),
) -> CaseListResponse:
    """Return the case management queue."""
    return cases


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(
    case_detail: CaseDetailResponse = Depends(get_case_detail_payload),
) -> CaseDetailResponse:
    """Return one case detail payload."""
    return case_detail


@router.post("", response_model=CaseDetailResponse)
async def create_case(
    case_detail: CaseDetailResponse = Depends(get_case_create_payload),
) -> CaseDetailResponse:
    """Create and return a new case."""
    return case_detail


@router.patch("/{case_id}", response_model=CaseDetailResponse)
async def update_case(
    case_detail: CaseDetailResponse = Depends(get_case_update_payload),
) -> CaseDetailResponse:
    """Patch and return a case."""
    return case_detail


@router.post("/{case_id}/feedback", response_model=CaseDetailResponse)
async def add_feedback(
    case_detail: CaseDetailResponse = Depends(get_case_feedback_payload),
) -> CaseDetailResponse:
    """Append analyst feedback to a case and return the updated detail."""
    return case_detail