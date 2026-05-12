"""Metadata stores for knowledge bases and registered documents.

These stores back the knowledgebases router CRUD endpoints. They live in the
``api`` package because the FastAPI gateway owns this lightweight metadata
projection. Graph contents, vectors, and raw artifacts remain owned by their
respective modules behind their own protocols.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from shared.types import KnowledgeBase
from shared.utils import utc_now
from storage.protocols import ObjectStore

__all__ = [
    "DocumentRecord",
    "InMemoryKnowledgeBaseRepository",
    "KnowledgeBaseRepository",
    "ObjectStoreKnowledgeBaseRepository",
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


class _KnowledgeBaseStoreSnapshot(BaseModel):
    """Serialized repository state for durable object-store persistence."""

    knowledge_bases: dict[str, KnowledgeBase] = Field(default_factory=dict)
    knowledge_base_order: list[str] = Field(default_factory=list)
    documents: dict[str, dict[str, DocumentRecord]] = Field(default_factory=dict)
    document_order: dict[str, list[str]] = Field(default_factory=dict)


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
        updates = _build_knowledge_base_summary_updates(
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

    def _sync_document_count(self, knowledge_base_id: str) -> None:
        """Keep KB summary metadata aligned with registered documents."""

        knowledge_base = self._knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            return
        document_count = len(self._document_order.get(knowledge_base_id, []))
        self._knowledge_bases[knowledge_base_id] = knowledge_base.model_copy(
            update={"document_count": document_count, "updated_at": utc_now()}
        )


class ObjectStoreKnowledgeBaseRepository:
    """Durable KB metadata repository backed by the configured object store.

    The repository writes a compact JSON snapshot through ``ObjectStore`` so the
    API process can restart without losing KB/document inventory state. This is
    intentionally adapter-independent and suitable for local/dev deployments
    where the API is the single metadata writer. A high-concurrency production
    metadata store can implement the same ``KnowledgeBaseRepository`` protocol
    later without changing routers or frontend contracts.
    """

    _DEFAULT_KEY = "system/knowledgebases/metadata.json"

    def __init__(
        self,
        object_store: ObjectStore,
        *,
        storage_key: str = _DEFAULT_KEY,
    ) -> None:
        self._object_store = object_store
        self._storage_key = storage_key

    def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        snapshot = self._load_snapshot()
        if knowledge_base.id in snapshot.knowledge_bases:
            raise ValueError(
                f"Knowledge base id '{knowledge_base.id}' already exists."
            )
        snapshot.knowledge_bases[knowledge_base.id] = knowledge_base
        snapshot.knowledge_base_order.append(knowledge_base.id)
        snapshot.documents[knowledge_base.id] = {}
        snapshot.document_order[knowledge_base.id] = []
        self._save_snapshot(snapshot)
        return knowledge_base

    def get(self, knowledge_base_id: str) -> KnowledgeBase | None:
        return self._load_snapshot().knowledge_bases.get(knowledge_base_id)

    def list(self, *, limit: int, offset: int) -> tuple[list[KnowledgeBase], int]:
        snapshot = self._load_snapshot()
        ordered_ids = snapshot.knowledge_base_order
        page_ids = ordered_ids[offset : offset + limit]
        items = [snapshot.knowledge_bases[kb_id] for kb_id in page_ids]
        return items, len(ordered_ids)

    def update_summary(
        self,
        knowledge_base_id: str,
        *,
        status: str | None = None,
        entity_count: int | None = None,
        relationship_count: int | None = None,
    ) -> KnowledgeBase | None:
        snapshot = self._load_snapshot()
        knowledge_base = snapshot.knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            return None
        updates = _build_knowledge_base_summary_updates(
            knowledge_base,
            status=status,
            entity_count=entity_count,
            relationship_count=relationship_count,
        )
        if not updates:
            return knowledge_base
        updated = knowledge_base.model_copy(update=updates)
        snapshot.knowledge_bases[knowledge_base_id] = updated
        self._save_snapshot(snapshot)
        return updated

    def delete(self, knowledge_base_id: str) -> bool:
        snapshot = self._load_snapshot()
        if knowledge_base_id not in snapshot.knowledge_bases:
            return False
        del snapshot.knowledge_bases[knowledge_base_id]
        snapshot.knowledge_base_order.remove(knowledge_base_id)
        snapshot.documents.pop(knowledge_base_id, None)
        snapshot.document_order.pop(knowledge_base_id, None)
        self._save_snapshot(snapshot)
        return True

    def add_document(self, document: DocumentRecord) -> DocumentRecord:
        snapshot = self._load_snapshot()
        kb_documents = snapshot.documents.get(document.knowledge_base_id)
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
        snapshot.document_order[document.knowledge_base_id].append(document.id)
        self._sync_document_count(snapshot, document.knowledge_base_id)
        self._save_snapshot(snapshot)
        return document

    def get_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> DocumentRecord | None:
        kb_documents = self._load_snapshot().documents.get(knowledge_base_id)
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
        snapshot = self._load_snapshot()
        ordered_ids = snapshot.document_order.get(knowledge_base_id, [])
        kb_documents = snapshot.documents.get(knowledge_base_id, {})
        page_ids = ordered_ids[offset : offset + limit]
        items = [kb_documents[doc_id] for doc_id in page_ids]
        return items, len(ordered_ids)

    def update_document_status(
        self,
        knowledge_base_id: str,
        document_id: str,
        status: str,
    ) -> DocumentRecord | None:
        snapshot = self._load_snapshot()
        kb_documents = snapshot.documents.get(knowledge_base_id)
        if kb_documents is None:
            return None
        document = kb_documents.get(document_id)
        if document is None:
            return None
        if document.status == status:
            return document
        updated = document.model_copy(update={"status": status})
        kb_documents[document_id] = updated
        self._save_snapshot(snapshot)
        return updated

    def delete_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool:
        snapshot = self._load_snapshot()
        kb_documents = snapshot.documents.get(knowledge_base_id)
        if kb_documents is None or document_id not in kb_documents:
            return False
        del kb_documents[document_id]
        order = snapshot.document_order.get(knowledge_base_id)
        if order is not None and document_id in order:
            order.remove(document_id)
        self._sync_document_count(snapshot, knowledge_base_id)
        self._save_snapshot(snapshot)
        return True

    def _load_snapshot(self) -> _KnowledgeBaseStoreSnapshot:
        if not self._object_store.exists(self._storage_key):
            return _KnowledgeBaseStoreSnapshot()

        stored = self._object_store.get_bytes(self._storage_key)
        return _KnowledgeBaseStoreSnapshot.model_validate_json(stored.content)

    def _save_snapshot(self, snapshot: _KnowledgeBaseStoreSnapshot) -> None:
        content = snapshot.model_dump_json().encode("utf-8")
        self._object_store.put_bytes(
            self._storage_key,
            content,
            media_type="application/json",
            metadata={"record_type": "knowledge_base_metadata"},
        )

    @staticmethod
    def _sync_document_count(
        snapshot: _KnowledgeBaseStoreSnapshot,
        knowledge_base_id: str,
    ) -> None:
        knowledge_base = snapshot.knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            return
        document_count = len(snapshot.document_order.get(knowledge_base_id, []))
        snapshot.knowledge_bases[knowledge_base_id] = knowledge_base.model_copy(
            update={"document_count": document_count, "updated_at": utc_now()}
        )


def _build_knowledge_base_summary_updates(
    knowledge_base: KnowledgeBase,
    *,
    status: str | None,
    entity_count: int | None,
    relationship_count: int | None,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    if status is not None and knowledge_base.status != status:
        updates["status"] = status
    if entity_count is not None and knowledge_base.entity_count != entity_count:
        updates["entity_count"] = entity_count
    if (
        relationship_count is not None
        and knowledge_base.relationship_count != relationship_count
    ):
        updates["relationship_count"] = relationship_count
    if updates:
        updates["updated_at"] = utc_now()
    return updates
