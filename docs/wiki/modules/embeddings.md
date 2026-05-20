# Module: embeddings

**Verified against codebase:** 2026-05-20
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
    submissions: list[EmbedSubmission]    # must have >= 1 item (validated)
```

### `EmbedResponse`
```python
class EmbedResponse(BaseModel):
    request_id: str
    model_name: str
    dimensions: int    # > 0
    items: list[EmbeddedItem]
```

### `EmbeddedItem`
```python
class EmbeddedItem(BaseModel):
    content_id: str
    vector: list[float]
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

Embeddings 1.0 implementation plan is in-flight (`docs/` planning artifacts). Current adapter set is verified complete (in_memory, openai, sentence_transformers).

---

## Module Dependencies

- `config/schema.py` — `EmbeddingsConfig`
- `shared/utils.py` — `generate_id`
- Optional: `openai`, `sentence_transformers`

---

## Tests

Location: `backend/tests/embeddings/`
