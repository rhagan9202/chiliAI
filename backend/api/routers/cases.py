"""Case management router exposing human-review read models."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from api.contracts import (
    CaseAttachAlertRequest,
    CaseCreateRequest,
    CaseDossierExportResponse,
    CaseDossierResponse,
    CaseDetailResponse,
    CaseFeedbackCreateRequest,
    CaseListResponse,
    CasePromoteRequest,
    CaseUpdateRequest,
)
from api.dependencies import (
    get_alert_feed_store,
    get_audit_log_service,
    get_case_attach_alert_payload,
    get_case_create_payload,
    get_case_dossier_export_payload,
    get_case_dossier_payload,
    get_case_detail_payload,
    get_case_feedback_payload,
    get_case_list_payload,
    get_case_promote_payload,
    get_case_service,
    get_case_update_payload,
    get_evidence_pack_repository,
    record_case_audit_event,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from auditlog.service import AuditLogService
from analytics.explainability.repository import EvidencePackRepository
from cases.service import CaseService
from monitoring.adapters.protocols import AlertFeedStoreProtocol

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
)
async def create_case(
    payload: CaseCreateRequest,
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    audit_service: AuditLogService = Depends(get_audit_log_service),
    user: User = Depends(require_role("analyst")),
) -> CaseDetailResponse:
    """Create and return a new case."""
    case_detail = get_case_create_payload(
        payload=payload,
        knowledge_base_id=knowledge_base_id,
        service=service,
        evidence_repository=evidence_repository,
        alert_store=alert_store,
    )
    record_case_audit_event(
        audit_service,
        knowledge_base_id=knowledge_base_id,
        actor_user_id=user.user_id,
        actor_email=user.email,
        actor_roles=user.roles,
        action="case.create",
        case_id=case_detail.case.id,
        before=None,
        after={
            "status": case_detail.case.status,
            "priority": case_detail.case.priority,
            "alert_count": len(case_detail.case.alert_ids),
        },
    )
    return case_detail


@router.post(
    "/promote",
    response_model=CaseDetailResponse,
)
async def promote_alert_to_case(
    payload: CasePromoteRequest,
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    audit_service: AuditLogService = Depends(get_audit_log_service),
    user: User = Depends(require_role("analyst")),
) -> CaseDetailResponse:
    """Promote an alert into a new case and return the case detail."""
    case_detail = get_case_promote_payload(
        payload=payload,
        knowledge_base_id=knowledge_base_id,
        service=service,
        alert_store=alert_store,
        evidence_repository=evidence_repository,
    )
    record_case_audit_event(
        audit_service,
        knowledge_base_id=knowledge_base_id,
        actor_user_id=user.user_id,
        actor_email=user.email,
        actor_roles=user.roles,
        action="case.promote",
        case_id=case_detail.case.id,
        before=None,
        after={
            "status": case_detail.case.status,
            "priority": case_detail.case.priority,
            "originating_alert_id": case_detail.case.originating_alert_id,
            "evidence_pack_id": case_detail.case.evidence_pack_id,
        },
        metadata={"alert_id": payload.alert_id},
    )
    return case_detail


@router.post(
    "/{case_id}/alerts",
    response_model=CaseDetailResponse,
)
async def attach_alert_to_case(
    payload: CaseAttachAlertRequest,
    case_id: str = Path(..., description="Case the alert is attached to."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    audit_service: AuditLogService = Depends(get_audit_log_service),
    user: User = Depends(require_role("analyst")),
) -> CaseDetailResponse:
    """Attach an alert to an existing case and return the updated detail.

    ``POST /cases/promote`` opens a *new* case; this is the other half — adding
    to one that already exists (UXA-405).
    """
    before_case = service.get(knowledge_base_id=knowledge_base_id, case_id=case_id)
    case_detail = get_case_attach_alert_payload(
        payload=payload,
        case_id=case_id,
        knowledge_base_id=knowledge_base_id,
        service=service,
        alert_store=alert_store,
        evidence_repository=evidence_repository,
    )
    record_case_audit_event(
        audit_service,
        knowledge_base_id=knowledge_base_id,
        actor_user_id=user.user_id,
        actor_email=user.email,
        actor_roles=user.roles,
        action="case.alert.attach",
        case_id=case_detail.case.id,
        before={
            "alert_count": len(before_case.alert_ids) if before_case is not None else 0,
            "alert_ids": list(before_case.alert_ids) if before_case is not None else [],
        },
        after={
            "alert_count": len(case_detail.case.alert_ids),
            "alert_ids": list(case_detail.case.alert_ids),
            "attached_alert_id": payload.alert_id,
        },
        metadata={"alert_id": payload.alert_id},
    )
    return case_detail


@router.patch(
    "/{case_id}",
    response_model=CaseDetailResponse,
)
async def update_case(
    payload: CaseUpdateRequest,
    case_id: str = Path(..., description="Case identifier."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    audit_service: AuditLogService = Depends(get_audit_log_service),
    user: User = Depends(require_role("analyst")),
) -> CaseDetailResponse:
    """Patch and return a case."""
    before_case = service.get(knowledge_base_id=knowledge_base_id, case_id=case_id)
    case_detail = get_case_update_payload(
        payload=payload,
        case_id=case_id,
        knowledge_base_id=knowledge_base_id,
        service=service,
        evidence_repository=evidence_repository,
        alert_store=alert_store,
    )
    changed_fields = [
        field
        for field in ("title", "status", "priority", "assignee")
        if getattr(payload, field) is not None
    ]
    record_case_audit_event(
        audit_service,
        knowledge_base_id=knowledge_base_id,
        actor_user_id=user.user_id,
        actor_email=user.email,
        actor_roles=user.roles,
        action="case.update",
        case_id=case_detail.case.id,
        before={
            field: getattr(before_case, field)
            for field in changed_fields
            if before_case is not None
        },
        after={field: getattr(case_detail.case, field) for field in changed_fields},
    )
    return case_detail


@router.post(
    "/{case_id}/feedback",
    response_model=CaseDetailResponse,
)
async def add_feedback(
    payload: CaseFeedbackCreateRequest,
    case_id: str = Path(..., description="Case identifier."),
    knowledge_base_id: str = Query(..., min_length=1, description="Knowledge base scope."),
    service: CaseService = Depends(get_case_service),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
    audit_service: AuditLogService = Depends(get_audit_log_service),
    user: User = Depends(require_role("analyst")),
) -> CaseDetailResponse:
    """Append analyst feedback to a case and return the updated detail."""
    before_case = service.get(knowledge_base_id=knowledge_base_id, case_id=case_id)
    case_detail = get_case_feedback_payload(
        payload=payload,
        case_id=case_id,
        knowledge_base_id=knowledge_base_id,
        service=service,
        evidence_repository=evidence_repository,
        alert_store=alert_store,
    )
    record_case_audit_event(
        audit_service,
        knowledge_base_id=knowledge_base_id,
        actor_user_id=user.user_id,
        actor_email=user.email,
        actor_roles=user.roles,
        action="case.feedback.create",
        case_id=case_detail.case.id,
        before={
            "feedback_count": (
                len(before_case.feedback_history) if before_case is not None else 0
            )
        },
        after={
            "feedback_count": len(case_detail.feedback_history),
            "label": payload.label,
            "evidence_adequacy": payload.evidence_adequacy,
            "missing_evidence_count": len(payload.missing_evidence),
        },
    )
    return case_detail
