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
from knowledgebases.models import DocumentRecord
from knowledgebases.protocols import KnowledgeBaseRepository
from api._kb_cleanup import (
    KbDeletionStores,
    get_kb_deletion_stores,
    kb_deletion_steps,
)
from api.dependencies import (
    get_agent_service,
    get_document_status_store,
    get_event_bus,
    get_domain_config,
    get_graph_service,
    get_ingestion_service,
    get_knowledge_base_repository,
    get_object_store,
    get_vector_service,
    get_workflow_tracker,
)
from api.middleware.rbac import require_role
from agent.protocols import AgentServiceProtocol
from agent.service_models import WorkflowSubmissionRequest
from agent.workflow_tracking import default_steps_for_trigger
from config.schema import DomainConfig, ValidationConfig
from events.protocols import EventBus
from events.types import KnowledgeBaseCreatedEvent, KnowledgeBaseDeletedEvent
from graph.protocols import GraphServiceProtocol
from ingestion.adapters.protocols import SourceDocumentStatusStore
from ingestion.models import IngestionStatus, SourceDocumentStatusRecord
from ingestion.protocols import IngestionServiceProtocol
from ingestion.service_models import DocumentReceipt, DocumentSubmission
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
    warning_count: int = Field(default=0, ge=0)
    warning_reasons: list[str] = Field(default_factory=list)
    # Durable ingestion projection (BL-041). ``current_status`` is None when
    # no pipeline event has been projected for the document yet.
    current_status: str | None = None
    last_error: str | None = None
    dropped_entity_count: int = Field(default=0, ge=0)
    dropped_relationship_count: int = Field(default=0, ge=0)
    drop_sample_reasons: list[str] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    """Paginated knowledge base document list response."""

    items: list[DocumentSummary]
    total: int = Field(ge=0)


router = APIRouter(prefix="/knowledgebases", tags=["knowledge-bases"])
_UPLOAD_READ_CHUNK_SIZE = 64 * 1024


async def read_upload_file_with_limit(
    upload: UploadFile,
    *,
    max_bytes: int,
    detail: str,
) -> bytes:
    """Read an upload incrementally and fail as soon as it exceeds the limit."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_UPLOAD_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=detail,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _cleanup_replaced_document(
    *,
    knowledge_base_id: str,
    replacement: DocumentRecord,
    receipt: DocumentReceipt,
    repository: KnowledgeBaseRepository,
    graph_service: GraphServiceProtocol,
    vector_service: VectorServiceProtocol,
    object_store: ObjectStore,
    document_status_store: SourceDocumentStatusStore,
) -> None:
    """Remove old derived artifacts after the replacement was safely enqueued."""
    try:
        graph_service.delete_by_source_document(knowledge_base_id, replacement.id)
        vector_service.delete_by_source_document(knowledge_base_id, replacement.id)
        protected_keys: set[str] = (
            {receipt.storage_key} if receipt.storage_key is not None else set()
        )
        prefix = f"knowledgebases/{knowledge_base_id}/documents/{replacement.id}/"
        for key in object_store.list_keys(prefix):
            if key not in protected_keys:
                object_store.delete(key)
        repository.delete_document(knowledge_base_id, replacement.id)
        # Purge the durable status projection row too, so it never outlives
        # the document it describes (an orphaned row would inflate a
        # status-filtered list's `total` past `len(items)`) — mirrors the
        # purge on the DELETE endpoint. A missing row is a no-op.
        document_status_store.delete_by_document(knowledge_base_id, replacement.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clean up replaced document '{replacement.id}'.",
        ) from exc


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
    config: DomainConfig = Depends(get_domain_config),
) -> KnowledgeBase:
    """Create a new knowledge base and publish a creation event.

    The KB is stamped with the active domain name so a later domain swap can
    surface (never block on) a mismatch between the KB and the active pack.
    """
    knowledge_base = KnowledgeBase(
        id=generate_id(),
        name=payload.name,
        description=payload.description,
        created_at=utc_now(),
        domain=config.domain.name,
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
    stores: KbDeletionStores = Depends(get_kb_deletion_stores),
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
    event_bus: EventBus = Depends(get_event_bus),
) -> Response:
    """Cascade-delete a KB across every per-KB durable store + metadata.

    The full step list lives in `api._kb_cleanup.kb_deletion_steps`.
    """
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

    for step_name, deletion in kb_deletion_steps(stores, knowledge_base_id):
        _run(step_name, deletion)

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


@router.get(
    "/{knowledge_base_id}/documents",
    response_model=DocumentListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def list_knowledge_base_documents(
    knowledge_base_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: IngestionStatus | None = Query(default=None, alias="status"),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
    document_status_store: SourceDocumentStatusStore = Depends(
        get_document_status_store
    ),
) -> DocumentListResponse:
    """Return registered documents, enriched with the durable status projection.

    ``status`` filters on the durable projection: documents without a
    projected status row never match a filter.
    """
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

    projection_by_id: dict[str, SourceDocumentStatusRecord]
    if status_filter is not None:
        status_rows, total = document_status_store.list(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
            status=status_filter,
        )
        # Load every registered document once (not per matching row: the
        # object-store repository reloads and re-parses its whole metadata
        # snapshot on each `get_document` call) and index into that dict.
        document_count = hydrated_knowledge_base.document_count
        documents_by_id: dict[str, DocumentRecord] = {}
        if document_count > 0:
            all_documents, _ = repository.list_documents(
                knowledge_base_id, limit=document_count, offset=0
            )
            documents_by_id = {document.id: document for document in all_documents}
        records: list[DocumentRecord] = []
        matched_rows: list[SourceDocumentStatusRecord] = []
        for row in status_rows:
            document = documents_by_id.get(row.source_document_id)
            if document is None:
                # Orphan resurrection race: an in-flight pipeline event can
                # re-create a document's status row AFTER a delete/reupload
                # purge already ran (the row's source_document_id has no
                # matching registered document). Left alone this would
                # permanently inflate a status-filtered `total` past
                # `len(items)`. Reap it opportunistically here and exclude it
                # from both the page and the reported total.
                document_status_store.delete_by_document(
                    knowledge_base_id, row.source_document_id
                )
                total -= 1
                continue
            records.append(document)
            matched_rows.append(row)
        projection_by_id = {row.source_document_id: row for row in matched_rows}
    else:
        records, total = repository.list_documents(
            knowledge_base_id, limit=limit, offset=offset
        )
        projection_by_id = document_status_store.get_many(
            knowledge_base_id=knowledge_base_id,
            source_document_ids=[record.id for record in records],
        )

    items = [
        _document_summary(
            record,
            hydrated_knowledge_base,
            repository,
            projection_by_id.get(record.id),
        )
        for record in records
    ]
    return DocumentListResponse(items=items, total=total)


def _document_summary(
    record: DocumentRecord,
    knowledge_base: KnowledgeBase,
    repository: KnowledgeBaseRepository,
    projection: SourceDocumentStatusRecord | None,
) -> DocumentSummary:
    """Merge the registered-document record with its durable status projection."""
    return DocumentSummary(
        id=record.id,
        knowledge_base_id=record.knowledge_base_id,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        status=document_status_for_knowledge_base(record, knowledge_base, repository),
        created_at=record.created_at,
        warning_count=record.warning_count,
        warning_reasons=record.warning_reasons,
        current_status=(
            projection.current_status.value if projection is not None else None
        ),
        last_error=projection.last_error if projection is not None else None,
        dropped_entity_count=(
            projection.dropped_entity_count if projection is not None else 0
        ),
        dropped_relationship_count=(
            projection.dropped_relationship_count if projection is not None else 0
        ),
        drop_sample_reasons=(
            list(projection.sample_reasons) if projection is not None else []
        ),
    )


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
    document_status_store: SourceDocumentStatusStore = Depends(
        get_document_status_store
    ),
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
    # Purge the durable status projection row too, so it never outlives the
    # document it describes (an orphaned row would inflate a status-filtered
    # list's `total` past `len(items)`).
    document_status_store.delete_by_document(knowledge_base_id, document_id)


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
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
    document_status_store: SourceDocumentStatusStore = Depends(
        get_document_status_store
    ),
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
    raw_metadata: list[tuple[str, str | None, int, str, DocumentRecord | None]] = []
    for upload in files:
        if not validate_content_type(upload.content_type, allowed_content_types):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Content type '{upload.content_type}' not allowed.",
            )

        content = await read_upload_file_with_limit(
            upload,
            max_bytes=max_bytes,
            detail=(
                f"File '{upload.filename or 'upload'}' exceeds the "
                f"configured {validation.max_file_size_mb} MB limit."
            ),
        )

        filename = sanitize_filename(upload.filename or "document")
        content_hash = hashlib.sha256(content).hexdigest()

        # Dedup: identify the document this upload will replace, but defer all
        # destructive cleanup until registration and event publication succeed.
        existing = repository.get_document_by_content_hash(knowledge_base_id, content_hash)

        submissions.append(
            DocumentSubmission(
                filename=filename,
                content=content,
                content_type=upload.content_type,
            )
        )
        raw_metadata.append(
            (filename, upload.content_type, len(content), content_hash, existing)
        )

    correlation_id = generate_id()
    receipts = ingestion_service.register_documents(
        knowledge_base_id, submissions, correlation_id=correlation_id
    )

    # Start a tracked workflow run for this ingestion only when registration
    # actually published documents.uploaded under `correlation_id`, so the
    # worker's tracker can advance the run.
    # start_workflow is create-or-get by correlation, so a worker that already
    # fallback-created the run is adopted rather than duplicated.
    if any(receipt.enqueued for receipt in receipts):
        agent_service.start_workflow(
            WorkflowSubmissionRequest(
                knowledge_base_id=knowledge_base_id,
                trigger_event_type="documents.uploaded",
                requested_steps=default_steps_for_trigger("documents.uploaded"),
                correlation_id=correlation_id,
            )
        )

    final_receipts: list[DocumentReceipt] = []
    for receipt, (filename, content_type, size_bytes, content_hash, replacement) in zip(
        receipts, raw_metadata, strict=True
    ):
        replaced_document_id = replacement.id if replacement is not None else None
        if replacement is not None and receipt.enqueued:
            _cleanup_replaced_document(
                knowledge_base_id=knowledge_base_id,
                replacement=replacement,
                receipt=receipt,
                repository=repository,
                graph_service=graph_service,
                vector_service=vector_service,
                object_store=object_store,
                document_status_store=document_status_store,
            )
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
