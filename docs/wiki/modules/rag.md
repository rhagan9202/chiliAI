# Module: rag

**Verified against codebase:** 2026-05-28
**Source:** `backend/rag/`

## Purpose

Retrieval-augmented generation pipeline. Orchestrates: query embedding → vector search → context assembly → optional graph expansion → LLM answer generation. Supports both single-shot and streaming (SSE) responses.

---

## Service Protocol (`rag/protocols.py`)

```python
class RagServiceProtocol(Protocol):
    def answer(self, request: RagQueryRequest) -> RagQueryResponse: ...

    def answer_question(
        self,
        *,
        knowledge_base_ids: list[str],
        question: str,
    ) -> RagAnswer: ...

    def stream_answer(
        self,
        request: RagQueryRequest,
    ) -> Iterator[RagStreamChunk]: ...
```

---

## Service Models (`rag/service_models.py`)

Last verified: 2026-05-28

```python
MetadataValue = str | int | float | bool | None  # from rag/models.py

class RagQueryRequest(BaseModel):
    knowledge_base_ids: list[str] = Field(min_length=1)
    question: str                         # non-empty; enforced by model_validator
    top_k: int = Field(default=5, gt=0)
    include_graph_context: bool = True
    system_prompt: str | None = None
    filters: dict[str, MetadataValue] = {}

class RagCitation(BaseModel):
    record_id: str
    content_id: str
    score: float           # [-1.0, 1.0]
    snippet: str
    document_id: str | None = None
    chunk_index: int | None = None
    highlight: str | None = None

class RagQueryResponse(BaseModel):
    request_id: str
    knowledge_base_ids: list[str]
    answer: str
    provider: str
    model_name: str
    citations: list[RagCitation] = []
    graph_summary: str | None = None

class RagAnswer(BaseModel):
    """Simplified response used by the chat router."""
    content: str
    sources: list[str] = []

class RagStreamChunk(BaseModel):
    """SSE streaming chunk.
    Non-final: chunk_text populated, citations=[].
    Final: is_final=True, chunk_text="", citations=full citation set."""
    chunk_text: str
    is_final: bool
    citations: list[RagCitation] = []
```

---

## Internal Adapter Protocols (`rag/adapters/protocols.py`)

```python
class QueryEmbedderProtocol(Protocol):
    # Embeds the query string → vector

class ContextRetrieverProtocol(Protocol):
    # Vector search → list[RetrievedContextItem]

class GraphContextExpanderProtocol(Protocol):
    # Optional: expands retrieved entities via graph neighborhood query

class AnswerGeneratorProtocol(Protocol):
    # Calls LLM with assembled context → completion
```

---

## `RagService` Constructor

```python
class RagService:
    def __init__(
        self,
        query_embedder: QueryEmbedderProtocol,
        context_retriever: ContextRetrieverProtocol,
        answer_generator: AnswerGeneratorProtocol,
        *,
        event_bus: EventBus,
        graph_context_expander: GraphContextExpanderProtocol | None = None,
        domain_config: DomainConfig | None = None,
    ) -> None: ...
```

`graph_context_expander` is optional — when None, the pipeline skips graph expansion.

---

## Adapters

| Backend | File | Notes |
|---------|------|-------|
| In-memory | `adapters/in_memory.py` | Test/dev stubs for retrieval and generation |

`adapters/protocols.py` defines the inner sub-protocols.

---

## Module Dependencies

- `embeddings/` — `EmbeddingsServiceProtocol` (via QueryEmbedder)
- `vectorstore/` — `VectorServiceProtocol` (via ContextRetriever)
- `graph/` — `GraphServiceProtocol` (via GraphContextExpander)
- `llm/` — `LlmServiceProtocol` (via AnswerGenerator)
- `events/` — publishes `RagCompletedEvent`
- `config/schema.py` — `RagConfig` (top_k, expansion_depth, system_prompt_template)

---

## Tests

Location: `backend/tests/rag/`
