# RAG Query Flow: Question → Answer

**Verified against codebase:** 2026-05-28
**Sources:** `rag/service.py`, `rag/protocols.py`, `api/routers/rag.py`, `rag/service_models.py`, `events/types.py`

---

## Overview

The RAG pipeline converts a user question into a grounded answer by embedding the query, retrieving semantically similar context, optionally expanding via the knowledge graph, assembling context, and generating a response via the configured LLM.

---

## Step-by-step

```
1. API: POST /chat/conversations/{conversation_id}/messages
   ├── Payload: ChatMessageCreateRequest {content, include_graph_context, filters}
   ├── Validates content with ValidationConfig.max_rag_question_length
   ├── Resolves knowledge base scope with default_reference_kb_id when configured
   ├── Optional: ?stream=true → returns SSE StreamingResponse

2. RagService.answer(RagQueryRequest) [or stream_answer()]
   │
   ├── _prepare_state(request)
   │     └── Embeds the question text via QueryEmbedderProtocol
   │           Uses EmbeddingsServiceProtocol.embed(EmbedRequest)
   │           Returns RagWorkflowState {query_vector, context_items: []}
   │
   ├── _retrieve_context(state)
   │     └── Calls ContextRetrieverProtocol (backed by VectorServiceProtocol.search)
   │           VectorSearchRequest {knowledge_base_ids, query_vector, top_k=RagConfig.top_k}
   │           Returns list[RetrievedContextItem {record_id, content, score, metadata}]
   │           Stored in state.context_items
   │
   ├── _expand_graph_context(state, request)  [optional]
   │     └── If GraphContextExpanderProtocol is configured AND include_graph_context:
   │           For each RetrievedContextItem with an entity_id:
   │             Calls GraphServiceProtocol.query_neighborhood(kb_id, entity_id, depth=RagConfig.expansion_depth)
   │           Merges neighbor context into state
   │
   ├── _build_generation_request(state, request, graph_context)
   │     └── Assembles system prompt (RagConfig.system_prompt_template or default)
   │         Formats context items as text
   │         Builds GenerateRequest for LlmServiceProtocol
   │
   └── _answer_generator.generate(generation_request) [or stream]
         └── Calls LlmServiceProtocol.generate(GenerateRequest)
               Returns CompletionResponse {content, model_name, provider}
         Returns RagQueryResponse {request_id, knowledge_base_ids, answer: str, provider, model_name, citations: list[RagCitation], graph_summary: str | None}

Note: The chat router wraps the result in RagAnswer {content: str, sources: list[str]} before
returning ChatConversationResponse. "content" maps to RagQueryResponse.answer, "sources" maps to citation record_ids.

3. After generation:
   └── Publishes RagCompletedEvent to EventBus
         event_type: "rag.completed"
         replies: list[RagCompletionReference {kb_id, request_id, provider, model_name, context_item_count, citation_count, answer_length}]
```

---

## Streaming Path

```
POST /chat/conversations/{id}/messages?stream=true
  └── _stream_sse(rag_service, knowledge_base_ids, question)
        └── for chunk in rag_service.stream_answer(RagQueryRequest):
              yield SSE: {"token": chunk.chunk_text, "done": false}
              ...
              yield SSE: {"token": "", "done": true, "sources": [record_id, ...], "citations": [...]}
```

SSE format: `data: {json}\n\n`

---

## Config-driven Behavior

| Config field | Effect |
|-------------|--------|
| `RagConfig.top_k` | Number of vector search results to retrieve |
| `RagConfig.expansion_depth` | Graph neighborhood expansion depth (0 = disabled) |
| `RagConfig.reranking_enabled` | Reranking not yet implemented |
| `RagConfig.system_prompt_template` | Custom system prompt; falls back to built-in default |
| `LlmConfig.provider` | Which LLM adapter generates the answer |
| `EmbeddingsConfig.provider` | Which embedder encodes the query |

---

## Exceptions

| Exception | When raised |
|-----------|------------|
| `RagConfigurationError` | LLM/vector store misconfigured |
| `RagRetrievalError` | Vector search failure |
| `RagGenerationError` | LLM completion failure |

---

## Relevant Source Files

- `backend/rag/service.py` — `RagService` orchestration
- `backend/rag/protocols.py` — `RagServiceProtocol`
- `backend/rag/service_models.py` — `RagQueryRequest`, `RagQueryResponse`, `RagStreamChunk`, `RagAnswer {content, sources}`, `RagCitation`
- `backend/rag/adapters/protocols.py` — inner sub-protocols
- `backend/api/routers/rag.py` — HTTP entry points + SSE streaming
