"""Knowledge base API endpoints."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from api._kb_busy import KbBusyError, WorkflowBusyTracker, ensure_kb_idle
from api._kb_projection import (
    document_status_for_knowledge_base,
    project_knowledge_base,
)
from knowledgebases import DocumentRecord, KnowledgeBaseRepository
from api.dependencies import (
    get_event_bus,
    get_domain_config,
    get_graph_service,
    get_ingestion_service,
    get_knowledge_base_repository,
    get_object_store,
    get_raw_record_store,
    get_vector_service,
    get_workflow_tracker,
)
from api.middleware.rbac import require_role
from config.schema import DomainConfig, ValidationConfig
from events.protocols import EventBus
from events.types import KnowledgeBaseCreatedEvent, KnowledgeBaseDeletedEvent
from graph.protocols import GraphServiceProtocol
from ingestion.protocols import IngestionServiceProtocol
from ingestion.service_models import DocumentReceipt, DocumentSubmission
from records.adapters.protocols import RawRecordStore
from shared.types import KnowledgeBase
from shared.utils import generate_id, utc_now
from shared.validation import sanitize_filename, validate_content_type
from storage.protocols import ObjectStore
from vectorstore.protocols import VectorServiceProtocol

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
    knowledge_base_id: str
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
    dependencies=[Depends(require_role("admin"))],
)
async def delete_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    vector_service: VectorServiceProtocol = Depends(get_vector_service),
    raw_record_store: RawRecordStore = Depends(get_raw_record_store),
    object_store: ObjectStore = Depends(get_object_store),
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
    event_bus: EventBus = Depends(get_event_bus),
) -> Response:
    """Cascade-delete a KB across graph, vector, raw_records, object store, and metadata."""
    existing_kb = repository.get(knowledge_base_id)
    if existing_kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )

    try:
        ensure_kb_idle(knowledge_base_id, tracker=workflow_tracker)
    except KbBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    steps: list[dict[str, object]] = []
    pending_cleanup = False

    def _run(step_name: str, fn: Callable[[], object]) -> None:
        nonlocal pending_cleanup
        try:
            fn()
            steps.append({"step": step_name, "status": "succeeded"})
        except Exception as exc:  # noqa: BLE001 — surface every failure in the 207 body
            pending_cleanup = True
            steps.append({"step": step_name, "status": "failed", "error": str(exc)})

    _run("graph", lambda: graph_service.delete_knowledge_base(knowledge_base_id))
    _run("vector", lambda: vector_service.delete_knowledge_base(knowledge_base_id))
    _run("raw_records", lambda: raw_record_store.delete_by_kb(knowledge_base_id))
    _run(
        "object_store",
        lambda: _delete_object_store_prefix(object_store, knowledge_base_id),
    )

    if pending_cleanup:
        repository.mark_pending_cleanup(knowledge_base_id)
        event_bus.publish(
            KnowledgeBaseDeletedEvent(
                knowledge_base_id=knowledge_base_id,
                cleanup_pending=True,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_207_MULTI_STATUS,
            content={
                "knowledge_base_id": knowledge_base_id,
                "pending_cleanup": True,
                "steps": steps,
            },
        )

    repository.delete(knowledge_base_id)
    event_bus.publish(
        KnowledgeBaseDeletedEvent(
            knowledge_base_id=knowledge_base_id,
            cleanup_pending=False,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _delete_object_store_prefix(
    object_store: ObjectStore, knowledge_base_id: str
) -> None:
    """Remove all object-store keys under the KB prefix."""
    prefix = f"knowledgebases/{knowledge_base_id}/"
    for key in object_store.list_keys(prefix):
        object_store.delete(key)


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
            knowledge_base_id=record.knowledge_base_id,
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
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
) -> None:
    """Delete a single document from a knowledge base and its stored artifacts."""
    existing_kb = repository.get(knowledge_base_id)
    if existing_kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )

    if existing_kb.pending_cleanup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Knowledge base '{knowledge_base_id}' has pending cleanup; cannot mutate until resolved.",
        )

    try:
        ensure_kb_idle(knowledge_base_id, tracker=workflow_tracker)
    except KbBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

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
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    vector_service: VectorServiceProtocol = Depends(get_vector_service),
    object_store: ObjectStore = Depends(get_object_store),
    config: DomainConfig = Depends(get_domain_config),
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
) -> DocumentRegistrationResponse:
    """Register uploaded documents and enqueue ingestion work."""
    existing_kb = repository.get(knowledge_base_id)
    if existing_kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )

    if existing_kb.pending_cleanup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Knowledge base '{knowledge_base_id}' has pending cleanup; cannot mutate until resolved.",
        )

    try:
        ensure_kb_idle(knowledge_base_id, tracker=workflow_tracker)
    except KbBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    validation = config.validation or ValidationConfig()
    max_bytes = validation.max_file_size_mb * 1024 * 1024
    allowed_content_types = set(validation.allowed_content_types)
    submissions: list[DocumentSubmission] = []
    raw_metadata: list[tuple[str, str | None, int, str, str | None]] = []
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
        content_hash = hashlib.sha256(content).hexdigest()

        # Dedup: if a document with this content hash already exists, cascade-
        # delete its graph nodes, vector points, and metadata record before
        # re-ingesting, and surface the replaced id in the receipt.
        replaced_document_id: str | None = None
        existing = repository.get_document_by_content_hash(knowledge_base_id, content_hash)
        if existing is not None:
            graph_service.delete_by_source_document(knowledge_base_id, existing.id)
            vector_service.delete_by_source_document(knowledge_base_id, existing.id)
            repository.delete_document(knowledge_base_id, existing.id)
            # Also drop the source object so register_documents re-publishes the event.
            prefix = f"knowledgebases/{knowledge_base_id}/documents/{existing.id}/"
            for key in object_store.list_keys(prefix):
                object_store.delete(key)
            replaced_document_id = existing.id

        submissions.append(
            DocumentSubmission(
                filename=filename,
                content=content,
                content_type=upload.content_type,
            )
        )
        raw_metadata.append(
            (filename, upload.content_type, len(content), content_hash, replaced_document_id)
        )

    receipts = ingestion_service.register_documents(knowledge_base_id, submissions)

    final_receipts: list[DocumentReceipt] = []
    for receipt, (filename, content_type, size_bytes, content_hash, replaced_document_id) in zip(
        receipts, raw_metadata, strict=True
    ):
        if repository.get_document(knowledge_base_id, receipt.source_document_id) is None:
            repository.add_document(
                DocumentRecord(
                    id=receipt.source_document_id,
                    knowledge_base_id=knowledge_base_id,
                    filename=filename,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    status=receipt.status.value,
                    storage_key=receipt.storage_key,
                    content_hash=content_hash,
                )
            )
        final_receipts.append(
            receipt.model_copy(update={"replaced_document_id": replaced_document_id})
        )

    return DocumentRegistrationResponse(documents=final_receipts)
