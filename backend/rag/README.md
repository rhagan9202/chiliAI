# rag

Retrieval-augmented answer generation: **query → embed → vector search →
graph expansion → LLM answer**, with citations. `rag/` owns only the
orchestration and its ports; it does not import the embeddings, vectorstore,
graph or LLM modules. The API layer composes those services into the ports
through the bridges in `api/_rag_bridges.py`, which keeps the cross-module
coupling in the gateway (see [docs/architecture.md](../../docs/architecture.md)).

## Layout

| File | Responsibility |
|------|----------------|
| `protocols.py` | `RagServiceProtocol` — `answer`, `answer_question`, `stream_answer`. |
| `adapters/protocols.py` | Ports: `QueryEmbedderProtocol.embed_query`, `ContextRetrieverProtocol.retrieve`, `GraphContextExpanderProtocol.expand`, `AnswerGeneratorProtocol.generate` / `stream_generate`. |
| `adapters/in_memory.py` | `InMemoryQueryEmbedder`, `InMemoryContextRetriever`, `InMemoryGraphContextExpander`, `InMemoryAnswerGenerator`, and a self-contained `InMemoryRagService` for tests. |
| `service.py` | `RagService` and `create_rag_service` — runs the pipeline, builds citations, resolves the system prompt, publishes `rag.completed`. |
| `models.py` | Internal models: `ContextRecord`, `RetrievedContextItem`, `GraphContext` / `GraphContextNode` / `GraphContextEdge`, `RagGenerationRequest`, `RagGenerationResult`, `RagWorkflowState`. |
| `service_models.py` | Boundary models: `RagQueryRequest` (`knowledge_base_ids` min length 1, non-empty `question`, `top_k` default 5, `include_graph_context` default true, optional `system_prompt`, `filters`), `RagQueryResponse`, `RagCitation`, `RagAnswer`, `RagStreamChunk`. |
| `exceptions.py` | `RagError` → `RagConfigurationError`, `RagRetrievalError`, `RagGenerationError`. |

## Behaviour and invariants

- **Error mapping.** A `ValueError` from any port becomes
  `RagConfigurationError`; any other exception becomes `RagRetrievalError`
  (embedding, retrieval, graph expansion) or `RagGenerationError` (generation).
  A graph-expansion failure fails the request.
- **Graph expansion** runs only when `include_graph_context` is true and an
  expander was supplied; `answer_question` always disables it.
- **System prompt precedence:** `RagQueryRequest.system_prompt`, else
  `DomainConfig.rag.system_prompt_template` rendered with `{domain_name}` and
  `{entity_types}` (unknown placeholders are left as-is; a malformed template is
  used raw), else `None` (the answer generator applies its own default).
- **Citations** are ordered by descending score (ties keep retrieval order);
  `document_id`, `chunk_index` and `highlight` (falling back to `text`) come
  from match metadata; snippets are whitespace-normalized and capped at 160
  characters.
- **Streaming.** `stream_answer` yields text chunks with `is_final=False`, then
  one final chunk with empty text and the full citation set. It does not
  publish `rag.completed`; `answer` does.
- **Retrieval channel.** `ServiceContextRetriever` (in `api/_rag_bridges.py`)
  always adds `EMBEDDING_CHANNEL_KEY = EMBEDDING_CHANNEL_TEXT` from
  `shared.provenance` to the search filters.

## How it is reached

- **API**: `get_rag_service()` in `api/dependencies.py` builds `RagService`
  from `ServiceQueryEmbedder`, `ServiceContextRetriever`,
  `ServiceAnswerGenerator` and `ServiceGraphContextExpander`.
  `api/routers/rag.py` (prefix `/chat`) calls it from
  `POST /chat/conversations/{conversation_id}/messages` — `?stream=true`
  streams SSE via `stream_answer`; otherwise the conversation append in
  `api/dependencies.py` calls `answer`. Both pass the KB list from
  `shared.kb_scope.resolve_kb_scope`.
- **Workflows**: `workflow_definitions/rag_adapter.py` calls `answer`.
- **Events**: publishes `RagCompletedEvent` (`rag.completed`, see
  [docs/ledger/event-catalog.md](../../docs/ledger/event-catalog.md)). No
  backend module consumes it.

## Persistence

None. Conversation history is persisted by
[conversations/](../conversations/README.md).

## Current gaps

- **Single-KB retrieval.** `RagQueryRequest` accepts several KB ids, but
  embedding, retrieval, graph expansion, generation and the completion event
  all use `knowledge_base_ids[0]`. A reference KB added by `resolve_kb_scope`
  is echoed in the response but not searched.
- `TODO(production)` in `service.py`: no retry/backoff, per-stage timeouts,
  caching, graceful degradation when graph expansion fails, or circuit breaker.
- `TODO(production)` in `adapters/protocols.py`: retrieval has no `min_score`,
  pagination, hybrid search, reranking or timeout; expansion has no configurable
  depth or type filters; generation has no token-budget parameter.

## Tests

`tests/rag/` — `test_service.py`, `test_models.py`, `test_in_memory_adapter.py`,
and bridge tests for the API adapters (`test_embeddings_bridge.py`,
`test_vectorstore_bridge.py`, `test_graph_bridge.py`, `test_llm_bridge.py`).
