# embeddings backlog

> **Scope:** Embedder protocol + adapters (local, OpenAI, sentence-transformers), batching, caching, versioning, dimensions handling, cost tracking, fine-tuning hook.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story embeddings.01: Add EmbedderProtocol introspection and health-check surfaces

**ID:** embeddings.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [agent.09, embeddings.08, embeddings.09, rag.01, vectorstore.11]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md

**As a** platform operator,
**I need** every embedder adapter to advertise its model identity, dimensions, and reachability through a typed protocol,
**so that** the API readiness probe and config-validation paths can verify embedder health without provider-specific code paths.

### Current State
- `EmbedderProtocol` only declares `embed(request) -> EmbeddingResult` and carries an explicit `TODO(production)` noting that `get_model_info()` / `health_check()` and an async variant are still missing (`backend/embeddings/adapters/protocols.py:11-22`).
- Each adapter (`InMemoryEmbedder`, `OpenAIEmbedder`, `SentenceTransformersEmbedder`) hard-codes its provider name and reads `dimensions` from config but never exposes it through the protocol (`backend/embeddings/adapters/in_memory.py:14-36`, `backend/embeddings/adapters/openai_adapter.py:51-103`, `backend/embeddings/adapters/sentence_transformers_adapter.py:47-83`).
- API readiness has no embedder probe today and `get_embedder` simply constructs the adapter under `lru_cache` (`backend/api/dependencies.py:531-572`).

### Acceptance Criteria
- [ ] `EmbeddingModelInfo` model added to `backend/embeddings/models.py` (fields: `model_name`, `provider`, `dimensions`, `max_input_tokens`, `supports_batch`).
- [ ] `EmbedderProtocol` in `backend/embeddings/adapters/protocols.py` declares `get_model_info() -> EmbeddingModelInfo` and `health_check() -> EmbedderHealth` (success/failure with reason).
- [ ] All three concrete adapters implement both methods; in-memory always reports healthy, OpenAI issues a minimal probe (or surfaces the last error), sentence-transformers checks the model object is loaded.
- [ ] `EmbeddingsServiceProtocol` exposes a pass-through `describe()` and `health_check()` that callers can invoke without touching the adapter directly.
- [ ] `pyright --strict` clean for `backend/embeddings/` and `backend/api/dependencies.py`.
- [ ] Unit tests in `backend/tests/embeddings/` cover each adapter's introspection and health output (including failure paths for OpenAI and sentence-transformers).

### Verification
- `uv run --project backend pytest backend/tests/embeddings -v` green.
- `uv run --project backend pyright backend/embeddings backend/api/dependencies.py` clean.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/adapters/protocols.py` (modify)
- `backend/embeddings/models.py` (modify)
- `backend/embeddings/adapters/in_memory.py` (modify)
- `backend/embeddings/adapters/openai_adapter.py` (modify)
- `backend/embeddings/adapters/sentence_transformers_adapter.py` (modify)
- `backend/embeddings/protocols.py` (modify)
- `backend/embeddings/service.py` (modify)
- `backend/tests/embeddings/` (modify | new)

---

## Story embeddings.02: Add configurable embedding cache via EmbeddingCacheProtocol

**ID:** embeddings.02
**Status:** planned
**Prerequisites:** []
**Unblocks:** [rag.02, rag.08, rag.16]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md

**As a** RAG pipeline owner,
**I need** identical text to skip the provider call by returning a cached vector,
**so that** re-uploads, deduplicated records, and repeated RAG queries do not pay full provider cost or latency for content we have already embedded.

### Current State
- `EmbeddingsService.embed` always invokes the adapter; the service-level `TODO(production)` explicitly calls out the missing content-hash cache and chunking logic (`backend/embeddings/service.py:20-49`).
- No cache abstraction exists in `backend/embeddings/`; `llm` has no shared cache surface either.
- The §14.2 endgame implies a single cross-module cache abstraction reused by `llm`.
- **PM prereq cleanup (2026-06-23):** original prereqs `[shared.02, _infra.05, llm.09]` were all mislabeled — shared.02 = "Retire `Alert.acknowledged`", _infra.05 = "Helm values/chart-test CI", llm.09 = "LLM observability"; none gates an embedding cache adapter. The body had referenced a "shared Redis pool from `shared.02`" but **no shared-redis-pool foundation story exists** (the Redis client/pool lives in `events/runtime.py` + config). The `RedisEmbeddingCache` adapter sources the pool from existing infra at implementation time; prereqs reduced to `[]`.

### Acceptance Criteria
- [ ] `EmbeddingCacheProtocol` added to `backend/embeddings/protocols.py` with `get(key) -> list[float] | None` and `set(key, vector, model_name, dimensions, ttl)`.
- [ ] Cache key derived from `(model_name, provider, dimensions, sha256(normalized_content))`; key derivation lives in a `_cache_key` helper covered by tests.
- [ ] Two concrete cache adapters in `backend/embeddings/adapters/`: `InMemoryEmbeddingCache` and `RedisEmbeddingCache` (the latter reuses the existing Redis client/pool established in `events/runtime.py`).
- [ ] `EmbeddingsService` constructor accepts an optional `EmbeddingCacheProtocol`; service flow checks the cache before invoking the adapter and writes back on miss.
- [ ] Cache is bypassed for any submission that requests `model_name` not equal to the cached value (no cross-model reuse).
- [ ] Composition root `get_embeddings_service()` wires the cache implementation from `DomainConfig.embeddings.cache` (new sub-config; off by default for backwards compatibility).
- [ ] Unit tests cover: hit, miss, partial-batch hit/miss interleaving, model-name mismatch invalidation, TTL eviction.

### Verification
- `uv run --project backend pytest backend/tests/embeddings -v` green including new cache cases.
- Coverage gate: ≥ 85% on `embeddings` package.
- Integration test with `RedisEmbeddingCache` against the dev Redis container (`docker compose -f docker-compose.dev.yaml up redis`) shows second identical call hits the cache.

### Code touch points
- `backend/embeddings/protocols.py` (modify)
- `backend/embeddings/adapters/` (new: `in_memory_cache.py`, `redis_cache.py`)
- `backend/embeddings/service.py` (modify)
- `backend/config/schema.py` (modify — add `EmbeddingsCacheConfig`)
- `backend/api/dependencies.py` (modify — wire cache)
- `backend/agent/coordinator.py` (modify — wire cache in `build_embedder`/service composition)
- `backend/tests/embeddings/` (new test files)

---

## Story embeddings.03: Add provider-side retry/backoff for non-OpenAI adapters

**ID:** embeddings.03
**Status:** planned
**Prerequisites:** [shared.15]
**Unblocks:** [rag.07]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md

**As a** worker operator,
**I need** every embedder adapter to apply consistent retry-with-backoff on transient errors and to respect provider rate limits,
**so that** sporadic 429s, network blips, or local-model GPU contention do not surface as pipeline failures.

### Current State
- Only `OpenAIEmbedder._create_embeddings_with_retry` implements exponential backoff for 429s using `_MAX_RETRY_ATTEMPTS = 3` (`backend/embeddings/adapters/openai_adapter.py:115-138`).
- `SentenceTransformersEmbedder._encode_batch` has no retry surface; any exception from `self._model.encode(...)` propagates raw and is then wrapped as `EmbeddingProviderError` by the service (`backend/embeddings/adapters/sentence_transformers_adapter.py:65-117`).
- `InMemoryEmbedder.embed` has no retry but also no I/O; it should be exempt.
- Service-level `TODO(production)` flags retry-with-backoff as a gap (`backend/embeddings/service.py:20-25`).

### Acceptance Criteria
- [ ] Shared retry primitive consumed from `shared.15` (or, if not yet extracted at implementation time, a local `_retry_with_backoff` helper that mirrors the contract and is replaced in a follow-up).
- [ ] `SentenceTransformersEmbedder` retries on `RuntimeError` / `torch.cuda.OutOfMemoryError`-class errors with bounded attempts and falls back to a smaller batch before re-raising.
- [ ] `OpenAIEmbedder` refactored to consume the shared primitive without changing observable retry semantics; `_is_rate_limit_error` stays the trigger and retry budget is configurable via `EmbeddingsConfig.retry_max_attempts` (default 3).
- [ ] Retry counts and final-failure reasons are exposed for the observability story (embeddings.04) — adapters expose a `last_retry_count` attribute or emit a callback hook on retry.
- [ ] Tests cover: succeeds on first attempt, succeeds after one retry, exhausts attempts and raises `EmbeddingProviderError`, non-retryable error path raises immediately for each adapter.

### Verification
- `uv run --project backend pytest backend/tests/embeddings -v` green.
- Coverage gate: ≥ 85% on `embeddings` package.
- `uv run --project backend pyright backend/embeddings` clean.

### Code touch points
- `backend/embeddings/adapters/sentence_transformers_adapter.py` (modify)
- `backend/embeddings/adapters/openai_adapter.py` (modify)
- `backend/embeddings/adapters/in_memory.py` (unchanged — no retry needed; assert in tests)
- `backend/config/schema.py` (modify — add `retry_max_attempts`, `retry_base_seconds` to `EmbeddingsConfig`)
- `backend/tests/embeddings/` (modify)

---

## Story embeddings.04: Add embedding observability (latency, batch size, errors, retries)

**ID:** embeddings.04
**Status:** planned
**Prerequisites:** [_observability.03, _observability.05]
**Unblocks:** [embeddings.05]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md

**As a** site-reliability engineer,
**I need** per-provider latency, batch size, vector count, and error-class metrics plus structured logs from every embedding call,
**so that** I can attribute slow ingestion to a specific provider/model and alert on embedder-level error spikes without parsing coordinator logs.

### Current State
- `EmbeddingsService` and adapters emit no metrics, traces, or structured logs (`backend/embeddings/service.py:38-105`, `backend/embeddings/adapters/openai_adapter.py:80-138`).
- The coordinator only emits `observe_pipeline_stage("embeddings", ...)` at the workflow boundary, so per-provider latency and error-class breakdown are invisible.
- No telemetry conventions exist for embedding spans/attributes yet — they need to follow whatever `_observability.03` lands.

### Acceptance Criteria
- [ ] OpenTelemetry span emitted around `EmbeddingsService.embed` and around each adapter's `embed` call with attributes `embedding.provider`, `embedding.model`, `embedding.dimensions`, `embedding.batch_size`, `embedding.item_count`, `embedding.channel`.
- [ ] Counters: `embeddings_requests_total{provider,model,channel,status}`; histograms: `embeddings_latency_seconds{provider,model,channel}`, `embeddings_batch_size{provider,model}`.
- [ ] Retry events from embeddings.03 emit `embeddings_retries_total{provider,model,reason}`.
- [ ] Structured log on adapter exception path includes provider, model, item count, error class name (no content payload).
- [ ] Metric/attribute names match the conventions documented in `_observability.03`.
- [ ] Unit tests assert metric emission via the observability fake/recording exporter from `_observability.05`.

### Verification
- `uv run --project backend pytest backend/tests/embeddings -v` green.
- Local stack: hit `/embeddings` via worker run; verify metrics show up in the observability backend defined by `_observability.03`.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/service.py` (modify)
- `backend/embeddings/adapters/openai_adapter.py` (modify)
- `backend/embeddings/adapters/sentence_transformers_adapter.py` (modify)
- `backend/embeddings/adapters/in_memory.py` (modify — minimal instrumentation)
- `backend/tests/embeddings/` (modify)

---

## Story embeddings.05: Add embedding cost tracking per provider

**ID:** embeddings.05
**Status:** planned
**Prerequisites:** [_observability.06, embeddings.04]
**Unblocks:** [api.19, llm.05, llm.08, rag.11]
**Estimated size:** M

**As a** finance / platform owner,
**I need** OpenAI input-token counts and sentence-transformers compute units recorded per request, knowledge base, and tenant,
**so that** embedding spend can be attributed to the workload that incurred it and rolled up alongside LLM cost.

### Current State
- `_estimate_tokens` exists only inside the OpenAI adapter's batcher (`backend/embeddings/adapters/openai_adapter.py:225-228`); the value is never surfaced.
- No cost counter, per-request token usage, or per-KB roll-up is recorded for any provider.
- Service emits an `EmbeddingsGeneratedEvent` with item counts but no cost fields (`backend/embeddings/service.py:92-104`).

### Acceptance Criteria
- [ ] `EmbeddingCostRecord` added to `backend/embeddings/models.py` with fields `provider`, `model_name`, `input_tokens`, `requests`, `knowledge_base_id`, `tenant_id`, `estimated_cost_usd`.
- [ ] OpenAI adapter records actual input tokens from the provider response (`usage.prompt_tokens` when present, falling back to `_estimate_tokens` only if absent) and surfaces them on `EmbeddingResult.metadata` or a sibling `cost: EmbeddingCostRecord` field.
- [ ] Sentence-transformers adapter records `input_tokens` via the same `_estimate_tokens` heuristic shared into a module-level helper.
- [ ] `EmbeddingsService.embed` publishes a cost event/metric via the cost-attribution surface from `_observability.06`; tenant ID flows through from request context.
- [ ] Cost-per-million-tokens table is configuration-driven (`EmbeddingsConfig.cost_per_million_tokens`, default 0); estimated cost = `input_tokens * cost_per_million / 1_000_000`.
- [ ] Unit tests assert recorded token counts and cost computation for both real provider response shapes and missing-usage fallback.

### Verification
- `uv run --project backend pytest backend/tests/embeddings -v` green.
- Manual: run worker, embed a 5-item batch through OpenAI fake, verify cost record present in observability sink.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/models.py` (modify)
- `backend/embeddings/adapters/openai_adapter.py` (modify)
- `backend/embeddings/adapters/sentence_transformers_adapter.py` (modify)
- `backend/embeddings/service.py` (modify)
- `backend/config/schema.py` (modify — add `cost_per_million_tokens`)
- `backend/tests/embeddings/` (modify)

---

## Story embeddings.06: Stamp immutable model_version metadata on persisted vectors

**ID:** embeddings.06
**Status:** planned
**Prerequisites:** []
**Unblocks:** [embeddings.07]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md

**As a** KB curator,
**I need** every persisted vector to carry an immutable `model_version` string that reflects the exact provider snapshot used,
**so that** I can detect when a configuration change has moved the model under existing vectors and trigger a backfill (embeddings.07) deterministically.

### Current State
- `EmbeddingMetadata` carries `model_name` only — no immutable model snapshot / commit hash (`backend/embeddings/models.py:45-52`).
- `EmbeddingVector` similarly tracks `model_name` but not a stable `model_version` (`backend/embeddings/models.py:54-71`).
- Coordinator's `handle_embeddings_complete` indexes vectors without stamping a versioned identity into vectorstore metadata (`backend/agent/coordinator.py:1761-1864`).

### Acceptance Criteria
- [ ] `EmbeddingMetadata.model_version: str` field added; required for all adapter outputs.
- [ ] OpenAI adapter populates `model_version` from the API response (`response.model` snapshot id like `text-embedding-3-small-2024-01-25`); fallback to configured model when absent.
- [ ] Sentence-transformers adapter populates `model_version` from the loaded model's commit hash (via `model._modules` / `model.config_keys` introspection) or the package version + model name when commit hash is unavailable.
- [ ] In-memory adapter uses a deterministic `model_version = "in-memory@<implementation-version>"`.
- [ ] `embedding_model_version` flows into vectorstore record metadata in `handle_embeddings_complete` (written into the existing freeform vector `metadata`/`payload` map — no vectorstore schema-change story is required; the prior `vectorstore.06` prereq was mislabeled, as that story is sharding/replication knobs).
- [ ] Unit tests cover each adapter's `model_version` output including the fallback paths.

### Verification
- `uv run --project backend pytest backend/tests/embeddings backend/tests/agent -v` green.
- Manual: index one OpenAI vector, query it back via the vectorstore CLI, assert `embedding_model_version` is present.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/models.py` (modify)
- `backend/embeddings/adapters/openai_adapter.py` (modify)
- `backend/embeddings/adapters/sentence_transformers_adapter.py` (modify)
- `backend/embeddings/adapters/in_memory.py` (modify)
- `backend/agent/coordinator.py` (modify — `handle_embeddings_complete`)
- `backend/tests/embeddings/` (modify)
- `backend/tests/agent/` (modify)

---

## Story embeddings.07: Embedding backfill workflow for model-version changes

**ID:** embeddings.07
**Status:** planned
**Prerequisites:** [embeddings.06]
**Unblocks:** []
**Estimated size:** L

**As a** KB operator,
**I need** a worker workflow that re-embeds existing KB content when the configured model version changes,
**so that** retrieval quality does not silently degrade as old vectors mix with new ones in the same collection.

### Current State
- No backfill job exists; coordinator workflow only embeds content during ingestion (`backend/agent/coordinator.py:1761-1864`).
- `EmbeddingMetadata` will gain `model_version` in embeddings.06 but nothing acts on a mismatch.
- **PM prereq cleanup (2026-06-23):** original prereqs additionally cited `agent.11` (claimed "generic backfill job runner") and `vectorstore.06`, but agent.11 = "store-level indexes + API pagination for workflow listing" and there is **no backfill-job-runner story** in agent.md; vectorstore.06 = "sharding/replication knobs". Both were dangling — dropped. This story builds its own `BackfillEmbeddingsJob` workflow module directly; the only real prerequisite is embeddings.06 (model_version stamping).

### Acceptance Criteria
- [ ] New module `backend/agent/workflows/embedding_backfill.py` defines a `BackfillEmbeddingsJob` that scans vectorstore records by `knowledge_base_id`, identifies records with `embedding_model_version != current_configured_version`, and re-embeds the source content.
- [ ] Job paginates with bounded batch size and emits progress events (`embeddings.backfill.progress`).
- [ ] Old vectors are replaced atomically per content_id (new record indexed first, old deleted only after successful index) to keep RAG live during backfill.
- [ ] Idempotent: re-running for the same KB and version is a no-op when no records mismatch.
- [ ] Job exposes a CLI entrypoint (`python -m agent.workflows.embedding_backfill --knowledge-base-id ...`) plus an API trigger gated by RBAC.
- [ ] Unit tests cover: mismatch found and re-embedded, no mismatch is no-op, partial failure leaves DB consistent, concurrent backfills are rejected per KB.

### Verification
- `uv run --project backend pytest backend/tests/agent/workflows/test_embedding_backfill.py -v` green.
- Manual: change configured model version, run backfill against dev KB, confirm vectorstore records updated and old version absent.
- Coverage gate: ≥ 85% on `agent` package for the new workflow.

### Code touch points
- `backend/agent/workflows/embedding_backfill.py` (new)
- `backend/agent/coordinator.py` (modify — wire CLI/event trigger)
- `backend/api/routers/embeddings.py` (modify — admin trigger endpoint)
- `backend/tests/agent/workflows/test_embedding_backfill.py` (new)

---

## Story embeddings.08: Dimension governance preflight across providers and vectorstore

**ID:** embeddings.08
**Status:** planned
**Prerequisites:** [embeddings.01, vectorstore.05]
**Unblocks:** [embeddings.09]
**Estimated size:** S
**Spec:** docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md

**As a** chiliAI operator deploying a new domain config,
**I need** startup to reject mismatches between the configured embedder model's actual dimensions and `EmbeddingsConfig.dimensions` / vectorstore collection dimensions,
**so that** a mis-set sentence-transformers model fails fast at boot instead of mid-batch in production.

### Current State
- `EmbeddingsConfig.dimensions` defaults to 384 and is independent from the actual model output (`backend/config/schema.py:128-137`).
- `DomainConfig` cross-checks vector-store dimension only when both sections are configured (`backend/config/schema.py:403-411`).
- Nothing verifies the embedder actually returns the configured dimension; a wrong-dimension model will only fail at first batch through `_parse_embedding_response`'s dimension assertion (`backend/embeddings/adapters/openai_adapter.py:268-273`).

### Acceptance Criteria
- [ ] `EmbeddingsService.validate_dimensions()` added; calls `embedder.get_model_info()` (embeddings.01) and compares against `EmbeddingsConfig.dimensions`.
- [ ] On boot, `get_embeddings_service()` (or an explicit startup hook in `api.app.create_app`) invokes `validate_dimensions()` and raises `EmbeddingConfigurationError` on mismatch with a clear remediation message.
- [ ] When vectorstore collection dimensions (from `vectorstore.05`) are queryable, the preflight also verifies they match.
- [ ] Preflight is opt-out only when `DomainConfig.embeddings.skip_dimension_preflight=True` (for offline/test contexts).
- [ ] Unit tests cover: matching dimensions (pass), mismatched embedder vs config (raise), mismatched config vs collection (raise), opt-out flag honored.

### Verification
- `uv run --project backend pytest backend/tests/embeddings backend/tests/config -v` green.
- Manual: set `dimensions=512` with `all-MiniLM-L6-v2` (real 384) and observe a clean startup failure.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/service.py` (modify)
- `backend/config/schema.py` (modify — add `skip_dimension_preflight`)
- `backend/api/app.py` (modify — wire startup hook)
- `backend/api/dependencies.py` (modify — optionally run on `get_embeddings_service`)
- `backend/tests/embeddings/` (modify)
- `backend/tests/config/` (modify)

---

## Story embeddings.09: Multi-model routing via per-KB embedder binding

**ID:** embeddings.09
**Status:** planned
**Prerequisites:** [embeddings.01, embeddings.08, knowledgebases.06]
**Unblocks:** []
**Estimated size:** L

**As a** multi-domain operator,
**I need** to bind a specific embedder model to a knowledge base at configuration time and dispatch requests to the right embedder based on the request's `knowledge_base_id`,
**so that** different KBs can use different embedding models without sharing collections or polluting vectors.

### Current State
- `EmbedRequest.model_name` is accepted but ignored: `get_embedder()` is `@lru_cache(maxsize=1)` and the service holds exactly one embedder (`backend/api/dependencies.py:531-572`, `backend/embeddings/service.py:30-49`).
- `EmbedRequest` carries `knowledge_base_id` but `EmbeddingsService` does not route on it (`backend/embeddings/service_models.py:25-42`).
- Vectorstore collections are dimension-pinned per KB today, so per-KB binding is the safer cut than request-time switching.

### Acceptance Criteria
- [ ] `EmbedderRegistry` class added in `backend/embeddings/registry.py`; constructed from `DomainConfig.knowledge_bases[*].embeddings` overrides plus the default `EmbeddingsConfig`.
- [ ] `EmbeddingsService` accepts an `EmbedderRegistry` (not a single `EmbedderProtocol`) and resolves the embedder by `request.knowledge_base_id` for each call; default embedder used when KB has no override.
- [ ] When a request specifies a `knowledge_base_id` with an override, the cache key from embeddings.02 incorporates the resolved model.
- [ ] Composition root builds the registry from config; `@lru_cache` widened to cache per-KB-id resolution.
- [ ] Backward compatibility: requests with no KB binding behave exactly as today.
- [ ] Unit tests cover: default-only registry (current behavior), per-KB override resolved correctly, unknown KB falls back to default, registry rejects two KBs binding the same model with different dimensions.

### Verification
- `uv run --project backend pytest backend/tests/embeddings backend/tests/api -v` green.
- Manual: configure two KBs with different models, embed against each, verify provider/model in `EmbedResponse`.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/registry.py` (new)
- `backend/embeddings/service.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/agent/coordinator.py` (modify — `build_embedder`)
- `backend/config/schema.py` (modify — `KnowledgeBaseConfig.embeddings` override)
- `backend/tests/embeddings/` (modify | new)

---

## Story embeddings.10: Warm sentence-transformers model loads and gate readiness

**ID:** embeddings.10
**Status:** planned
**Prerequisites:** [agent.09]
**Unblocks:** [analytics.22]
**Estimated size:** M

**As a** worker operator,
**I need** sentence-transformers models to be pre-loaded and the model cache directory persisted, with worker readiness gated until the load completes,
**so that** the first request after worker start does not block on a fresh HuggingFace download or model instantiation.

### Current State
- `_load_sentence_transformer_model` performs `importlib.import_module("sentence_transformers")` and constructs `SentenceTransformer(model_name)` on first adapter instantiation (`backend/embeddings/adapters/sentence_transformers_adapter.py:119-149`).
- `get_embedder()` is lazy and `@lru_cache`-wrapped — first request after worker start triggers the model download (`backend/api/dependencies.py:541-551`).
- No model-cache directory env var is enforced; no readiness gate delays traffic.

### Acceptance Criteria
- [ ] `SentenceTransformersEmbedder.warm()` method that performs the load and runs a 1-item dummy `embed` to materialize weights into memory.
- [ ] Composition root invokes `warm()` during worker startup (eager) when the configured provider is `sentence_transformers`.
- [ ] `HF_HOME` / `SENTENCE_TRANSFORMERS_HOME` honored from config or env; documented default mount point in `backend/embeddings/README.md`.
- [ ] Worker readiness probe (from `agent.09`) reports `not_ready` until warm completes; liveness remains green.
- [ ] Warm errors surface as `EmbeddingConfigurationError` with the model name in the message.
- [ ] Unit tests verify `warm()` is called once, idempotent, and that readiness flips from `not_ready` → `ready` after warm completes.

### Verification
- `uv run --project backend pytest backend/tests/embeddings backend/tests/agent -v` green.
- Manual: cold-start worker container with mounted model cache; verify first request latency < 100 ms and readiness probe reflects state.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/adapters/sentence_transformers_adapter.py` (modify)
- `backend/api/dependencies.py` (modify — wire warm)
- `backend/agent/coordinator.py` (modify — wire warm on startup)
- `backend/embeddings/README.md` (modify — document model cache)
- `backend/tests/embeddings/` (modify)

---

## Story embeddings.11: Fine-tuning hook for §14.2 model-training pipeline

**ID:** embeddings.11
**Status:** planned
**Prerequisites:** [analytics.18, storage.07]
**Unblocks:** [rag.10]
**Estimated size:** L

**As a** ML/analytics owner,
**I need** a fine-tuning hook in the embeddings module that produces a trained sentence-transformers checkpoint, persists it to object storage, and exposes it to `SentenceTransformersEmbedder` via a model path,
**so that** the §14.2 endgame model-training pipeline can deliver domain-tuned embedders without forking the embeddings module.

### Current State
- Nothing exists yet in `backend/embeddings/`; no `FineTuningJobProtocol`, no checkpoint artifact contract, no swap-in path for trained weights.
- `architecture.md §14.2` lists "embedding fine-tuning" as Medium-priority alongside scheduled GNN training (`docs/architecture.md:1358`).
- Sibling model-training pipeline lands in `analytics.18`.

### Acceptance Criteria
- [ ] `FineTuningJobProtocol` declared in `backend/embeddings/protocols.py` with `run(dataset, base_model, output_uri) -> FineTuningResult`.
- [ ] `FineTuningResult` model (request_id, base_model, output_uri, metrics, completed_at) added to `backend/embeddings/models.py`.
- [ ] `SentenceTransformersFineTuner` adapter in `backend/embeddings/adapters/` implements the protocol using sentence-transformers' training loop on a labeled pair dataset; gated by an optional `[fine-tuning]` extra in `pyproject.toml`.
- [ ] Trained checkpoint persisted via the object-storage adapter contracts from `storage.07`; artifact key shape `embeddings/fine-tunes/{job_id}/`.
- [ ] `SentenceTransformersEmbedder` accepts an optional `model_path` (local cache hydrated from object storage) and prefers it over a HuggingFace model id when supplied.
- [ ] Config addition: `EmbeddingsConfig.fine_tuned_artifact_uri` for runtime selection.
- [ ] Integration test (marked `@pytest.mark.integration`) runs a 5-pair tiny fine-tune end-to-end (skipped without the `[fine-tuning]` extra).

### Verification
- `uv run --project backend pytest backend/tests/embeddings -v` green for unit cases.
- `uv run --project backend pytest backend/tests/embeddings -m integration -v` green when extras installed.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/protocols.py` (modify)
- `backend/embeddings/models.py` (modify)
- `backend/embeddings/adapters/sentence_transformers_fine_tuner.py` (new)
- `backend/embeddings/adapters/sentence_transformers_adapter.py` (modify — accept `model_path`)
- `backend/config/schema.py` (modify)
- `backend/pyproject.toml` (modify — add `[fine-tuning]` extra)
- `backend/tests/embeddings/` (new test files)

---

## Story embeddings.12: Persist embedding artifacts to object storage for reproducibility

**ID:** embeddings.12
**Status:** planned
**Prerequisites:** [storage.04, agent.13]
**Unblocks:** []
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-19-embeddings-1-0-design.md

**As a** auditor / pipeline operator,
**I need** every multi-channel embedding artifact (text + graph vectors plus metadata) persisted to object storage with a stable key and retention,
**so that** a workflow re-run can replay vectors without recomputation and we have an audit trail of what was generated when.

### Current State
- `EmbeddingResult` is built and returned by `EmbeddingsService.embed` and consumed by `handle_embeddings_complete`, then discarded — the service-level `TODO(production)` flags this explicitly (`backend/embeddings/service.py:20-105`).
- `handle_embeddings_complete` indexes vectors directly into the vectorstore without writing the artifact (`backend/agent/coordinator.py:1761-1864`).
- `storage.04` will introduce the artifact-key conventions and adapter contracts this story uses.

### Acceptance Criteria
- [ ] `EmbeddingArtifactWriter` (new) in `backend/embeddings/artifact.py` accepts an `EmbedResponse` + request context and writes JSON to `embeddings/{knowledge_base_id}/{request_id}.json` via the object-storage adapter from `storage.04`.
- [ ] Artifact JSON shape: `{request_id, knowledge_base_id, model_name, model_version, dimensions, channels: {text: [...], graph: [...]}, graph_status, created_at}`; pinned by a JSON schema and a pydantic model.
- [ ] `EmbeddingsService.embed` invokes the writer (when configured) after publishing `embeddings.generated`; coordinator persists via the same writer in `handle_embeddings_complete`.
- [ ] Retention policy honored via storage adapter lifecycle (configured separately); writer never deletes.
- [ ] Replay helper `EmbeddingArtifactReader.load(request_id)` reconstructs an `EmbedResponse` from storage and is covered by tests.
- [ ] Unit tests cover: write happy path, write failure does not block embedding response (logged at WARN), replay round-trip.

### Verification
- `uv run --project backend pytest backend/tests/embeddings backend/tests/agent -v` green.
- Manual: run worker end-to-end; verify MinIO bucket contains the artifact at the expected key; replay through helper.
- Coverage gate: ≥ 85% on `embeddings` package.

### Code touch points
- `backend/embeddings/artifact.py` (new)
- `backend/embeddings/service.py` (modify)
- `backend/agent/coordinator.py` (modify — `handle_embeddings_complete`)
- `backend/config/schema.py` (modify — artifact storage flag)
- `backend/tests/embeddings/test_artifact.py` (new)
- `backend/tests/agent/` (modify)
