"""Adapter-level protocol for the durable document status projection (BL-041)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ingestion.models import (
    DocumentStatusTransition,
    IngestionStatus,
    SourceDocumentStatusRecord,
)

__all__ = ["SourceDocumentStatusStore"]


@runtime_checkable
class SourceDocumentStatusStore(Protocol):
    """Persist and query the per-document ingestion status projection.

    ``apply`` is monotonic: a transition only changes ``current_status`` when
    its ``STATUS_RANK`` is strictly greater than the stored rank, so stale or
    redelivered events are no-ops. Drop counts / sample reasons are absolute
    values and overwrite whenever the transition carries them.
    """

    def apply(
        self, transition: DocumentStatusTransition
    ) -> SourceDocumentStatusRecord:
        """Upsert one status observation; return the resulting current row."""
        ...

    def get_many(
        self,
        *,
        knowledge_base_id: str,
        source_document_ids: list[str],
    ) -> dict[str, SourceDocumentStatusRecord]:
        """Return known rows keyed by source_document_id (missing ids omitted)."""
        ...

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
    ) -> tuple[list[SourceDocumentStatusRecord], int]:
        """Return a page of rows (newest first) plus the total match count."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all rows for a knowledge base; return the count removed."""
        ...
