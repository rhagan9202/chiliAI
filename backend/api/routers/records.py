"""Structured-record ingestion API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from api._kb_busy import KbBusyError, WorkflowBusyTracker, ensure_kb_idle
from api.dependencies import (
    get_agent_service,
    get_domain_config,
    get_knowledge_base_repository,
    get_records_service,
    get_workflow_tracker,
)
from api.middleware.rbac import require_role
from agent.protocols import AgentServiceProtocol
from agent.service_models import WorkflowSubmissionRequest
from agent.workflow_tracking import default_steps_for_trigger
from shared.utils import generate_id
from config.schema import DomainConfig, ValidationConfig
from knowledgebases.protocols import KnowledgeBaseRepository
from records.adapters.sources.file_source import CsvFileSource, JsonlFileSource
from records.exceptions import RecordFeedNotFoundError, RecordPersistenceError, RecordsError
from records.protocols import RecordsServiceProtocol
from records.service_models import RecordIngestReceipt, RecordSubmission

__all__ = ["RecordPushRequest", "router"]

router = APIRouter(prefix="/records", tags=["records"])
_UPLOAD_READ_CHUNK_SIZE = 64 * 1024


class RecordPushRequest(BaseModel):
    """Request payload for the api-push records endpoint."""

    feed_name: str = Field(min_length=1)
    rows: list[dict[str, object]] = Field(min_length=1)


async def _read_upload_file_with_limit(
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


def _select_file_source(
    filename: str,
) -> tuple[CsvFileSource | JsonlFileSource, str]:
    """Return the source parser and its format token for an upload filename."""
    lowered = filename.lower()
    if lowered.endswith(".jsonl"):
        return JsonlFileSource(), "jsonl"
    if lowered.endswith(".csv"):
        return CsvFileSource(), "csv"
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported records file type: '{filename}'. Use .csv or .jsonl.",
    )


def _resolve_feed_formats(config: DomainConfig, feed_name: str) -> list[str] | None:
    """Return a feed's accepted_formats, or None when the feed is not declared."""
    if config.records is None:
        return None
    for feed in config.records.feeds:
        if feed.name == feed_name:
            return feed.accepted_formats
    return None


def _start_records_workflow(
    agent_service: AgentServiceProtocol,
    *,
    knowledge_base_id: str,
    correlation_id: str,
    receipt: RecordIngestReceipt,
) -> None:
    """Start a tracked workflow run when records were actually ingested.

    A duplicate/empty submission publishes no ``records.ingested`` event, so we
    skip it to avoid an orphan run. start_workflow is create-or-get by
    correlation, so a worker that already fallback-created the run is adopted.
    """

    if receipt.duplicate or receipt.accepted_count <= 0:
        return
    agent_service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id=knowledge_base_id,
            trigger_event_type="records.ingested",
            requested_steps=default_steps_for_trigger("records.ingested"),
            correlation_id=correlation_id,
        )
    )


@router.post(
    "/{knowledge_base_id}/files",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecordIngestReceipt,
    dependencies=[Depends(require_role("analyst"))],
)
async def upload_record_file(
    knowledge_base_id: str,
    response: Response,
    feed: str = Form(...),
    file: UploadFile = File(...),
    service: RecordsServiceProtocol = Depends(get_records_service),
    config: DomainConfig = Depends(get_domain_config),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
) -> RecordIngestReceipt:
    """Ingest a CSV or JSONL upload into the named feed."""
    existing_kb = repository.get(knowledge_base_id)
    if existing_kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' was not found.",
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

    filename = file.filename or "upload"
    source, file_format = _select_file_source(filename)
    accepted_formats = _resolve_feed_formats(config, feed)
    if accepted_formats is not None and file_format not in accepted_formats:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Feed '{feed}' does not accept '{file_format}' uploads. "
                f"Accepted formats: {', '.join(accepted_formats)}."
            ),
        )
    validation = config.validation or ValidationConfig()
    content = await _read_upload_file_with_limit(
        file,
        max_bytes=validation.max_file_size_mb * 1024 * 1024,
        detail=f"File exceeds the configured {validation.max_file_size_mb} MB limit.",
    )

    try:
        rows = source.read_rows(content)
        correlation_id = generate_id()
        receipt = service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=feed,
                rows=rows,
                source_type="file_upload",
                source_ref=filename,
            ),
            correlation_id=correlation_id,
        )
        _start_records_workflow(
            agent_service,
            knowledge_base_id=knowledge_base_id,
            correlation_id=correlation_id,
            receipt=receipt,
        )
        if receipt.duplicate:
            response.status_code = status.HTTP_200_OK
        return receipt
    except RecordFeedNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RecordPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Record storage failure.",
        ) from exc
    except RecordsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post(
    "/{knowledge_base_id}/push",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecordIngestReceipt,
    dependencies=[Depends(require_role("analyst"))],
)
async def push_records(
    knowledge_base_id: str,
    payload: RecordPushRequest,
    response: Response,
    service: RecordsServiceProtocol = Depends(get_records_service),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
) -> RecordIngestReceipt:
    """Ingest a JSON array of record rows into the named feed."""
    existing_kb = repository.get(knowledge_base_id)
    if existing_kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' was not found.",
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

    try:
        correlation_id = generate_id()
        receipt = service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=payload.feed_name,
                rows=payload.rows,
                source_type="api_push",
                source_ref=None,
            ),
            correlation_id=correlation_id,
        )
        _start_records_workflow(
            agent_service,
            knowledge_base_id=knowledge_base_id,
            correlation_id=correlation_id,
            receipt=receipt,
        )
        if receipt.duplicate:
            response.status_code = status.HTTP_200_OK
        return receipt
    except RecordFeedNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RecordPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Record storage failure.",
        ) from exc
    except RecordsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
