# Module: embeddings

**Verified against codebase:** 2026-05-28
**Source:** `backend/embeddings/`

## Purpose

Embedding generation abstraction. Accepts text items, returns dense vectors. Used by the worker (embeddings pipeline step) and by the RAG pipeline (query embedding).

---

## Service Protocol (`embeddings/protocols.py`)

```python
class EmbeddingsServiceProtocol(Protocol):
    def embed(self, request: EmbedRequest) -> EmbedResponse: ...
```

---

## Service Models (`embeddings/service_models.py`)

### `EmbedSubmission`
```python
class EmbedSubmission(BaseModel):
    content_id: str
    content: str    # must not be empty (validated)
```

### `EmbedRequest`
```python
class EmbedRequest(BaseModel):
    knowledge_base_id: str | None = None
    model_name: str = "in-memory-embedder"
    include_graph_embeddings: bool = False
    require_graph_embeddings: bool = False
    graph_embedding_dimension: int = Field(default=8, gt=0, le=256)
    submissions: list[EmbedSubmission]    # must have >= 1 item (validated)
```

### `EmbedResponse`
```python
class EmbedResponse(BaseModel):
    request_id: str
    model_name: str
    dimensions: int    # > 0
    items: list[EmbeddedItem]
    graph_status: GraphEmbeddingStatus | None = None
```

### `EmbeddedItem`
```python
class EmbeddedItem(BaseModel):
    content_id: str
    vector: list[float]
    channel: EmbeddingChannel = "text"
    model_name: str | None = None
    provider: str | None = None
    dimensions: int | None = None   # defaults to len(vector)
```

---

## Adapters

| Backend | File | Config | Optional extra |
|---------|------|--------|---------------|
| In-memory (deterministic fake) | `adapters/in_memory.py` | `EmbeddingsConfig.provider = "local"` | None |
| OpenAI | `adapters/openai_adapter.py` | `provider = "openai"`, `api_key_env_var` | `[openai]` |
| Sentence Transformers | `adapters/sentence_transformers_adapter.py` | `provider = "sentence_transformers"`, `model` | `[sentence-transformers]` |

Inner adapter protocol: `adapters/protocols.py` (structural subset consumed by the service).

**Default model:** `all-MiniLM-L6-v2` (384 dimensions) with `sentence_transformers` provider.

---

## Configuration Constraint

`EmbeddingsConfig.dimensions` must equal `VectorStoreConfig.dimensions`. Enforced by `DomainConfig._validate_cross_references()` at startup.

---

## Status Note

Current adapter set is verified complete for text embeddings (in-memory, OpenAI, sentence-transformers). Graph embedding request fields are present in the service model; callers can inspect `graph_status` to see whether graph embeddings were produced or skipped.

---

## Module Dependencies

- `config/schema.py` — `EmbeddingsConfig`
- `shared/utils.py` — `generate_id`
- Optional: `openai`, `sentence_transformers`

---

## Tests

Location: `backend/tests/embeddings/`
