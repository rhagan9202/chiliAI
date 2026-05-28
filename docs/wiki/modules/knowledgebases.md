# Module: knowledgebases

**Verified against codebase:** 2026-05-28
**Source:** `backend/knowledgebases/`

## Purpose

Knowledge base and document metadata persistence. This module owns the `KnowledgeBaseRepository` protocol and its current adapters so `api/` and `agent/` can share KB metadata without importing from each other.

---

## Public Surface

### `knowledgebases/models.py`

```python
class DocumentRecord(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    status: str = "registered"
    storage_key: str | None = None
    content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
```

`KnowledgeBase` itself remains the shared runtime type in `shared/types.py`.

### `knowledgebases/protocols.py`

```python
class KnowledgeBaseRepository(Protocol):
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
    def get_document(self, knowledge_base_id: str, document_id: str) -> DocumentRecord | None: ...
    def list_documents(self, knowledge_base_id: str, *, limit: int, offset: int) -> tuple[list[DocumentRecord], int]: ...
    def update_document_status(self, knowledge_base_id: str, document_id: str, status: str) -> DocumentRecord | None: ...
    def delete_document(self, knowledge_base_id: str, document_id: str) -> bool: ...
    def get_document_by_content_hash(self, knowledge_base_id: str, content_hash: str) -> DocumentRecord | None: ...
```

---

## Adapters

| Backend | Class | Selection |
|---------|-------|-----------|
| In-memory | `adapters/in_memory.py::InMemoryKnowledgeBaseRepository` | Default; `CHILI_KB_REPOSITORY_BACKEND=in_memory` or `memory` |
| Object store | `adapters/object_store.py::ObjectStoreKnowledgeBaseRepository` | `CHILI_KB_REPOSITORY_BACKEND=object_store` / `object-store` / `objectstore` |

The object-store adapter writes one JSON snapshot at `system/knowledgebases/metadata.json` through `storage.protocols.ObjectStore`. It is suitable for local/dev single-writer metadata durability; the code notes that a high-concurrency production store can implement the same protocol later.

---

## Module Dependencies

- `shared/types.py` — `KnowledgeBase`
- `shared/utils.py` — `utc_now`
- `storage/protocols.py` — `ObjectStore` for the object-store adapter

---

## Tests

Location: `backend/tests/knowledgebases/` plus API integration coverage in `backend/tests/api/test_kb_store.py` and `backend/tests/api/test_knowledgebases_router.py`.
