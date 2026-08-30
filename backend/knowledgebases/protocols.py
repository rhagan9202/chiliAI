"""Persistence protocol for knowledge base and document metadata."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from knowledgebases.models import DocumentRecord
from shared.types import KnowledgeBase

__all__ = ["KnowledgeBaseRepository"]


@runtime_checkable
class KnowledgeBaseRepository(Protocol):
    """Persistence boundary for knowledge base and document metadata."""

    def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase: ...

    def get(self, knowledge_base_id: str) -> KnowledgeBase | None: ...

    def list(self, *, limit: int, offset: int) -> tuple[list[KnowledgeBase], int]: ...

    def update_summary(
        self,
        knowledge_base_id: str,
        *,
        status: str | None = None,
        entity_count: int | None = None,
        relationship_count: int | None = None,
    ) -> KnowledgeBase | None: ...

    def delete(self, knowledge_base_id: str) -> bool: ...

    def mark_pending_cleanup(self, knowledge_base_id: str) -> None: ...

    def add_document(self, document: DocumentRecord) -> DocumentRecord: ...

    def get_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> DocumentRecord | None: ...

    def list_documents(
        self,
        knowledge_base_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentRecord], int]: ...

    def update_document_status(
        self,
        knowledge_base_id: str,
        document_id: str,
        status: str,
    ) -> DocumentRecord | None: ...

    def set_stage_document_warnings(
        self,
        knowledge_base_id: str,
        document_id: str,
        *,
        stage: str,
        count: int,
        reasons: list[str],
    ) -> DocumentRecord | None:
        """Set one pipeline stage's warning contribution absolutely.

        The document-level ``warning_count`` / ``warning_reasons`` are the
        sum / sampled union across every stage that has written for this
        document (e.g. ``"parse"``, ``"extract"``), not a running counter.
        Absolute per stage rather than additive overall, so replaying the
        handler that owns a stage -- a retry, or an at-least-once Redis
        Streams redelivery -- converges to the same value instead of
        accumulating, while a different stage's contribution is never
        overwritten.

        Returns the updated record, or ``None`` if the knowledge base or the
        document does not exist (a no-op; no document is created as a side
        effect).
        """
        ...

    def delete_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool: ...

    def get_document_by_content_hash(
        self,
        knowledge_base_id: str,
        content_hash: str,
    ) -> DocumentRecord | None: ...
