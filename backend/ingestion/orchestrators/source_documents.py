"""Pure helpers for SourceDocument lifecycle transitions."""

from __future__ import annotations

from datetime import datetime, timezone

from ingestion.models import IngestionStatus, ParsedDocument, SourceDocument

__all__ = ["enrich_source_document", "mark_failed", "mark_parsed", "mark_parsing"]


def mark_parsing(source: SourceDocument) -> SourceDocument:
    """Return a copy of the source document marked as parsing."""
    return source.model_copy(
        update={
            "status": IngestionStatus.PARSING,
            "error_detail": None,
        }
    )


def mark_parsed(source: SourceDocument, parsed_document: ParsedDocument) -> SourceDocument:
    """Return a copy of the source document marked as parsed."""
    metadata = dict(source.metadata)
    metadata.update(
        {
            "parser_name": parsed_document.parser_name,
            "parser_version": parsed_document.parser_version,
        }
    )
    return source.model_copy(
        update={
            "status": IngestionStatus.PARSED,
            "processed_at": parsed_document.parsed_at,
            "metadata": metadata,
        }
    )


def mark_failed(source: SourceDocument, error_message: str) -> SourceDocument:
    """Return a copy of the source document marked as failed."""
    return source.model_copy(
        update={
            "status": IngestionStatus.FAILED,
            "error_detail": error_message,
            "processed_at": datetime.now(timezone.utc),
        }
    )


def enrich_source_document(
    source: SourceDocument,
    *,
    document_format: object | None = None,
    filename: str | None = None,
    media_type: str | None = None,
    size_bytes: int | None = None,
    uri: str | None = None,
) -> SourceDocument:
    """Return a source copy enriched with transport metadata when provided."""
    updates: dict[str, object] = {}
    if document_format is not None:
        updates["document_format"] = document_format
    if filename is not None:
        updates["filename"] = filename
    if media_type is not None:
        updates["media_type"] = media_type
    if size_bytes is not None:
        updates["size_bytes"] = size_bytes
    if uri is not None:
        updates["uri"] = uri
    if not updates:
        return source
    return source.model_copy(update=updates)