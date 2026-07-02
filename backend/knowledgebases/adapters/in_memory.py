"""In-memory knowledge base + document metadata repository."""

from __future__ import annotations

from knowledgebases._helpers import build_knowledge_base_summary_updates
from knowledgebases.models import MAX_DOCUMENT_WARNING_REASONS, DocumentRecord
from shared.types import KnowledgeBase
from shared.utils import utc_now

__all__ = ["InMemoryKnowledgeBaseRepository"]


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

    def update_summary(
        self,
        knowledge_base_id: str,
        *,
        status: str | None = None,
        entity_count: int | None = None,
        relationship_count: int | None = None,
    ) -> KnowledgeBase | None:
        knowledge_base = self._knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            return None
        updates = build_knowledge_base_summary_updates(
            knowledge_base,
            status=status,
            entity_count=entity_count,
            relationship_count=relationship_count,
        )
        if not updates:
            return knowledge_base
        updated = knowledge_base.model_copy(update=updates)
        self._knowledge_bases[knowledge_base_id] = updated
        return updated

    def delete(self, knowledge_base_id: str) -> bool:
        if knowledge_base_id not in self._knowledge_bases:
            return False
        del self._knowledge_bases[knowledge_base_id]
        self._knowledge_base_order.remove(knowledge_base_id)
        self._documents.pop(knowledge_base_id, None)
        self._document_order.pop(knowledge_base_id, None)
        return True

    def mark_pending_cleanup(self, knowledge_base_id: str) -> None:
        """Flag the knowledge base as requiring a cleanup retry."""
        knowledge_base = self._knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            return
        self._knowledge_bases[knowledge_base_id] = knowledge_base.model_copy(
            update={"pending_cleanup": True, "updated_at": utc_now()}
        )

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
        self._sync_document_count(document.knowledge_base_id)
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

    def update_document_status(
        self,
        knowledge_base_id: str,
        document_id: str,
        status: str,
    ) -> DocumentRecord | None:
        kb_documents = self._documents.get(knowledge_base_id)
        if kb_documents is None:
            return None
        document = kb_documents.get(document_id)
        if document is None:
            return None
        if document.status == status:
            return document
        updated = document.model_copy(update={"status": status})
        kb_documents[document_id] = updated
        return updated

    def record_document_warnings(
        self,
        knowledge_base_id: str,
        document_id: str,
        *,
        additional_count: int,
        reasons: list[str],
    ) -> DocumentRecord | None:
        kb_documents = self._documents.get(knowledge_base_id)
        if kb_documents is None:
            return None
        document = kb_documents.get(document_id)
        if document is None:
            return None
        combined_reasons = (document.warning_reasons + reasons)[
            :MAX_DOCUMENT_WARNING_REASONS
        ]
        updated = document.model_copy(
            update={
                "warning_count": document.warning_count + additional_count,
                "warning_reasons": combined_reasons,
            }
        )
        kb_documents[document_id] = updated
        return updated

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
        self._sync_document_count(knowledge_base_id)
        return True

    def get_document_by_content_hash(
        self,
        knowledge_base_id: str,
        content_hash: str,
    ) -> DocumentRecord | None:
        for record in self._documents.get(knowledge_base_id, {}).values():
            if record.content_hash == content_hash:
                return record
        return None

    def _sync_document_count(self, knowledge_base_id: str) -> None:
        """Keep KB summary metadata aligned with registered documents."""

        knowledge_base = self._knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            return
        document_count = len(self._document_order.get(knowledge_base_id, []))
        self._knowledge_bases[knowledge_base_id] = knowledge_base.model_copy(
            update={"document_count": document_count, "updated_at": utc_now()}
        )
