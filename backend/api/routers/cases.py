"""Case management router exposing human-review read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.contracts import (
    CaseDossierExportResponse,
    CaseDossierResponse,
    CaseDetailResponse,
    CaseListResponse,
)
from api.dependencies import (
    get_case_attach_alert_payload,
    get_case_create_payload,
    get_case_dossier_export_payload,
    get_case_dossier_payload,
    get_case_detail_payload,
    get_case_feedback_payload,
    get_case_list_payload,
    get_case_promote_payload,
    get_case_update_payload,
)
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=CaseListResponse, dependencies=[Depends(require_role("viewer"))])
async def list_cases(
    cases: CaseListResponse = Depends(get_case_list_payload),
) -> CaseListResponse:
    """Return the case management queue."""
    return cases


@router.get(
    "/{case_id}/dossier",
    response_model=CaseDossierResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_case_dossier(
    dossier: CaseDossierResponse = Depends(get_case_dossier_payload),
) -> CaseDossierResponse:
    """Return the case dossier projection."""
    return dossier


@router.get(
    "/{case_id}/dossier/export",
    response_model=CaseDossierExportResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def export_case_dossier(
    export: CaseDossierExportResponse = Depends(get_case_dossier_export_payload),
) -> CaseDossierExportResponse:
    """Return a portable case dossier export."""
    return export


@router.get(
    "/{case_id}",
    response_model=CaseDetailResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_case(
    case_detail: CaseDetailResponse = Depends(get_case_detail_payload),
) -> CaseDetailResponse:
    """Return one case detail payload."""
    return case_detail


@router.post(
    "",
    response_model=CaseDetailResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def create_case(
    case_detail: CaseDetailResponse = Depends(get_case_create_payload),
) -> CaseDetailResponse:
    """Create and return a new case."""
    return case_detail


@router.post(
    "/promote",
    response_model=CaseDetailResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def promote_alert_to_case(
    case_detail: CaseDetailResponse = Depends(get_case_promote_payload),
) -> CaseDetailResponse:
    """Promote an alert into a new case and return the case detail."""
    return case_detail


@router.post(
    "/{case_id}/alerts",
    response_model=CaseDetailResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def attach_alert_to_case(
    case_detail: CaseDetailResponse = Depends(get_case_attach_alert_payload),
) -> CaseDetailResponse:
    """Attach an alert to an existing case and return the updated detail.

    ``POST /cases/promote`` opens a *new* case; this is the other half — adding
    to one that already exists (UXA-405).
    """
    return case_detail


@router.patch(
    "/{case_id}",
    response_model=CaseDetailResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def update_case(
    case_detail: CaseDetailResponse = Depends(get_case_update_payload),
) -> CaseDetailResponse:
    """Patch and return a case."""
    return case_detail


@router.post(
    "/{case_id}/feedback",
    response_model=CaseDetailResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def add_feedback(
    case_detail: CaseDetailResponse = Depends(get_case_feedback_payload),
) -> CaseDetailResponse:
    """Append analyst feedback to a case and return the updated detail."""
    return case_detail
