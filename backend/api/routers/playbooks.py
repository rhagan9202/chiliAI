"""KB-scoped fraud playbook API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from api.contracts import (
    PlaybookEvidenceRequirementResponse,
    PlaybookExportResponse,
    PlaybookImportRequestPayload,
    PlaybookImportResponse,
    PlaybookListResponse,
    PlaybookPublishRequestPayload,
    PlaybookRagPromptResponse,
    PlaybookResponse,
    PlaybookSnapshotResponse,
    PlaybookWorkflowStepResponse,
)
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_playbook_repository,
    get_playbook_service,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from config.schema import DomainConfig, FraudPlaybookConfig
from knowledgebases.protocols import KnowledgeBaseRepository
from playbooks.models import PlaybookImportResult, PlaybookPublishRequest, PlaybookSnapshot
from playbooks.repository import PlaybookRepository
from playbooks.service import PlaybookService
from shared.types import KnowledgeBase

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/playbooks",
    tags=["playbooks"],
)


def _can_access_knowledge_base(user: User, knowledge_base_id: str) -> bool:
    allowed = user.knowledge_base_ids
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


def _require_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository,
    user: User,
    domain_config: DomainConfig,
) -> tuple[KnowledgeBase, str]:
    if not _can_access_knowledge_base(user, knowledge_base_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )
    kb = repository.get(knowledge_base_id)
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )
    return kb, _resolve_domain_name(kb, domain_config)


def _resolve_domain_name(kb: KnowledgeBase, domain_config: DomainConfig) -> str:
    domain_name = getattr(kb, "domain_name", None)
    if isinstance(domain_name, str) and domain_name:
        return domain_name
    return kb.domain or domain_config.domain.name


@router.get(
    "",
    response_model=PlaybookListResponse,
)
def list_playbooks(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    playbook_repository: PlaybookRepository = Depends(get_playbook_repository),
    service: PlaybookService = Depends(get_playbook_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> PlaybookListResponse:
    """Return config-authored playbooks and published snapshots for one KB."""
    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    try:
        definitions = service.list_config_playbooks(
            domain_name=domain_name,
            limit=limit,
            offset=offset,
        )
        service.adopt_legacy_snapshots(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
        )
        published = playbook_repository.list_snapshots(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
            limit=limit,
            offset=offset,
        )
    except KeyError as exc:
        raise _not_found("Knowledge base", knowledge_base_id) from exc

    return PlaybookListResponse(
        items=[_playbook_response(item) for item in definitions.items],
        published=[_snapshot_response(snapshot) for snapshot in published.items],
        total=definitions.total,
        limit=definitions.limit,
        offset=definitions.offset,
        published_total=published.total,
        published_limit=published.limit,
        published_offset=published.offset,
    )


@router.get(
    "/export",
    response_model=PlaybookExportResponse,
)
def export_playbooks(
    knowledge_base_id: str,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    playbook_repository: PlaybookRepository = Depends(get_playbook_repository),
    service: PlaybookService = Depends(get_playbook_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> PlaybookExportResponse:
    """Export published playbooks for one KB domain, falling back to seeds."""
    del playbook_repository
    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    try:
        artifact = service.export_domain_playbooks(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
        )
    except KeyError as exc:
        raise _not_found("Knowledge base", knowledge_base_id) from exc
    return PlaybookExportResponse(
        artifact=artifact,
    )


@router.get(
    "/{playbook_id}/versions/{version}",
    response_model=PlaybookResponse,
)
def get_playbook_version(
    knowledge_base_id: str,
    playbook_id: str = Path(...),
    version: str = Path(...),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    playbook_repository: PlaybookRepository = Depends(get_playbook_repository),
    service: PlaybookService = Depends(get_playbook_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("viewer")),
) -> PlaybookResponse:
    """Return one published playbook version or config-authored seed."""
    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    service.adopt_legacy_snapshots(
        knowledge_base_id=knowledge_base_id,
        domain_name=domain_name,
    )
    snapshot = playbook_repository.get_snapshot(
        knowledge_base_id=knowledge_base_id,
        domain_name=domain_name,
        playbook_id=playbook_id,
        version=version,
    )
    if snapshot is not None:
        return _playbook_response(snapshot.definition)

    try:
        definition = service.get_config_playbook(
            domain_name=domain_name,
            playbook_id=playbook_id,
            version=version,
        )
    except KeyError as exc:
        raise _not_found("Knowledge base", knowledge_base_id) from exc
    if definition is not None:
        return _playbook_response(definition)
    raise _not_found("Playbook", f"{playbook_id}:{version}")


@router.post(
    "/{playbook_id}/publish",
    response_model=PlaybookSnapshotResponse,
)
def publish_playbook(
    knowledge_base_id: str,
    playbook_id: str,
    payload: PlaybookPublishRequestPayload,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    playbook_repository: PlaybookRepository = Depends(get_playbook_repository),
    service: PlaybookService = Depends(get_playbook_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> PlaybookSnapshotResponse:
    """Publish a config-authored seed playbook as an immutable snapshot."""
    del playbook_repository
    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    try:
        snapshot = service.publish_config_playbook(
            PlaybookPublishRequest(
                domain_name=domain_name,
                knowledge_base_id=knowledge_base_id,
                playbook_id=playbook_id,
                version=payload.version,
                actor_user_id=user.user_id,
            )
        )
    except KeyError as exc:
        raise _not_found("Playbook", f"{playbook_id}:{payload.version}") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _snapshot_response(snapshot)


@router.post(
    "/import",
    response_model=PlaybookImportResponse,
)
def import_playbooks(
    knowledge_base_id: str,
    payload: PlaybookImportRequestPayload,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    playbook_repository: PlaybookRepository = Depends(get_playbook_repository),
    service: PlaybookService = Depends(get_playbook_service),
    domain_config: DomainConfig = Depends(get_domain_config),
    user: User = Depends(require_role("admin")),
) -> PlaybookImportResponse:
    """Import a portable playbook artifact for one KB domain."""
    del playbook_repository
    _, domain_name = _require_knowledge_base(
        knowledge_base_id,
        kb_repository,
        user,
        domain_config,
    )
    artifact = payload.artifact
    if artifact.domain_name != domain_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Artifact domain '{artifact.domain_name}' does not match "
                f"knowledge base domain '{domain_name}'."
            ),
        )
    try:
        result = service.import_playbooks(
            artifact,
            knowledge_base_id=knowledge_base_id,
            actor_user_id=user.user_id,
        )
    except KeyError as exc:
        raise _not_found("Knowledge base", knowledge_base_id) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _import_response(result)


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{identifier}' not found.",
    )


def _playbook_response(playbook: FraudPlaybookConfig) -> PlaybookResponse:
    return PlaybookResponse(
        id=playbook.id,
        version=playbook.version,
        title=playbook.title,
        summary=playbook.summary,
        status=playbook.status,
        typology_ids=list(playbook.typology_ids),
        feature_ids=list(playbook.feature_ids),
        policy_rule_ids=list(playbook.policy_rule_ids),
        evidence_requirements=[
            PlaybookEvidenceRequirementResponse(
                id=requirement.id,
                label=requirement.label,
                description=requirement.description,
                source_types=list(requirement.source_types),
                required=requirement.required,
            )
            for requirement in playbook.evidence_requirements
        ],
        workflow_steps=[
            PlaybookWorkflowStepResponse(
                id=step.id,
                label=step.label,
                capability_ref=step.capability_ref,
                input_refs=list(step.input_refs),
                output_refs=list(step.output_refs),
                requires_human_approval=step.requires_human_approval,
            )
            for step in playbook.workflow_steps
        ],
        rag_prompts=[
            PlaybookRagPromptResponse(
                id=prompt.id,
                model_ref=prompt.model_ref,
                prompt_version=prompt.prompt_version,
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
            )
            for prompt in playbook.rag_prompts
        ],
        decision_guidance=list(playbook.decision_guidance),
        export_tags=list(playbook.export_tags),
    )


def _snapshot_response(snapshot: PlaybookSnapshot) -> PlaybookSnapshotResponse:
    return PlaybookSnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        knowledge_base_id=snapshot.knowledge_base_id,
        domain_name=snapshot.domain_name,
        playbook_id=snapshot.playbook_id,
        version=snapshot.version,
        status=snapshot.status,
        definition=_playbook_response(snapshot.definition),
        source=snapshot.source,
        published_by=snapshot.published_by,
        published_at=snapshot.published_at,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
    )


def _import_response(result: PlaybookImportResult) -> PlaybookImportResponse:
    return PlaybookImportResponse(
        domain_name=result.domain_name,
        imported_count=result.imported_count,
        snapshot_ids=list(result.snapshot_ids),
    )
