"""In-memory metadata stores for knowledge bases and registered documents.

These stores back the knowledgebases router CRUD endpoints. They live in the
``api`` package because no other module needs them and the router is the sole
consumer; production deployments will swap them for a persistent backend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from shared.types import KnowledgeBase
from shared.utils import utc_now

__all__ = [
    "DocumentRecord",
    "InMemoryKnowledgeBaseRepository",
    "KnowledgeBaseRepository",
]


class DocumentRecord(BaseModel):
    """Metadata recorded for a registered document inside a knowledge base."""

    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str = "registered"
    storage_key: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


@runtime_checkable
class KnowledgeBaseRepository(Protocol):
    """Persistence boundary for knowledge base and document metadata."""

    def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase: ...

    def get(self, knowledge_base_id: str) -> KnowledgeBase | None: ...

    def list(self, *, limit: int, offset: int) -> tuple[list[KnowledgeBase], int]: ...

    def delete(self, knowledge_base_id: str) -> bool: ...

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

    def delete_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool: ...


class InMemoryKnowledgeBaseRepository:
    """Process-local repository for knowledge base and document metadata."""

    def __init__(self) -> None:
        self._knowledge_bases: dict[str, KnowledgeBase] = {}
        self._knowledge_base_order: list[str] = []
        self._documents: dict[str, dict[str, DocumentRecord]] = {}
        self._document_order: dict[str, list[str]] = {}

    def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        if knowledge_base.id in self._knowledge_bases:
            raise ValueError(
                f"Knowledge base id '{knowledge_base.id}' already exists."
            )
        self._knowledge_bases[knowledge_base.id] = knowledge_base
        self._knowledge_base_order.append(knowledge_base.id)
        self._documents[knowledge_base.id] = {}
        self._document_order[knowledge_base.id] = []
        return knowledge_base

    def get(self, knowledge_base_id: str) -> KnowledgeBase | None:
        return self._knowledge_bases.get(knowledge_base_id)

    def list(self, *, limit: int, offset: int) -> tuple[list[KnowledgeBase], int]:
        ordered_ids = self._knowledge_base_order
        page_ids = ordered_ids[offset : offset + limit]
        items = [self._knowledge_bases[kb_id] for kb_id in page_ids]
        return items, len(ordered_ids)

    def delete(self, knowledge_base_id: str) -> bool:
        if knowledge_base_id not in self._knowledge_bases:
            return False
        del self._knowledge_bases[knowledge_base_id]
        self._knowledge_base_order.remove(knowledge_base_id)
        self._documents.pop(knowledge_base_id, None)
        self._document_order.pop(knowledge_base_id, None)
        return True

    def add_document(self, document: DocumentRecord) -> DocumentRecord:
        kb_documents = self._documents.get(document.knowledge_base_id)
        if kb_documents is None:
            raise ValueError(
                f"Knowledge base '{document.knowledge_base_id}' does not exist."
            )
        if document.id in kb_documents:
            raise ValueError(
                f"Document '{document.id}' already exists in knowledge base "
                f"'{document.knowledge_base_id}'."
            )
        kb_documents[document.id] = document
        self._document_order[document.knowledge_base_id].append(document.id)
        return document

    def get_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> DocumentRecord | None:
        kb_documents = self._documents.get(knowledge_base_id)
        if kb_documents is None:
            return None
        return kb_documents.get(document_id)

    def list_documents(
        self,
        knowledge_base_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentRecord], int]:
        ordered_ids = self._document_order.get(knowledge_base_id, [])
        kb_documents = self._documents.get(knowledge_base_id, {})
        page_ids = ordered_ids[offset : offset + limit]
        items = [kb_documents[doc_id] for doc_id in page_ids]
        return items, len(ordered_ids)

    def delete_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool:
        kb_documents = self._documents.get(knowledge_base_id)
        if kb_documents is None or document_id not in kb_documents:
            return False
        del kb_documents[document_id]
        order = self._document_order.get(knowledge_base_id)
        if order is not None and document_id in order:
            order.remove(document_id)
        return True
