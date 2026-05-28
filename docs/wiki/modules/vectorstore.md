# Module: vectorstore

**Verified against codebase:** 2026-05-28
**Source:** `backend/vectorstore/`

## Purpose

Vector store access abstraction. Owns embedding storage and similarity search. Used by the worker (vector indexing step) and by the RAG pipeline (retrieval step).

---

## Service Protocol (`vectorstore/protocols.py`)

```python
class VectorServiceProtocol(Protocol):
    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]: ...
    def search(self, request: VectorSearchRequest) -> VectorSearchResponse: ...
    def batch_search(self, requests: list[VectorSearchRequest]) -> list[VectorSearchResponse]: ...
    def get_record(self, knowledge_base_id: str, record_id: str) -> VectorRecord | None: ...
    def count(self, knowledge_base_id: str) -> int: ...
    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool: ...
    def delete_knowledge_base(self, knowledge_base_id: str) -> VectorDeleteResponse: ...
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> VectorDeleteResponse: ...
```

---

## Service Models (`vectorstore/service_models.py`)

Last verified: 2026-05-22

```python
class VectorIndexSubmission(BaseModel):
    """Single embedding payload submitted to the vectorstore service."""
    content_id: str
    embedding: list[float]               # non-empty; enforced by model_validator
    content: str | None = None
    metadata: dict[str, MetadataValue] = {}   # MetadataValue = str | int | float | bool | None

class VectorIndexRequest(BaseModel):
    knowledge_base_id: str
    submissions: list[VectorIndexSubmission]  # non-empty; enforced by model_validator

class VectorIndexReceipt(BaseModel):
    knowledge_base_id: str
    record_id: str
    content_id: str
    dimension: int          # > 0
    created_at: datetime    # default_factory=utc_now

class VectorAuditArtifact(BaseModel):
    request_id: str
    knowledge_base_id: str
    receipts: list[VectorIndexReceipt] = []
    created_at: datetime
    receipt_count: int      # computed from receipts

class VectorDeleteResponse(BaseModel):
    knowledge_base_id: str
    deleted_count: int      # >= 0
    deleted_at: datetime    # default_factory=utc_now

class VectorSearchRequest(BaseModel):
    knowledge_base_ids: list[str]        # min_length=1; multi-KB search
    query_vector: list[float]            # non-empty; enforced by model_validator
    limit: int = Field(default=5, gt=0)
    filters: dict[str, MetadataValue] = {}

class VectorSearchMatch(BaseModel):
    record_id: str
    content_id: str
    score: float
    content: str | None = None
    metadata: dict[str, MetadataValue] = {}

class VectorSearchResponse(BaseModel):
    knowledge_base_ids: list[str]
    query_dimension: int    # > 0
    matches: list[VectorSearchMatch] = []
```

**Note:** `VectorSearchRequest.knowledge_base_ids` is a list (multi-KB search), not a single string. The Qdrant adapter uses count-before-delete to return an exact `deleted_count` from `delete_by_source_document`. `VectorService.index()` publishes `VectorsIndexedEvent` and persists a `VectorAuditArtifact`; `delete_knowledge_base()` publishes `VectorsDeletedEvent`.

---

## Adapters

| Backend | File | Config |
|---------|------|--------|
| In-memory | `adapters/in_memory.py` | `VectorStoreConfig.backend = "in_memory"` |
| Qdrant | `adapters/qdrant_adapter.py` | `backend = "qdrant"`, `uri` |

Inner adapter protocol: `adapters/protocols.py`.

---

## Configuration

`VectorStoreConfig.dimensions` must match `EmbeddingsConfig.dimensions` (cross-validated at startup).

---

## Module Dependencies

- `config/schema.py` — `VectorStoreConfig`
- `embeddings/` — dimension contract
- Optional: `qdrant-client` (skipped without `[qdrant]` extra)

---

## Tests

Location: `backend/tests/vectorstore/`
Qdrant adapter tests marked `@pytest.mark.integration`.
