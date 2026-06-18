# rag backlog

> **Scope:** Query → embed → search → graph-expand → LLM pipeline, citations, conversation history, streaming, reranking, hybrid retrieval, evals, multi-KB.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story rag.01: Wire live RagService into the API and retire the seeded InMemoryRagService fallback

**ID:** rag.01
**Status:** planned
**Prerequisites:** [vectorstore.01, embeddings.01, llm.01, graph.01, api.29]
**Unblocks:** [_plugins.01, analytics.16, llm.07, rag.02, rag.03, rag.04, rag.05, rag.06, rag.08, rag.09, rag.10, rag.11, rag.12, rag.13, rag.14, rag.16]
**Estimated size:** L

**As a** chiliAI analyst,
**I need** the RAG chat endpoint to call the real embeddings/vectorstore/graph/LLM services rather than the deterministic in-memory seed,
**so that** answers reflect ingested data and configured providers instead of the canned `"Answer based on N context items: <question>"` echo.

### Current State
- `get_rag_service()` in `backend/api/dependencies.py` composes the live embeddings -> vectorstore -> graph -> LLM pipeline through `ServiceQueryEmbedder`, `ServiceContextRetriever`, `ServiceGraphContextExpander`, and `ServiceAnswerGenerator`.
- `api.app.create_app()` injects that live service into `ApiState` when composition succeeds.
- `ApiState` still falls back to the seeded in-memory RAG pipeline when constructed without DI or when live composition fails.
- `ServiceContextRetriever` forwards a flat scalar `filters` dict and forces `embedding_channel="text"` before calling vector search.
- The seeded context builder remains for the fallback/test path.

### Acceptance Criteria
- [x] New `get_rag_service()` DI factory added to `backend/api/dependencies.py` that composes `ServiceQueryEmbedder`, `ServiceContextRetriever`, `ServiceGraphContextExpander`, `ServiceAnswerGenerator` against the configured `EmbeddingsServiceProtocol`, `VectorServiceProtocol`, graph neighborhood service, and `LlmServiceProtocol`.
- [ ] `ApiState.__init__` keeps `InMemory*` adapters only as an explicit fallback/test path, and production startup fails loudly instead of silently falling back when live RAG composition fails.
- [ ] `InMemoryRagService` and the four `InMemory*` RAG adapters are kept only for tests (no production import); a lint or boundary test asserts they are not imported under `backend/api/`.
- [x] Chat routes use the `ApiState.rag_service` injected by `create_app()` when live composition succeeds.
- [ ] `_build_context_records` (`backend/api/state.py:830-846`) is deleted or moved to a test-only fixture.
- [ ] An integration test (skipped without `[neo4j,qdrant,openai]` extras) demonstrates an end-to-end answer that includes a citation pointing at an ingested document.

### Verification
- `pytest backend/tests/rag backend/tests/api/test_rag_router.py --cov=rag --cov=api -q` — coverage ≥ 85% on `backend/rag/` and the new wiring in `backend/api/`.
- `pyright backend/api/dependencies.py backend/api/state.py backend/api/_rag_bridges.py backend/rag/` clean.
- Manual: `docker compose -f docker-compose.dev.yaml up --build`, ingest a fixture document, POST a chat message, observe answer text that is not the seeded echo.
- `rg --files-with-matches 'InMemoryRagService|InMemoryAnswerGenerator' backend/api/` returns nothing.

### Code touch points
- `backend/api/dependencies.py` (modify — add `get_rag_service` factory)
- `backend/api/state.py` (modify — call factory, drop seeded adapters and seed records)
- `backend/api/_rag_bridges.py` (modify — register as the canonical production composition)
- `backend/rag/adapters/in_memory.py` (modify — restrict to test surface or move to a `tests/fakes` module)
- `backend/tests/rag/test_rag_service_live.py` (new)
- `backend/tests/api/test_rag_router.py` (modify)

---

## Story rag.02: Fan retrieval, embedding, and graph expansion across the full KB scope

**ID:** rag.02
**Status:** planned
**Prerequisites:** [rag.01, vectorstore.02, embeddings.02, graph.02, events.02]
**Unblocks:** []
**Estimated size:** L

**As a** chiliAI analyst running queries that span the transactional KB and a reference (policy) KB,
**I need** retrieval, embedding, and graph expansion to consider all KBs in `knowledge_base_ids`,
**so that** the dual-graph contract (`docs/architecture.md:810`) holds and the reference KB isn't silently dropped at `_prepare_state`.

### Current State
- `RagService._prepare_state` picks `primary_kb_id = request.knowledge_base_ids[0]` and embeds + retrieves against only that KB (`backend/rag/service.py:130-149`).
- `_build_generation_request` passes the same scalar to the generator (`backend/rag/service.py:166-173`).
- `_expand_graph_context` passes `state.knowledge_base_ids[0]` only (`backend/rag/service.py:199-202`).
- `_publish_completed_event` flattens to `response.knowledge_base_ids[0]` on the event reference (`backend/rag/service.py:217-228`).
- `VectorSearchRequest` already accepts `knowledge_base_ids: list[...]`, but `ServiceContextRetriever` still wraps one scalar `knowledge_base_id` into a single-item list, so retrieval has not adopted the native multi-KB path.
- The chat dependency resolves the conversation KB scope before calling RAG, but the RAG service still projects to the first KB internally.

### Acceptance Criteria
- [ ] `ContextRetrieverProtocol.retrieve` / `ServiceContextRetriever.retrieve` accept the full `knowledge_base_ids` list and call the vector service once with the multi-KB request (no per-KB Python fan-out unless required by adapter limits).
- [ ] `QueryEmbedderProtocol.embed_query` either accepts `knowledge_base_ids: list[str]` or callers fan out per KB and cache embeddings keyed by `(kb_id, model)` to avoid re-embedding the same question for KBs sharing a model.
- [ ] `GraphContextExpanderProtocol.expand` fans out per KB and returns a merged `GraphContext` (or, when graph adapters cannot cross KB boundaries, one `GraphContext` per KB with KB attribution preserved).
- [ ] `RagCompletionReference` (or `RagCompletedEvent.replies`) is updated to carry one reference per KB or to carry `knowledge_base_ids: list[str]`; existing consumers in `backend/monitoring/` and `backend/analytics/` are updated accordingly.
- [ ] Citations carry the originating `knowledge_base_id` so multi-KB attribution is visible in `RagQueryResponse.citations[*]`.
- [ ] Decision on the fan-out strategy (one call with multi-KB list vs. one per KB with RRF fuse) is documented in `backend/rag/README.md` and cited from `docs/architecture.md`.

### Verification
- `pytest backend/tests/rag/test_multi_kb_scope.py -q` covers (a) two-KB query returns citations from both KBs, (b) reference KB is not silently dropped, (c) `RagCompletedEvent` retains both KB ids.
- `pytest backend/tests/events/test_rag_completed_event.py -q` reflects the new shape.
- `pyright backend/rag backend/api/_rag_bridges.py` clean.
- Manual: send a chat message with `knowledge_base_ids=[primary, policy]` against a seeded fixture; observe citations from both KBs in the response payload.

### Code touch points
- `backend/rag/service.py` (modify — remove all `knowledge_base_ids[0]` projections)
- `backend/rag/adapters/protocols.py` (modify — protocol signatures accept list or document fan-out)
- `backend/rag/adapters/in_memory.py` (modify)
- `backend/api/_rag_bridges.py` (modify — `ServiceQueryEmbedder`, `ServiceContextRetriever`, `ServiceGraphContextExpander`)
- `backend/events/types.py` (modify — `RagCompletionReference`)
- `backend/rag/service_models.py` (modify — `RagCitation.knowledge_base_id`)
- `backend/rag/README.md` (modify)

---

## Story rag.03: Drive top_k, expansion_depth, and reranking_enabled from RagConfig

**ID:** rag.03
**Status:** planned
**Prerequisites:** [rag.01, config.01]
**Unblocks:** [rag.07]
**Estimated size:** M

**As a** chiliAI domain operator tuning retrieval for Medicare vs. food-supply,
**I need** `RagConfig` (`top_k`, `expansion_depth`, `reranking_enabled`) to actually drive RAG behavior,
**so that** I can configure retrieval breadth and graph depth per domain via YAML without code edits.

### Current State
- `RagConfig` (`backend/config/schema.py:205-211`) declares `top_k: int = 5`, `expansion_depth: int = 2`, `reranking_enabled: bool = False`.
- `RagQueryRequest.top_k` defaults to 5 in the request model itself (`backend/rag/service_models.py:27`) — `RagService` never reads `domain_config.rag.top_k`.
- `ServiceGraphContextExpander.__init__(depth=1)` is constructed with a literal at `backend/api/_rag_bridges.py:152-157`; nothing else consumes the depth concept.
- `reranking_enabled` is referenced in `backend/config/defaults/medicare_fraud.yaml:159-162` and the schema; zero code paths inspect it.

### Acceptance Criteria
- [ ] `RagService` (or the DI factory from `rag.01`) reads `domain_config.rag.top_k`, `expansion_depth`, `reranking_enabled` at request time and applies them when the request omits an override.
- [ ] Explicit `RagQueryRequest.top_k` overrides config; explicit `expansion_depth` (added to the request model) overrides config; otherwise config wins.
- [ ] `ServiceGraphContextExpander` receives its `depth` from config-driven DI instead of the literal `depth=1`.
- [ ] `RagConfig.reranking_enabled` toggles whether the reranker stage runs once `rag.07` lands — story includes a feature-flag check that no-ops the stage today.
- [ ] Tests cover (a) request-set overrides config, (b) config-only path applies when request omits values, (c) absent `RagConfig` falls back to the existing defaults.

### Verification
- `pytest backend/tests/rag/test_config_driven.py -q`
- `pytest backend/tests/config/test_schema.py -q`
- `pyright backend/rag backend/config backend/api/_rag_bridges.py` clean.
- Manual: change `top_k: 12` in `backend/config/defaults/medicare_fraud.yaml`, restart the API, send a chat message, observe 12 citations in the response.

### Code touch points
- `backend/rag/service.py` (modify)
- `backend/rag/service_models.py` (modify — add `expansion_depth: int | None`)
- `backend/api/_rag_bridges.py` (modify — `ServiceGraphContextExpander` config-driven)
- `backend/api/dependencies.py` (modify — wire `domain_config.rag` into the factory)
- `backend/tests/rag/test_config_driven.py` (new)

---

## Story rag.04: AnswerCitationProtocol — emit only the passages the LLM actually used

**ID:** rag.04
**Status:** planned
**Prerequisites:** [rag.01, llm.02]
**Unblocks:** []
**Estimated size:** L

**As a** chiliAI analyst reading a chat answer,
**I need** the citation chips to point only at passages the answer actually referenced (not the full retrieval set),
**so that** "supporting evidence" claims are truthful and reviewers can trust the citation chain.

### Current State
- `_build_citations` (`backend/rag/service.py:253-256`) sorts every retrieved item by descending score and returns all of them as `RagCitation`s.
- Items truncated out of the prompt by `_fit_context_to_budget` (`backend/api/_rag_bridges.py:334-375`) still appear as citations.
- The frontend chat bubble (`chili_app/src/pages/RagChatPage.tsx:146-152`) renders every `citation_id` regardless of whether the answer text references it.
- Prompt assembly at `backend/api/_rag_bridges.py:312-331` interpolates context items without any `[n]` marker convention the model could echo.

### Acceptance Criteria
- [ ] New `AnswerCitationProtocol` (`backend/rag/adapters/protocols.py`) with method `extract(question, answer, retrieved_items) -> CitationResult` returning `cited_record_ids: list[str]`.
- [ ] At least one in-tree adapter: `MarkerCitationExtractor` (parses `[1]`, `[2]` markers the LLM emits) — prompt template updated at `backend/api/_rag_bridges.py:312-331` to instruct the model to cite passages.
- [ ] Optional second adapter (`LlmJudgeCitationExtractor`) is sketched in the same protocol but may be deferred to a later story; the protocol is forward-compatible.
- [ ] `RagQueryResponse` distinguishes `retrieved_record_ids` (informational) from `cited_record_ids` (chips); `RagCitation` adds a `cited: bool` field.
- [ ] Frontend `RagChatPage.tsx:146-152` renders only `cited: true` citations as chips; non-cited retrieved items go behind a "show retrieval set" disclosure.
- [ ] Decision on extractor strategy (marker vs. JSON-mode vs. judge LLM) documented in `backend/rag/README.md`.

### Verification
- `pytest backend/tests/rag/test_citation_extractor.py -q` — coverage ≥ 85%.
- `npm --prefix chili_app run test -- src/pages/RagChatPage` (Vitest) covers the chip filtering logic.
- `npm --prefix chili_app run test:e2e -- chat-citations` (Playwright) verifies only cited chips render.
- Manual: ask a question whose retrieval set has 5 items but the answer only cites 2; observe 2 chips.

### Code touch points
- `backend/rag/adapters/protocols.py` (modify — add `AnswerCitationProtocol`)
- `backend/rag/adapters/in_memory.py` (modify — in-memory extractor for tests)
- `backend/api/_rag_bridges.py` (modify — `MarkerCitationExtractor`, prompt template)
- `backend/rag/service.py` (modify — call extractor before building citations)
- `backend/rag/service_models.py` (modify — `RagCitation.cited`, `RagQueryResponse.retrieved_record_ids`)
- `chili_app/src/pages/RagChatPage.tsx` (modify)

---

## Story rag.05: Carry conversation history into the RAG prompt

**ID:** rag.05
**Status:** planned
**Prerequisites:** [rag.01, api.03, llm.02]
**Unblocks:** []
**Estimated size:** M

**As a** chiliAI analyst running a multi-turn investigation,
**I need** the assistant to remember prior turns in the conversation,
**so that** I can ask follow-ups like "narrow that to providers in Florida" without restating the entire context every message.

### Current State
- `RagService.answer` accepts `RagQueryRequest` (`backend/rag/service.py:66`), which has no `conversation_id`, no history, no message turns.
- `ServiceAnswerGenerator.generate` builds chat from exactly two messages (`SYSTEM` + a single `USER` carrying only the current question and context) at `backend/api/_rag_bridges.py:262-267`.
- `ApiState.add_message` appends user message to `ConversationRecord.messages` then calls `_rag_service.answer(...)` with only `request.content` (`backend/api/state.py:434-466`); each turn is independent.

### Acceptance Criteria
- [ ] `RagQueryRequest` gains an optional `history: list[ChatTurn]` field (or a separate `RagFollowUpRequest` extends it) with role + content.
- [ ] `ApiState.add_message` (or its replacement post-`api.03`) passes the prior turns of `ConversationRecord.messages` into `RagService.answer`.
- [ ] `ServiceAnswerGenerator.generate` translates the history into `ChatMessageInput` entries between system and the final user message.
- [ ] A history-window / truncation policy is defined (drop-oldest with a configurable `max_history_turns` in `RagConfig`); summarize-on-overflow is deferred to `rag.12`.
- [ ] Tests cover: (a) follow-up referencing prior answer succeeds, (b) history beyond `max_history_turns` is trimmed, (c) empty history matches today's behavior.

### Verification
- `pytest backend/tests/rag/test_conversation_history.py backend/tests/api/test_rag_router.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/api` clean.
- Manual: in the chat UI, ask "list top 3 providers", then ask "which is highest risk?"; the second answer must reference the first.

### Code touch points
- `backend/rag/service_models.py` (modify)
- `backend/rag/service.py` (modify)
- `backend/api/_rag_bridges.py` (modify — `ServiceAnswerGenerator.generate`)
- `backend/api/state.py` / `backend/api/routers/rag.py` (modify — pass history)
- `backend/config/schema.py` (modify — `RagConfig.max_history_turns`)

---

## Story rag.06: Token-level streaming end-to-end

**ID:** rag.06
**Status:** planned
**Prerequisites:** [rag.01, llm.17, api.07]
**Unblocks:** []
**Estimated size:** M

**As a** chiliAI analyst,
**I need** the chat UI to stream tokens as the model produces them,
**so that** I see incremental output instead of staring at a spinner before a wall of text lands.

### Current State
- `ServiceAnswerGenerator.stream_generate` calls `self.generate(request)` and yields the full answer as one chunk (`backend/api/_rag_bridges.py:277-279`).
- `_stream_sse` (`backend/api/routers/rag.py:108-122`) consumes that single chunk and emits one SSE event followed by the `done` sentinel.
- `RagService.stream_answer` (`backend/rag/service.py:109-127`) iterates the generator's stream but the upstream chunking is single-shot.
- No token-level metadata: chunks carry `chunk_text` and `is_final` only; no `tokens_so_far` or partial-citation surface.

### Acceptance Criteria
- [ ] `ServiceAnswerGenerator.stream_generate` calls `LlmServiceProtocol.stream_generate` (from `llm.03`) and yields chunks as they arrive from the provider.
- [ ] `RagStreamChunk` semantics updated: non-final chunks carry token text only; final chunk carries `citations`, `provider`, `model_name`, and (if `rag.11` has landed) `TokenUsage`.
- [ ] SSE encoder at `backend/api/routers/rag.py:108-122` emits each token chunk as its own `data:` event in order; client receives them as they arrive.
- [ ] Frontend `RagChatPage.tsx` renders the streamed tokens incrementally (verified in Playwright with `--headed` showing progressive text).
- [ ] Backpressure: if the SSE client disconnects mid-stream, the LLM call is cancelled (or at minimum the iterator is closed and resources are released).
- [ ] Tests cover: (a) chunked output preserves character order, (b) final chunk has citations, (c) early disconnect closes the underlying stream.

### Verification
- `pytest backend/tests/rag/test_streaming.py backend/tests/api/test_rag_streaming.py -q`
- `npm --prefix chili_app run test:e2e -- chat-streaming` confirms incremental render.
- Manual: open the chat page, ask a long question, observe tokens arriving sub-second.

### Code touch points
- `backend/api/_rag_bridges.py` (modify — `ServiceAnswerGenerator.stream_generate`)
- `backend/rag/service.py` (modify — `RagService.stream_answer`)
- `backend/rag/service_models.py` (modify — `RagStreamChunk`)
- `backend/api/routers/rag.py` (modify — `_stream_sse`)
- `chili_app/src/pages/RagChatPage.tsx` (modify)

---

## Story rag.07: Reranker stage gated by RagConfig.reranking_enabled

**ID:** rag.07
**Status:** planned
**Prerequisites:** [rag.03, llm.02, embeddings.03]
**Unblocks:** [frontend.04, frontend.05]
**Estimated size:** L

**As a** chiliAI domain operator,
**I need** an optional reranker between retrieval and prompt assembly,
**so that** I can trade latency for retrieval precision when dense-vector top-k alone has noisy ordering.

### Current State
- `ContextRetrieverProtocol` carries a `TODO(production)` calling out hybrid search + reranking as missing (`backend/rag/adapters/protocols.py:22-25`).
- `RagService.answer` (`backend/rag/service.py:66-89`) has no rerank step; retrieval output flows straight into prompt assembly.
- `RagConfig.reranking_enabled: bool = False` (`backend/config/schema.py:205-211`) exists but is referenced nowhere in code.
- No `RerankerProtocol`, no `InMemoryReranker`, no cross-encoder adapter.

### Acceptance Criteria
- [ ] New `RerankerProtocol` (`backend/rag/adapters/protocols.py`) with signature `rerank(question: str, items: list[RetrievedContextItem]) -> list[RetrievedContextItem]`.
- [ ] In-memory `IdentityReranker` (test fixture) and one of `LlmJudgeReranker` (uses `LlmServiceProtocol`) or `CrossEncoderReranker` (uses sentence-transformers `CrossEncoder`) ships in the same story; the second adapter may follow.
- [ ] `RagService.answer` and `stream_answer` insert the reranker between `_prepare_state` and `_build_generation_request` when `RagConfig.reranking_enabled` is true.
- [ ] Reranker is wired through DI (`backend/api/dependencies.py`) and only loaded when enabled (lazy import for optional extras).
- [ ] Latency overhead is logged per request (cross-edge to `rag.13`).
- [ ] Decision on reranker backend (cross-encoder vs. LLM-judge vs. config-selectable) recorded in `backend/rag/README.md`.

### Verification
- `pytest backend/tests/rag/test_reranker.py -q` — coverage ≥ 85%.
- `pytest -m integration backend/tests/rag/test_reranker_integration.py -q` (skipped without `[sentence-transformers]` extra).
- `pyright backend/rag` clean.
- Manual: with `reranking_enabled: true` and a query whose top-1 result is wrong by cosine but right by cross-encoder, observe the reordered citations.

### Code touch points
- `backend/rag/adapters/protocols.py` (modify)
- `backend/rag/adapters/in_memory.py` (modify — `IdentityReranker`)
- `backend/rag/adapters/rerankers.py` (new — production adapters)
- `backend/rag/service.py` (modify — pipeline insertion point)
- `backend/api/dependencies.py` (modify)
- `backend/pyproject.toml` (modify — optional `[rerank]` extra if cross-encoder)

---

## Story rag.08: Hybrid retrieval (vector + keyword + graph signals) behind ContextRetrieverProtocol

**ID:** rag.08
**Status:** planned
**Prerequisites:** [rag.01, vectorstore.03, graph.03, embeddings.02]
**Unblocks:** []
**Estimated size:** L

**As a** chiliAI analyst asking a question that mentions a specific named entity (provider, beneficiary, claim id),
**I need** retrieval to combine dense-vector matches with keyword and graph-entity matches,
**so that** the right passage surfaces even when cosine similarity ranks it below a topically-similar but irrelevant chunk.

### Current State
- Retrieval is pure dense-vector cosine through `ServiceContextRetriever` (`backend/api/_rag_bridges.py:104-142`) and `InMemoryContextRetriever._cosine_similarity` (`backend/rag/adapters/in_memory.py:238-247`).
- No BM25/keyword path, no fulltext fallback.
- Graph proximity is attempted only post-retrieval in `ServiceGraphContextExpander._extract_entity_id` (`backend/api/_rag_bridges.py:282-287`).
- `ContextRetrieverProtocol` TODO at `backend/rag/adapters/protocols.py:22-25` explicitly calls hybrid retrieval out as missing.

### Acceptance Criteria
- [ ] New `HybridRetriever` composite adapter that fans out to (a) vector search (existing path), (b) keyword search (Neo4j fulltext per `graph.md` or Qdrant payload keyword), (c) graph-entity match.
- [ ] Score fusion strategy is Reciprocal Rank Fusion (RRF) or weighted-sum (decision documented in `backend/rag/README.md`); `RagConfig` gets a `retrieval_mode: Literal["vector", "hybrid"]` field with default `"vector"` to keep the existing behavior the fallback.
- [ ] `RagQueryRequest.retrieval_mode` optional override surfaces for debugging — gated by `_security.md` decision on caller-controllable knobs.
- [ ] Per-channel hit counts attached to the response (or logged) so reviewers can see which channel surfaced each citation.
- [ ] Tests cover: (a) keyword-only hit (query exact-matches a chunk that ranks low by cosine), (b) graph-entity hit (query names an entity present in the graph but not the vector top-k), (c) fusion never drops a vector-only winner.

### Verification
- `pytest backend/tests/rag/test_hybrid_retriever.py -q` — coverage ≥ 85%.
- `pytest -m integration backend/tests/rag/test_hybrid_neo4j_qdrant.py -q` (skipped without `[neo4j,qdrant]`).
- `pyright backend/rag backend/api/_rag_bridges.py` clean.

### Code touch points
- `backend/rag/adapters/protocols.py` (modify)
- `backend/rag/adapters/hybrid.py` (new — `HybridRetriever`, RRF helpers)
- `backend/api/_rag_bridges.py` (modify — keyword channel against vector store, graph channel against graph service)
- `backend/api/dependencies.py` (modify)
- `backend/config/schema.py` (modify — `RagConfig.retrieval_mode`)
- `backend/rag/service_models.py` (modify — `RagCitation.retrieval_channel`)

---

## Story rag.09: Enforce per-KB access policy inside RagService

**ID:** rag.09
**Status:** planned
**Prerequisites:** [rag.01, knowledgebases.01, api.17, _security.01]
**Unblocks:** [rag.17]
**Estimated size:** M

**As a** chiliAI platform operator,
**I need** every RAG entry point to enforce KB existence and the caller's KB access policy,
**so that** a malicious or buggy caller can't bypass `resolve_kb_scope` and read another tenant's KB.

### Current State
- `resolve_kb_scope` (`backend/shared/kb_scope.py:30-66`) is called at the chat router (`backend/api/routers/rag.py:97`) and in `ApiState.add_message` (`backend/api/state.py:450`); no other RAG entry point enforces it.
- `RagService.answer_question` (`backend/rag/service.py:91-107`) takes raw `knowledge_base_ids` and never validates KB existence, ownership, or tenant binding.
- `InMemoryRagService._require_known_kb` (`backend/rag/adapters/in_memory.py:200-207`) is the only existence check and only fires on the in-memory path.

### Acceptance Criteria
- [ ] `RagService.answer`, `answer_question`, and `stream_answer` call a `KbAccessGuard` (new dependency, injected) before retrieval; unknown KBs raise `RagConfigurationError`; unauthorized KBs raise a new `RagAuthorizationError` mapped to HTTP 403.
- [ ] `KbAccessGuard.check(tenant_id, user_id, knowledge_base_ids)` is a protocol; default implementation delegates to the `knowledgebases` module.
- [ ] All RAG entry points (router, worker, test fixtures) route through `resolve_kb_scope` before calling `RagService`.
- [ ] New `RagAuthorizationError` added to `backend/rag/exceptions.py` and mapped at the router.
- [ ] Tests cover: (a) unknown KB → 4xx with `RagConfigurationError`, (b) cross-tenant KB → 403 with `RagAuthorizationError`, (c) authorized KB → success path.

### Verification
- `pytest backend/tests/rag/test_kb_access_guard.py backend/tests/api/test_rag_router.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/api` clean.
- Manual: call `POST /chat/conversations/.../messages` with a KB id belonging to another tenant; observe 403.

### Code touch points
- `backend/rag/service.py` (modify)
- `backend/rag/exceptions.py` (modify — `RagAuthorizationError`)
- `backend/rag/adapters/protocols.py` (modify — `KbAccessGuard` protocol)
- `backend/api/_rag_bridges.py` (modify — concrete guard against knowledgebases service)
- `backend/api/dependencies.py` (modify)
- `backend/api/routers/rag.py` (modify — error mapping)

---

## Story rag.10: RAG quality evaluation harness with gold Q/A regression

**ID:** rag.10
**Status:** planned
**Prerequisites:** [rag.01, embeddings.11, llm.04, _cicd.01]
**Unblocks:** [api.03, frontend.02]
**Estimated size:** L

**As a** chiliAI maintainer changing embeddings, prompts, or rerankers,
**I need** an automated regression harness over a gold Q/A set,
**so that** quality regressions are caught in CI rather than discovered by analysts in production.

### Current State
- No `backend/rag/evals/` package.
- No Ragas/Trulens scaffolding.
- No gold-question fixtures beyond unit-level retrieval matchers in `backend/tests/rag/`.
- `docs/architecture.md:1346` notes "RAG quality depends heavily on embedding model choice" but there is no regression gate.

### Acceptance Criteria
- [ ] New `backend/rag/evals/` package with `__init__.py`, `runner.py`, `metrics.py`, and a `gold_set.py` loader.
- [ ] Metrics computed per run: retrieval recall@k, MRR, citation precision (intersection of `cited_record_ids` with gold-cited ids), answer-similarity (embedding cosine vs. reference answer).
- [ ] CLI entrypoint at `tools/rag_eval.py` runs the harness for a given domain config and persists JSON results to `docs/rag-evals/<domain>/<YYYY-MM-DD>.json`.
- [ ] CI hook (cross-edge `_cicd.01`) runs the harness on PRs that touch `backend/rag/`, `backend/embeddings/`, `backend/llm/`, or `backend/config/defaults/*.yaml`; fails when any metric regresses beyond a configurable delta (default 5% relative).
- [ ] Gold set storage decision recorded in `backend/rag/evals/README.md` (repo vs. object storage) and at least one demo gold set lives under `backend/tests/fixtures/rag_gold/`.

### Verification
- `pytest backend/tests/rag/evals -q` — coverage ≥ 85%.
- `python tools/rag_eval.py --domain medicare_fraud --dry-run` exits 0 and prints metrics.
- CI run on a no-op PR shows the harness completing inside the gate.

### Code touch points
- `backend/rag/evals/__init__.py` (new)
- `backend/rag/evals/runner.py` (new)
- `backend/rag/evals/metrics.py` (new)
- `backend/rag/evals/gold_set.py` (new)
- `backend/rag/evals/README.md` (new)
- `tools/rag_eval.py` (new)
- `backend/tests/fixtures/rag_gold/medicare_fraud.yaml` (new)
- `.github/workflows/ci.yaml` (modify — cross-edge `_cicd.01`)

---

## Story rag.11: Token usage and cost tracking per RAG query

**ID:** rag.11
**Status:** planned
**Prerequisites:** [rag.01, rag.12, llm.05, embeddings.05, _observability.04, _multitenancy.04]
**Unblocks:** [api.09, rag.15]
**Estimated size:** L

**As a** chiliAI platform operator,
**I need** every RAG query to record prompt/completion token counts and estimated cost,
**so that** I can roll up cost per user, per KB, and per tenant, and enforce quotas (`rag.15`) on real numbers.

### Current State
- `ServiceAnswerGenerator.generate` returns `RagGenerationResult{request_id, answer, provider, model_name}` (`backend/api/_rag_bridges.py:240-275`) — no token usage.
- `RagQueryResponse` (`backend/rag/service_models.py:51-60`) carries no token usage, no cost.
- `RagCompletedEvent.replies` (`backend/events/types.py:229-241`) records `context_item_count`, `citation_count`, `answer_length` only.
- No price-per-token table; no per-provider cost accounting.

### Acceptance Criteria
- [ ] New `TokenUsage` model in `backend/rag/models.py` with `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`, `estimated_cost_usd: Decimal` and the model used.
- [ ] `RagGenerationResult` gains `usage: TokenUsage`; `RagQueryResponse` exposes it; `RagCompletionReference` carries `usage` and `tenant_id`.
- [ ] `ServiceAnswerGenerator.generate` reads token counts from the upstream `LlmServiceProtocol` response (cross-edge `llm.05`) and accumulates query-side embedding cost from `embeddings.05`.
- [ ] Cost calculation uses a per-model price table loaded from config; unknown model → cost = `None` (not zero) and logged.
- [ ] Per-query usage persisted (via `database.NN` once available, or to a Postgres table introduced here) keyed by `(tenant_id, user_id, kb_id, request_id, timestamp)`.
- [ ] `/metrics` exposes `rag_tokens_total` and `rag_cost_usd_total` counters labeled by tenant/kb/provider (cross-edge `_observability.04`).

### Verification
- `pytest backend/tests/rag/test_token_usage.py backend/tests/events/test_rag_completed_event.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/api/_rag_bridges.py` clean.
- Manual: send a chat message, query `/metrics`, observe non-zero `rag_tokens_total{provider="..."}`.

### Code touch points
- `backend/rag/models.py` (modify — `TokenUsage`)
- `backend/rag/service_models.py` (modify — `RagQueryResponse.usage`)
- `backend/events/types.py` (modify — `RagCompletionReference.usage`, `.tenant_id`)
- `backend/api/_rag_bridges.py` (modify — `ServiceAnswerGenerator.generate`)
- `backend/rag/service.py` (modify — propagate usage)
- `backend/config/schema.py` (modify — `RagConfig.model_pricing`)
- `backend/rag/cost.py` (new — cost computation)

---

## Story rag.12: First-class token-budget assembly with per-provider tokenizer

**ID:** rag.12
**Status:** planned
**Prerequisites:** [rag.01, llm.06]
**Unblocks:** [rag.11]
**Estimated size:** L

**As a** chiliAI analyst querying with long histories or large context,
**I need** context assembly to use a real tokenizer and respect the model's actual context window,
**so that** I don't silently lose passages to a `chars / 4` heuristic and the assistant doesn't crash on over-budget prompts.

### Current State
- `ServiceAnswerGenerator._fit_context_to_budget` (`backend/api/_rag_bridges.py:334-375`) computes `budget_chars = int(self._max_tokens * 0.8) * 4` using module constants `_CHAR_PER_TOKEN = 4`, `_BUDGET_FRACTION = 0.8` (`backend/api/_rag_bridges.py:38-40`).
- Items dropped greedily by score; last one rough-truncated at `_MIN_TRUNCATED_CONTENT_CHARS = 16` (`backend/api/_rag_bridges.py:40,366`).
- No tokenizer (no `tiktoken`, no SentencePiece); `max_tokens` is the generation cap, not the model window.
- `graph_context.summary` is not separately accounted for in the budget.
- No fallback when the question alone exceeds the window.
- No summarize-then-stuff path for long contexts.

### Acceptance Criteria
- [ ] New `TokenizerProtocol` (likely lives in `backend/llm/` per cross-edge `llm.06`) exposing `count_tokens(text: str, model: str) -> int`.
- [ ] `ServiceAnswerGenerator` uses the provider-appropriate tokenizer for budget math; the `_CHAR_PER_TOKEN` constant is removed.
- [ ] Per-model context-window registry consulted (`llm.06`); budget = `context_window - response_reserve - prompt_overhead`.
- [ ] `graph_context.summary` accounted for as a separate line item; question text counted before context.
- [ ] Over-budget fallback: when the question + system prompt alone exceed the window, drop graph context first, then fall back to a "context summarization" pre-pass (the simplest viable form, e.g. truncate the longest items and prepend "Note: context was abridged.").
- [ ] Observability signals emitted: `rag_context_items_dropped_total`, `rag_context_items_truncated_total`, `rag_prompt_tokens` histogram (cross-edge `_observability.04` / `rag.13`).
- [ ] Tests cover (a) accurate token count via tokenizer, (b) over-budget drops by score, (c) question-alone-too-big raises a clear error, (d) graph context dropped before retrieval items.

### Verification
- `pytest backend/tests/rag/test_token_budget.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/api/_rag_bridges.py backend/llm` clean.
- Manual: ask a question with `top_k=50`; observe a log line showing items dropped and the final prompt token count under the window.

### Code touch points
- `backend/api/_rag_bridges.py` (modify — `_fit_context_to_budget`, constants removed)
- `backend/rag/service.py` (modify — pass model into the assembler)
- `backend/llm/protocols.py` (modify — `TokenizerProtocol`; cross-edge `llm.06`)
- `backend/llm/registry.py` (new or modify — context-window table)
- `backend/rag/models.py` (modify — `RagGenerationRequest.tokens_used`)

---

## Story rag.13: Per-stage RAG observability (latency, retrieval recall, prompt size, errors)

**ID:** rag.13
**Status:** planned
**Prerequisites:** [rag.01, _observability.01, _observability.04, events.05]
**Unblocks:** [rag.14]
**Estimated size:** M

**As a** chiliAI on-call engineer,
**I need** per-stage RAG timing and error metrics on `/metrics` plus OTel spans on each pipeline stage,
**so that** I can graph p50/p95 latency per stage and chase down where a slow query bottlenecks.

### Current State
- `RagService` emits exactly one event (`RagCompletedEvent` at `backend/rag/service.py:208-229`).
- No Prometheus metric, no tracing span, no structured log lines for stage timings.
- `TODO(production)` at `backend/rag/service.py:43-47` enumerates the missing surface (retries, timeouts, circuit breakers, memoization) and none of it exists.

### Acceptance Criteria
- [ ] OTel span emitted per pipeline stage: `embed_query`, `retrieve`, `rerank` (when enabled), `expand_graph`, `assemble_prompt`, `generate`, `stream`.
- [ ] Prometheus metrics: `rag_stage_duration_seconds` (histogram, labels: stage, provider, kb_id), `rag_stage_errors_total` (counter, labels: stage, error_class), `rag_retrieved_items` (histogram), `rag_prompt_tokens` (histogram, requires `rag.12`).
- [ ] Structured log lines per stage with `request_id`, `knowledge_base_ids`, stage, duration_ms; sampled at info level, full at debug.
- [ ] W3C trace context propagated onto `RagCompletedEvent` (cross-edge `events.05`).
- [ ] `/metrics` surface reachable from the API container (cross-edge `_observability.01`); dashboards added to `infra/` once that module exists.

### Verification
- `pytest backend/tests/rag/test_observability.py -q` — coverage ≥ 85%.
- `pyright backend/rag` clean.
- Manual: send 10 chat messages, scrape `/metrics`, observe `rag_stage_duration_seconds_bucket` populated for every stage.

### Code touch points
- `backend/rag/service.py` (modify — wrap stages in spans + timers)
- `backend/rag/metrics.py` (new — Prometheus counters/histograms)
- `backend/rag/tracing.py` (new — OTel helpers)
- `backend/events/types.py` (modify — trace context on `RagCompletedEvent`)
- `backend/api/_rag_bridges.py` (modify — instrument bridges)

---

## Story rag.14: Request-side resilience (retries, timeouts, graceful graph degradation, circuit breaker)

**ID:** rag.14
**Status:** planned
**Prerequisites:** [rag.01, rag.13, llm.07, shared.05]
**Unblocks:** []
**Estimated size:** M

**As a** chiliAI analyst,
**I need** transient retrieval/generation failures to retry automatically and a graph-expansion outage to degrade gracefully,
**so that** a flaky LLM provider or a downed Neo4j doesn't pin every API worker or force me to retry by hand.

### Current State
- `RagService.answer` catches `ValueError → RagConfigurationError` and `Exception → RagRetrievalError`/`RagGenerationError` (`backend/rag/service.py:71-76,150-153,196-206`); never retries.
- `TODO(production)` at `backend/rag/service.py:43-47` calls out retries, timeouts, circuit breakers, memoization as missing.
- `ContextRetrieverProtocol` TODO (`backend/rag/adapters/protocols.py:22-25`) notes deadline propagation is missing.
- A graph expansion failure surfaces as `RagRetrievalError` and kills the whole query (`backend/rag/service.py:196-206`).

### Acceptance Criteria
- [ ] Tenacity-style retry with jittered exponential backoff on retrieval and generation stages; max attempts and base delay come from `RagConfig` (`retry_attempts`, `retry_base_delay_ms`).
- [ ] Per-stage timeouts (`retrieval_timeout_ms`, `generation_timeout_ms`, `graph_timeout_ms`) propagated via a request-scoped deadline; `ContextRetrieverProtocol`, `AnswerGeneratorProtocol`, and `GraphContextExpanderProtocol` accept an optional `deadline` parameter.
- [ ] Graph expansion failure is non-fatal: log + emit a metric + continue with empty `GraphContext`; only retrieval/generation failures still raise.
- [ ] Per-provider circuit breaker for the LLM and embeddings paths (cross-edge `llm.07`); circuit-open responses return 503 with `Retry-After`.
- [ ] Shared retry primitive lives in `backend/shared/resilience.py` (`shared.05`) so other modules (`embeddings`, `llm`, `monitoring`) can reuse it.
- [ ] Tests cover (a) transient retrieval failure retried then succeeds, (b) graph timeout returns answer without graph context, (c) repeated LLM failure trips circuit, (d) timeout raises `RagGenerationError` with the deadline propagated downstream.

### Verification
- `pytest backend/tests/rag/test_resilience.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/shared` clean.
- Manual: kill the LLM container mid-query, observe automatic retry + circuit open after the configured threshold.

### Code touch points
- `backend/rag/service.py` (modify — retries, timeouts, graph degradation)
- `backend/rag/adapters/protocols.py` (modify — `deadline` parameter)
- `backend/api/_rag_bridges.py` (modify — pass deadline downstream)
- `backend/shared/resilience.py` (new — shared retry, circuit breaker; cross-edge `shared.05`)
- `backend/config/schema.py` (modify — `RagConfig` resilience fields)

---

## Story rag.15: Per-user / per-tenant RAG rate limit and quota

**ID:** rag.15
**Status:** planned
**Prerequisites:** [rag.11, rag.17, api.18, _infra.04, _security.04, _multitenancy.04]
**Unblocks:** []
**Estimated size:** M

**As a** chiliAI platform operator,
**I need** RAG calls throttled per (tenant, user) and capped per tenant on monthly token spend,
**so that** a runaway client or a misbehaving prompt can't exhaust LLM budget or pin every API worker on SSE responses.

### Current State
- No throttle in `RagService`, `_rag_bridges`, or the chat router.
- `POST /chat/conversations/{conversation_id}/messages?stream=true` (`backend/api/routers/rag.py:65-105`) holds an SSE response open for the full LLM call with no per-user concurrency cap.
- No per-minute message limit, no per-tenant token-budget quota, no "cost ceiling reached" response.

### Acceptance Criteria
- [ ] Redis token-bucket keyed by `(tenant_id, user_id)` enforced as middleware or guard in front of `RagService`; bucket size + refill rate come from `RagConfig.rate_limit` per role.
- [ ] Per-tenant monthly token-cost ceiling (paired with `rag.11`); reads accumulated cost from the persistence layer; HTTP 429 with `Retry-After` when exceeded, HTTP 402 (or 403 + explicit body) when monthly ceiling hit.
- [ ] Per-user concurrent SSE stream cap (default 2) so one analyst can't hold N workers open.
- [ ] Cross-edge: piggybacks on the gateway rate-limit middleware from `api.18` rather than duplicating the throttle logic.
- [ ] Quota state observable on `/metrics` (`rag_rate_limit_remaining`, `rag_monthly_cost_remaining_usd`).
- [ ] Tests cover: (a) burst above rate → 429 with `Retry-After`, (b) monthly ceiling → 402/403, (c) concurrent-stream cap → 429.

### Verification
- `pytest backend/tests/rag/test_rate_limit.py backend/tests/api/test_rag_router.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/api` clean.
- Manual: burst 100 chat messages from one user, observe 429s with `Retry-After`.

### Code touch points
- `backend/rag/rate_limit.py` (new)
- `backend/api/routers/rag.py` (modify — enforce guard)
- `backend/api/middleware/rate_limit.py` (modify — cross-edge `api.18`)
- `backend/config/schema.py` (modify — `RagConfig.rate_limit`)
- `backend/rag/exceptions.py` (modify — `RagQuotaExceededError`)

---

## Story rag.16: Prompt caching (assembled system prompt + per-KB context block + provider cache hints)

**ID:** rag.16
**Status:** planned
**Prerequisites:** [rag.01, llm.08, embeddings.02, config.02]
**Unblocks:** []
**Estimated size:** M

**As a** chiliAI platform operator,
**I need** the assembled system prompt and per-KB stable context blocks cached, and provider cache-control surfaced where available,
**so that** repeated questions and large reference policy KBs don't repay the input-token cost each turn.

### Current State
- `_DEFAULT_SYSTEM_PROMPT` is recomputed at `backend/api/_rag_bridges.py:34-37` per request.
- `_resolve_system_prompt` re-renders the domain-config template via `_render_system_prompt` (`backend/rag/service.py:175-187, 308-318`) on every call with no memoization.
- `_assemble_prompt` (`backend/api/_rag_bridges.py:312-331`) rebuilds the full context block per request.
- Anthropic and OpenAI support cache-control / `cache_control` markers, but `ChatMessageInput` and `GenerateRequest` (`backend/llm/service_models.py`) have no cache hint.

### Acceptance Criteria
- [ ] Rendered system prompt cached by `(domain_config_version, template_hash, tenant_id)` in a TTL-ed in-process LRU or Redis (decision documented).
- [ ] Per-KB stable context blocks cached by `(kb_id, content_hash, tenant_id)` so repeated retrieval over the same set reuses the same string.
- [ ] `ChatMessageInput` / `GenerateRequest` gain `cache_hint: CacheHint | None` (or equivalent) so the LLM provider abstraction (`llm.08`) can attach native cache-control markers on long stable prompt prefixes.
- [ ] Cache invalidation on domain-config reload (cross-edge `config.02`): bumping `domain_config_version` evicts the system-prompt cache.
- [ ] Cache hit/miss observable on `/metrics` (`rag_prompt_cache_hits_total`, `rag_prompt_cache_misses_total`).
- [ ] Tests cover: (a) repeat question hits the cache, (b) config reload invalidates, (c) provider cache hint is attached when long stable prefix is present.

### Verification
- `pytest backend/tests/rag/test_prompt_cache.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/api/_rag_bridges.py backend/llm` clean.
- Manual: ask the same question twice, observe `rag_prompt_cache_hits_total` increase by 1.

### Code touch points
- `backend/rag/cache.py` (new — prompt cache)
- `backend/api/_rag_bridges.py` (modify — consult cache before rendering)
- `backend/rag/service.py` (modify — `_resolve_system_prompt` consults cache)
- `backend/llm/service_models.py` (modify — `CacheHint`; cross-edge `llm.08`)
- `backend/config/schema.py` (modify — `RagConfig.prompt_cache_ttl_seconds`)

---

## Story rag.17: Tenant-scoped RAG path (tenant on request, tenant-keyed caches, refuse cross-tenant KB joins)

**ID:** rag.17
**Status:** planned
**Prerequisites:** [rag.09, api.21, knowledgebases.05, _multitenancy.01, _multitenancy.02, _multitenancy.03, _security.05]
**Unblocks:** [rag.15]
**Estimated size:** L

**As a** chiliAI multi-tenant platform operator,
**I need** every RAG request bound to the caller's tenant with cross-tenant KB joins refused,
**so that** tenant A cannot accidentally or maliciously query tenant B's KB and prompt/embedding caches stay isolated.

### Current State
- `RagQueryRequest` (`backend/rag/service_models.py:22-30`) has no `tenant_id`.
- `RagService` is a process singleton built once at `ApiState.__init__` (`backend/api/state.py:172-178`).
- Even when `api.21` plumbs tenant context into middleware there is nowhere in the RAG layer to consume it today.
- `_security.md` calls cross-tenant data leakage out as a key risk; `_multitenancy.md` defines the tenant-context contract.

### Acceptance Criteria
- [ ] `RagQueryRequest` gains a required `tenant_id: str` (or `RagService` reads it from a request-scoped contextvar populated by middleware — decision recorded).
- [ ] Every `knowledge_base_id` in scope is validated against the caller's tenant via the `KbAccessGuard` from `rag.09`; mismatch raises `RagAuthorizationError`.
- [ ] Prompt cache (`rag.16`), embedding cache (`embeddings.02`), and per-tenant cost roll-ups (`rag.11`) are keyed by `tenant_id`.
- [ ] `RagCompletedEvent.replies[*]` carries `tenant_id` so downstream consumers can attribute cost per tenant.
- [ ] Decision recorded: does `RagService` stay a singleton with tenant as a request parameter, or does it become per-tenant via DI factory? (per cross-cutting `_multitenancy.02` resolution).
- [ ] Tests cover: (a) cross-tenant KB → 403, (b) two tenants asking the same question hit separate cache entries, (c) `RagCompletedEvent` carries the right `tenant_id` end-to-end.

### Verification
- `pytest backend/tests/rag/test_tenant_scoping.py backend/tests/api/test_rag_router.py -q` — coverage ≥ 85%.
- `pyright backend/rag backend/api` clean.
- Manual: as tenant A user, attempt to query a KB owned by tenant B; observe 403.

### Code touch points
- `backend/rag/service_models.py` (modify — `RagQueryRequest.tenant_id`)
- `backend/rag/service.py` (modify — propagate tenant)
- `backend/rag/cache.py` (modify — tenant-keyed cache)
- `backend/rag/rate_limit.py` (modify — tenant-keyed bucket; cross-edge `rag.15`)
- `backend/events/types.py` (modify — `RagCompletionReference.tenant_id`)
- `backend/api/_rag_bridges.py` (modify — guard pulls tenant from context)
- `backend/api/state.py` (modify — drop singleton if per-tenant decision lands)
