# Module: vectorstore

**Verified against codebase:** 2026-05-20
**Source:** `backend/vectorstore/`

## Purpose

Vector store access abstraction. Owns embedding storage and similarity search. Used by the worker (vector indexing step) and by the RAG pipeline (retrieval step).

---

## Service Protocol (`vectorstore/protocols.py`)

```python
class VectorServiceProtocol(Protocol):
    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]: ...
    def search(self, request: VectorSearchRequest) -> VectorSearchResponse: ...
```

---

## Service Models (`vectorstore/service_models.py`)

Last verified: 2026-05-20

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

class VectorSearchRequest(BaseModel):
    knowledge_base_id: str
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
    knowledge_base_id: str
    query_dimension: int    # > 0
    matches: list[VectorSearchMatch] = []
```

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
