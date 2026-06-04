"""Structured-record ingestion API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from api._kb_busy import KbBusyError, WorkflowBusyTracker, ensure_kb_idle
from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_records_service,
    get_workflow_tracker,
)
from api.middleware.rbac import require_role
from config.schema import DomainConfig, ValidationConfig
from knowledgebases import KnowledgeBaseRepository
from records.adapters.sources.file_source import CsvFileSource, JsonlFileSource
from records.exceptions import RecordFeedNotFoundError, RecordPersistenceError, RecordsError
from records.protocols import RecordsServiceProtocol
from records.service_models import RecordIngestReceipt, RecordSubmission

__all__ = ["RecordPushRequest", "router"]

router = APIRouter(prefix="/records", tags=["records"])


class RecordPushRequest(BaseModel):
    """Request payload for the api-push records endpoint."""

    feed_name: str = Field(min_length=1)
    rows: list[dict[str, object]] = Field(min_length=1)


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
) -> RecordIngestReceipt:
    """Ingest a CSV or JSONL upload into the named feed."""
    existing_kb = repository.get(knowledge_base_id)
    if existing_kb is not None and existing_kb.pending_cleanup:
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
    content = await file.read()

    validation = config.validation or ValidationConfig()
    if len(content) > validation.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the configured {validation.max_file_size_mb} MB limit.",
        )

    try:
        rows = source.read_rows(content)
        receipt = service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=feed,
                rows=rows,
                source_type="file_upload",
                source_ref=filename,
            ),
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
        receipt = service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=payload.feed_name,
                rows=payload.rows,
                source_type="api_push",
                source_ref=None,
            ),
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
