"""Structured-record ingestion API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from api.dependencies import get_domain_config, get_records_service
from api.middleware.rbac import require_role
from config.schema import DomainConfig, ValidationConfig
from records.adapters.sources.file_source import CsvFileSource, JsonlFileSource
from records.exceptions import RecordFeedNotFoundError, RecordsError
from records.protocols import RecordsServiceProtocol
from records.service_models import RecordIngestReceipt, RecordSubmission

__all__ = ["RecordPushRequest", "router"]

router = APIRouter(prefix="/records", tags=["records"])


class RecordPushRequest(BaseModel):
    """Request payload for the api-push records endpoint."""

    feed_name: str = Field(min_length=1)
    rows: list[dict[str, object]] = Field(min_length=1)


def _select_file_source(filename: str) -> CsvFileSource | JsonlFileSource:
    lowered = filename.lower()
    if lowered.endswith((".jsonl", ".json")):
        return JsonlFileSource()
    if lowered.endswith(".csv"):
        return CsvFileSource()
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported records file type: '{filename}'. Use .csv or .jsonl.",
    )


@router.post(
    "/{knowledge_base_id}/files",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecordIngestReceipt,
    dependencies=[Depends(require_role("analyst"))],
)
async def upload_record_file(
    knowledge_base_id: str,
    feed: str = Form(...),
    file: UploadFile = File(...),
    service: RecordsServiceProtocol = Depends(get_records_service),
    config: DomainConfig = Depends(get_domain_config),
) -> RecordIngestReceipt:
    """Ingest a CSV or JSONL upload into the named feed."""
    filename = file.filename or "upload"
    source = _select_file_source(filename)
    content = await file.read()

    validation = config.validation or ValidationConfig()
    if len(content) > validation.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the configured {validation.max_file_size_mb} MB limit.",
        )

    try:
        rows = source.read_rows(content)
        return service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=feed,
                rows=rows,
                source_type="file_upload",
                source_ref=filename,
            ),
        )
    except RecordFeedNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RecordsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
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
    service: RecordsServiceProtocol = Depends(get_records_service),
) -> RecordIngestReceipt:
    """Ingest a JSON array of record rows into the named feed."""
    try:
        return service.register_records(
            knowledge_base_id,
            RecordSubmission(
                feed_name=payload.feed_name,
                rows=payload.rows,
                source_type="api_push",
                source_ref=None,
            ),
        )
    except RecordFeedNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RecordsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
