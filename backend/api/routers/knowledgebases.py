"""Knowledge base API endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from api._kb_projection import (
    document_status_for_knowledge_base,
    project_knowledge_base,
)
from api._kb_store import DocumentRecord, KnowledgeBaseRepository
from api.dependencies import (
    get_event_bus,
    get_domain_config,
    get_graph_service,
    get_ingestion_service,
    get_knowledge_base_repository,
    get_object_store,
)
from api.middleware.rbac import require_role
from config.schema import DomainConfig, ValidationConfig
from events.protocols import EventBus
from events.types import KnowledgeBaseCreatedEvent, KnowledgeBaseDeletedEvent
from graph.protocols import GraphServiceProtocol
from ingestion.protocols import IngestionServiceProtocol
from ingestion.service_models import DocumentReceipt, DocumentSubmission
from shared.types import KnowledgeBase
from shared.utils import generate_id, utc_now
from shared.validation import sanitize_filename, validate_content_type
from storage.protocols import ObjectStore

__all__ = [
    "CreateKbRequest",
    "DocumentListResponse",
    "DocumentRegistrationResponse",
    "DocumentSummary",
    "KbListResponse",
    "router",
]


class DocumentRegistrationResponse(BaseModel):
    """Response model for document registration requests."""

    documents: list[DocumentReceipt]


class CreateKbRequest(BaseModel):
    """Request payload for creating a new knowledge base."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class KbListResponse(BaseModel):
    """Paginated knowledge base list response."""

    items: list[KnowledgeBase]
    total: int = Field(ge=0)


class DocumentSummary(BaseModel):
    """Summary projection of a registered document."""

    id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str
    created_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated knowledge base document list response."""

    items: list[DocumentSummary]
    total: int = Field(ge=0)


router = APIRouter(prefix="/knowledgebases", tags=["knowledge-bases"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeBase,
    dependencies=[Depends(require_role("analyst"))],
)
async def create_knowledge_base(
    payload: CreateKbRequest,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    event_bus: EventBus = Depends(get_event_bus),
) -> KnowledgeBase:
    """Create a new knowledge base and publish a creation event."""
    knowledge_base = KnowledgeBase(
        id=generate_id(),
        name=payload.name,
        description=payload.description,
        created_at=utc_now(),
    )
    repository.create(knowledge_base)
    event_bus.publish(
        KnowledgeBaseCreatedEvent(knowledge_base_id=knowledge_base.id)
    )
    return knowledge_base


@router.get(
    "",
    response_model=KbListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_knowledge_bases(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
) -> KbListResponse:
    """Return a paginated listing of registered knowledge bases."""
    items, total = repository.list(limit=limit, offset=offset)
    return KbListResponse(
        items=[
            project_knowledge_base(item, repository, graph_service, object_store)
            for item in items
        ],
        total=total,
    )


@router.get(
    "/{knowledge_base_id}",
    response_model=KnowledgeBase,
    dependencies=[Depends(require_role("viewer"))],
)
async def read_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
) -> KnowledgeBase:
    """Return a single knowledge base by id or 404."""
    knowledge_base = repository.get(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )
    return project_knowledge_base(
        knowledge_base,
        repository,
        graph_service,
        object_store,
    )


@router.delete(
    "/{knowledge_base_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
    event_bus: EventBus = Depends(get_event_bus),
) -> None:
    """Delete a knowledge base, its stored artifacts, and publish an event."""
    if repository.get(knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )

    prefix = f"knowledgebases/{knowledge_base_id}/"
    for key in object_store.list_keys(prefix):
        object_store.delete(key)

    graph_service.delete_knowledge_base(knowledge_base_id)
    repository.delete(knowledge_base_id)
    event_bus.publish(
        KnowledgeBaseDeletedEvent(knowledge_base_id=knowledge_base_id)
    )


@router.get(
    "/{knowledge_base_id}/documents",
    response_model=DocumentListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_knowledge_base_documents(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
) -> DocumentListResponse:
    """Return registered documents for a knowledge base."""
    knowledge_base = repository.get(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )
    hydrated_knowledge_base = project_knowledge_base(
        knowledge_base,
        repository,
        graph_service,
        object_store,
    )

    records, total = repository.list_documents(
        knowledge_base_id, limit=limit, offset=offset
    )
    items = [
        DocumentSummary(
            id=record.id,
            filename=record.filename,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            status=document_status_for_knowledge_base(
                record,
                hydrated_knowledge_base,
                repository,
            ),
            created_at=record.created_at,
        )
        for record in records
    ]
    return DocumentListResponse(items=items, total=total)


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("analyst"))],
)
async def delete_knowledge_base_document(
    knowledge_base_id: str,
    document_id: str,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    object_store: ObjectStore = Depends(get_object_store),
) -> None:
    """Delete a single document from a knowledge base and its stored artifacts."""
    if repository.get(knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )

    record = repository.get_document(knowledge_base_id, document_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Document '{document_id}' not found in knowledge base "
                f"'{knowledge_base_id}'."
            ),
        )

    prefix = f"knowledgebases/{knowledge_base_id}/documents/{document_id}/"
    for key in object_store.list_keys(prefix):
        object_store.delete(key)

    repository.delete_document(knowledge_base_id, document_id)


@router.post(
    "/{knowledge_base_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentRegistrationResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def register_knowledge_base_documents(
    knowledge_base_id: str,
    files: list[UploadFile] = File(...),
    ingestion_service: IngestionServiceProtocol = Depends(get_ingestion_service),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    config: DomainConfig = Depends(get_domain_config),
) -> DocumentRegistrationResponse:
    """Register uploaded documents and enqueue ingestion work."""
    if repository.get(knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )

    validation = config.validation or ValidationConfig()
    max_bytes = validation.max_file_size_mb * 1024 * 1024
    allowed_content_types = set(validation.allowed_content_types)
    submissions: list[DocumentSubmission] = []
    raw_metadata: list[tuple[str, str | None, int]] = []
    for upload in files:
        if not validate_content_type(upload.content_type, allowed_content_types):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Content type '{upload.content_type}' not allowed.",
            )

        content = await upload.read()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"File '{upload.filename or 'upload'}' exceeds the "
                    f"configured {validation.max_file_size_mb} MB limit."
                ),
            )

        filename = sanitize_filename(upload.filename or "document")
        submissions.append(
            DocumentSubmission(
                filename=filename,
                content=content,
                content_type=upload.content_type,
            )
        )
        raw_metadata.append(
            (filename, upload.content_type, len(content))
        )

    receipts = ingestion_service.register_documents(knowledge_base_id, submissions)

    for receipt, (filename, content_type, size_bytes) in zip(
        receipts, raw_metadata, strict=True
    ):
        repository.add_document(
            DocumentRecord(
                id=receipt.source_document_id,
                knowledge_base_id=knowledge_base_id,
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                status=receipt.status.value,
                storage_key=receipt.storage_key,
            )
        )

    return DocumentRegistrationResponse(documents=receipts)
