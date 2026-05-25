# Ingestion Pipeline E2E Demo Design

## Purpose

This spec describes the work needed to bring the chiliAI ingestion pipeline to a **demo-quality end-to-end state** for the medicare_fraud domain: a user can create a Knowledge Base, ingest real CMS provider data (NPPES, filtered to Tennessee) and synthetic Medicare claims (CMS DE-SynPUF, cross-filtered to the Tennessee NPI subset), have entities and relationships materialize in the graph, and have embeddings written to the vector index so the content is RAG-searchable. Production hardening of cross-cutting concerns (observability, tenant isolation, secrets management, IaC) is explicitly **out of scope** and will be specified separately.

Within the demo's bounded scope, the work also hardens the KB lifecycle: idempotent re-uploads, KB delete with cascading cleanup across graph + vector store + raw records + object store + KB metadata. These are demo-critical because the most common iteration loops are "fix a file and re-upload" and "reset the KB and start over."

The pipeline integrates two parallel ingestion flows that converge on a shared KB:

- **Documents flow** — PDF/DOCX/MD/JSON ingested via `POST /knowledgebases/{id}/documents`, chunked, then entity- and relationship-extracted by an LLM (cloud primary, local Ollama fallback). The synthetic policy corpus is **deferred**; the LLM extractor and its supporting infrastructure are built and unit/integration tested with two tiny markdown fixtures so the pipeline is exercised end-to-end. Notes for adding the real corpus later live in `docs/superpowers/specs/notes/synthetic-policy-corpus.md`.
- **Records flow** — CSV ingested via `POST /records/{kb_id}/files`, validated, landed in `raw_records`, then mapped to entities and relationships by per-feed mappers (NPPES, DE-SynPUF beneficiaries, DE-SynPUF inpatient/outpatient/carrier claims).

Both flows publish events on Redis Streams; the worker (`agent.coordinator`) consumes them, writes to the graph, and runs an embed-and-index step that writes to the vector store.

## Current State (Summary)

The existing scaffolding covers most of the pipeline mechanically:

- Event-driven architecture with Redis Streams transport and `agent.coordinator` worker.
- Modular parsers for PDF, DOCX, MD, JSON, CSV, XLSX (HTML stubbed).
- Generic config-driven entity/relationship validation in `shared.types`.
- Records pipeline with idempotent raw_records upsert by content hash, a feed mapper system, and a working CMS test against the existing medicare_fraud config.
- Graph adapters for in-memory and Neo4j; vectorstore adapters for in-memory and Qdrant; LLM adapters for OpenAI, Anthropic, and local.
- KB CRUD routes with live projection (entity/relationship counts from the graph).

The release gaps for this spec are:

- LLM-based entity extraction is stubbed (`PatternDocumentExtractor` is the working baseline). The stub `LlmDocumentExtractor` needs to be filled in.
- No Ollama LLM adapter exists.
- No mappers exist for NPPES or DE-SynPUF feeds, and the medicare_fraud config does not declare those feeds.
- No tooling exists to subset the 11 GB NPPES file or to cross-filter DE-SynPUF claims to a chosen NPI set.
- Re-upload idempotency is not enforced at the API surface; KB delete does not cascade across graph, vector store, raw records, and object store.
- The embed-and-index step is not wired into the records flow.

## Hard Architecture Requirements

This spec must not violate the cross-module rules established in `CLAUDE.md` and `docs/architecture.md`:

- All cross-module communication remains routed through the FastAPI gateway, the workflow coordinator, or the shared contracts library. No new direct cross-module imports.
- All external systems remain behind module-local `Protocol`s with adapters under `<module>/adapters/`. The new Ollama adapter follows the existing LLM adapter pattern.
- No hardcoded Medicare-specific domain classes. Provider, claim, and beneficiary are configured via `DomainConfig` entity definitions, validated against `shared.types.validate_entity`.
- `pyright --strict` clean, no `Any`, pytest coverage ≥ 85% per package.
- Frontend TypeScript strict mode and ESLint clean.
- Ollama is added to the `DomainConfig.llm.provider` literal **only after** the adapter and factory wiring exist and ship in the same increment (per the CLAUDE.md rule against premature roadmap-adapter literals).

## Target State

After the work in this spec lands, the demo flow is:

1. User creates a KB: `POST /knowledgebases` returns `kb_id`.
2. User runs `python -m tools.sample_data.build_tennessee_subset` to materialize `sample_data/CMS/tn_subset/` containing filtered NPPES + DE-SynPUF CSVs plus a `MANIFEST.json` capturing the filter strategy and provenance.
3. User POSTs the records files to the KB:
   - `nppes_providers_tn.csv` → `provider` entities (~25 000–35 000 expected for TN)
   - `desynpuf_beneficiaries_tn.csv` → `beneficiary` entities
   - `desynpuf_inpatient_claims_tn.csv`, `desynpuf_outpatient_claims_tn.csv`, `desynpuf_carrier_claims_tn.csv` → `claim` entities + `submitted_by` (claim→provider) + `beneficiary_of` (claim→beneficiary) relationships
4. (Once the deferred synthetic policy corpus exists) User POSTs policy documents; the worker extracts entities and relationships through the LLM extractor with Ollama fallback and writes them to the same KB graph.
5. The worker writes embeddings for all newly ingested chunks/records to the vector store; the KB becomes RAG-searchable.
6. User can `DELETE /knowledgebases/{kb_id}` and all graph + vector + raw record + object store + KB metadata state for that KB is removed.
7. User can re-upload any document or records file and the pipeline produces the same final state as a single fresh ingestion.

## Architecture

The pipeline keeps the existing layered structure and adds the following load-bearing pieces. Each piece either implements an existing protocol or follows a well-established pattern in its module.

```
                  ┌─────────────────────────────────────────────────┐
                  │              chili-app (React/Vite)             │
                  │  KB Manager: create / upload docs / upload      │
                  │              records / delete / view status     │
                  └────────────────────────┬────────────────────────┘
                                           │
                                  REST (api/)
                                           │
            ┌──────────────────────────────┼──────────────────────────────┐
            │                              │                              │
   POST /knowledgebases          POST /knowledgebases/{id}      POST /records/{kb_id}/files
                                  /documents                    (NPPES TN subset,
                                  (synthetic policies deferred)  DE-SynPUF TN-filtered)
            │                              │                              │
            ▼                              ▼                              ▼
       KB created event             DocumentsUploadedEvent       RecordsIngestedEvent
                                           │                              │
                                           └────────────┬─────────────────┘
                                                        │
                                                        ▼
                              ┌──────────────────────────────────────────┐
                              │   chili-worker (agent.coordinator)       │
                              │   • LlmDocumentExtractor                 │
                              │     (cloud LLM → Ollama fallback)        │
                              │   • Records feed_mapper (NPPES + DE-SynPUF) │
                              │   • GraphService.upsert_* (idempotent)   │
                              │   • EmbeddingService → VectorStore       │
                              │   • Cascade delete on KB removal         │
                              └──────────────────────────────────────────┘
                                       │                  │
                                       ▼                  ▼
                                  Graph (Neo4j)     VectorStore (Qdrant)
```

### Modules Touched

- **`backend/llm/`**
  - **New** `adapters/ollama_adapter.py` — `OllamaLlmClient` implementing the existing `LlmClient` protocol against a local Ollama HTTP endpoint.
  - **New** `service.py` (extend) — `FallbackLlmClient` decorator that wraps a primary client + ordered fallbacks and dispatches per a transient-error policy.
  - **Modified** `factory.py` — selects Ollama from `LlmConfig.provider == "ollama"`, constructs the fallback chain from `LlmConfig.fallback`.
  - **Modified** `protocols.py` / `service_models.py` — only if needed to surface the JSON-mode/structured-output flag uniformly across adapters.
- **`backend/ingestion/`**
  - **Modified** `extractor.py` — flesh out `LlmDocumentExtractor`. Reads `DomainConfig.entities` and `DomainConfig.relationships`, generates per-chunk prompts, parses JSON responses against a Pydantic schema derived from the entity definitions, validates each entity via `shared.types.validate_entity`, deduplicates within a document by configured natural key, and runs a follow-up relationship-extraction pass per chunk. Falls back to `PatternDocumentExtractor` when no LLM provider is configured.
  - **Unchanged** `service.py` (no orchestration change required; the existing extraction-strategy boundary already accommodates the LLM extractor).
- **`backend/records/`**
  - **New** `mappers/nppes.py` — `NppesProviderFeedMapper`. Maps an `npidata_pfile` row to a `provider` entity with NPI, organization/individual name, taxonomy, practice location, enumeration/deactivation dates. Companion mappers for `pl_pfile`, `othername_pfile`, `endpoint_pfile` produce satellite properties or relationships.
  - **New** `mappers/desynpuf.py` — `DeSynpufBeneficiaryFeedMapper` (beneficiary summary → `beneficiary`), `DeSynpufInpatientClaimFeedMapper`, `DeSynpufOutpatientClaimFeedMapper`, `DeSynpufCarrierClaimFeedMapper` (each row → `claim` + `submitted_by` + `beneficiary_of`).
  - **Unchanged** `service.py` (the feed-mapper registration system already supports adding new mappers without service changes).
- **`backend/graph/`**
  - **Modified** `service.py` — natural-key-based MERGE semantics on `upsert_entities`, `delete_knowledge_base(kb_id)` cascade, `delete_by_source_document(kb_id, document_id)` for re-upload, provenance fields (`source_kind`, `source_id`, `source_document_id`, `source_chunk_id`, `source_feed`, `source_raw_record_id`) propagated through every write.
  - **Modified** `adapters/neo4j_adapter.py` — implement the new operations using Cypher MERGE keyed on the configured natural key; ensure constraints/indexes exist for natural keys.
  - **Modified** `adapters/in_memory.py` — equivalent operations in-memory.
- **`backend/vectorstore/`**
  - **Modified** `service.py` — `delete_knowledge_base(kb_id)` (already in 1.0 contract per `2026-05-19-vectorstore-1-0-design.md`), `delete_by_source_document(kb_id, document_id)` for re-upload.
  - **Modified** adapters as needed to implement document-scoped delete via the existing `delete_record`/filter primitives. No new adapter behavior beyond what 1.0 already requires.
- **`backend/api/routers/knowledgebases.py`**
  - **Modified** `DELETE /knowledgebases/{id}` — orchestrates the cascade in order: workflow-busy check → graph → vector → raw_records → object store → KB metadata → publish `KnowledgeBaseDeletedEvent`. Returns 207 Multi-Status with per-step results on partial failure and writes a `pending_cleanup` marker for the worker to retry.
  - **Modified** `POST /documents` — re-upload semantics: detect existing `(filename, content_hash)`, invoke `delete_by_source_document` then re-ingest; advisory lock per `(kb_id, document_id)`; 409 if KB is in a non-idle workflow state.
  - **Modified** `POST /records/{kb_id}/files` — content-hash dedup returns a deterministic no-op; mapping still runs idempotently.
- **`backend/agent/coordinator.py`**
  - **Modified** `handle_documents_uploaded` — add the embed-and-index step after graph write.
  - **Modified** `handle_records_ingested` — add the embed-and-index step after graph write.
  - **New** `handle_knowledge_base_deleted` — retries any `pending_cleanup` markers left by the API delete orchestrator.
- **`backend/config/`**
  - **Modified** `schema.py` — add `"ollama"` to `LlmConfig.provider` literal once the adapter ships; add `LlmConfig.fallback: LlmConfig | None`; add `EntityDefinition.natural_key: list[str]`.
  - **Modified** `defaults/medicare_fraud_cms_desynpuf.yaml` — add `beneficiary` entity, `beneficiary_of` relationship, natural keys for all entities, feeds for NPPES + DE-SynPUF, `llm.provider: openai` + `llm.fallback.provider: ollama`.
- **`backend/shared/types.py`**
  - **Unchanged** for entity model itself; if any provenance field is exposed on `Entity`/`Relationship`, add it here so the contract is uniform.
- **`tools/sample_data/build_tennessee_subset.py` (new)**
  - One-shot CLI: streams NPPES → TN filter → satellite-file joins; loads DE-SynPUF claims; applies provider-NPI strategy (`--strategy={natural,remap,synthetic}`, default `remap`); cross-filters beneficiaries; writes outputs and `MANIFEST.json`. Idempotent.
- **`docs/superpowers/specs/notes/synthetic-policy-corpus.md` (new)**
  - Deferred-work notes describing what synthetic policy documents to author, suggested entity coverage, prompt templates for LLM-assisted authoring, and the pick-up checklist for a future implementer.

## Release Surface

After this spec lands, the public surface used by the demo is:

- `POST /knowledgebases` — create KB (unchanged behavior).
- `GET /knowledgebases/{kb_id}` — KB projection including entity/relationship counts and vector-indexed count (extended).
- `DELETE /knowledgebases/{kb_id}` — cascading cleanup, 207 on partial failure (**new behavior**).
- `POST /knowledgebases/{kb_id}/documents` — content-hash idempotent re-upload (**new behavior**).
- `POST /records/{kb_id}/files` — content-hash idempotent (existing) with mapping-side idempotency (**new guarantee**).
- `python -m tools.sample_data.build_tennessee_subset [--strategy=...] [--sample-rate=...]` — subset materializer (**new tool**).
- `make demo-tn-subset` — Make target that runs the subset build, creates a KB via the API, uploads the subset, and prints a summary (**new convenience target**).

The internal contracts gain:

- `LlmConfig.fallback: LlmConfig | None`
- `LlmConfig.provider: Literal["openai", "anthropic", "local", "ollama"]`
- `EntityDefinition.natural_key: list[str]`
- `Entity` / `Relationship` provenance fields: `source_kind: Literal["document", "record"]`, `source_id: str`, optional `source_document_id`, `source_chunk_id`, `source_feed`, `source_raw_record_id`.
- `GraphService.delete_knowledge_base(kb_id: str) -> GraphDeleteReport`
- `GraphService.delete_by_source_document(kb_id: str, document_id: str) -> GraphDeleteReport`
- `VectorService.delete_by_source_document(knowledge_base_id: str, document_id: str) -> VectorDeleteResponse` (in addition to the 1.0 `delete_knowledge_base`)
- `events.KnowledgeBaseDeletedEvent`

## Data Sources & Subsetting

### NPPES Tennessee Subset

- Input: `sample_data/npidata_pfile_<dates>.csv` (~11 GB), `pl_pfile`, `othername_pfile`, `endpoint_pfile`.
- Filter: rows where `Provider Business Practice Location Address State Name == "TN"` (or the equivalent NPPES column for the current schema version).
- Read the file in chunks (pandas `chunksize=50_000` or csv module streaming) to avoid loading all 11 GB into memory.
- Project a compact column set onto each output row (NPI, entity_type_code, organization_name, last_name, first_name, primary_taxonomy_code, practice_state, practice_city, practice_postal_code, enumeration_date, deactivation_date).
- Capture the set of TN NPIs in memory and use it to join satellite files.
- Outputs:
  - `sample_data/CMS/tn_subset/nppes_providers_tn.csv`
  - `sample_data/CMS/tn_subset/nppes_practice_locations_tn.csv` (from `pl_pfile`)
  - `sample_data/CMS/tn_subset/nppes_other_names_tn.csv` (from `othername_pfile`)
  - `sample_data/CMS/tn_subset/nppes_endpoints_tn.csv` (from `endpoint_pfile`)

### DE-SynPUF Cross-Filter

- Inputs: `Beneficiary_Summary_File_Sample_1` (per year), `Inpatient_Claims_Sample_1`, `Outpatient_Claims_Sample_1`, `Carrier_Claims_Sample_1A/B`, `Prescription_Drug_Events_Sample_1`.
- **Open implementation question (deliberately preserved for the build):** DE-SynPUF carrier claims contain provider NPI columns (`LINE_PRVDR_NPI_1`..`10`), and inpatient claims contain attending physician NPI (`AT_PHYSN_NPI`). Whether any of those NPIs are naturally present in the NPPES TN subset is not guaranteed because DE-SynPUF was synthesized independently. The tool must therefore support three strategies and the build will pick one based on inspection:
  - `natural` — keep only rows where some NPI naturally appears in the TN set. Lowest invasiveness, possibly very sparse output.
  - `remap` (**default**) — apply a deterministic hash-based remap of DE-SynPUF provider IDs onto the TN NPI set, so every kept claim references a real TN provider. Repeatable, dense output, but introduces synthetic linkage that must be flagged in the manifest.
  - `synthetic` — drop DE-SynPUF claim provider columns entirely and randomly assign each claim to a TN NPI per a configurable distribution.
- The chosen strategy is recorded in `MANIFEST.json` along with the source file paths, row counts before/after, and (for `remap`) a sample of the remap table.
- Cross-filter beneficiaries to those whose `DESYNPUF_ID` appears in the kept claims.
- Outputs:
  - `sample_data/CMS/tn_subset/desynpuf_beneficiaries_tn.csv`
  - `sample_data/CMS/tn_subset/desynpuf_inpatient_tn.csv`
  - `sample_data/CMS/tn_subset/desynpuf_outpatient_tn.csv`
  - `sample_data/CMS/tn_subset/desynpuf_carrier_tn.csv`
  - `sample_data/CMS/tn_subset/desynpuf_pde_tn.csv` (optional, included if PDE file is present)
  - `sample_data/CMS/tn_subset/MANIFEST.json`

### Sizing & Performance

- Target total subset size ≤ 500 MB so it ingests on the dev compose stack in under 10 minutes.
- The tool exposes `--sample-rate=<float>` to further random-sample claims when natural TN volume is too large.
- The tool is idempotent; re-running with the same inputs produces byte-identical outputs (modulo timestamps in the manifest).

### Synthetic Policy Corpus (Deferred)

- The LLM extraction path is built and tested with two tiny markdown fixtures under `backend/tests/ingestion/fixtures/policies/`.
- The real corpus is captured as a follow-up plan in `docs/superpowers/specs/notes/synthetic-policy-corpus.md`. A future implementer can pick it up without touching the platform code.

## KB Lifecycle Hardening

### Idempotency Contract

- Each `EntityDefinition` gains a required `natural_key: list[str]`. Examples in `medicare_fraud_cms_desynpuf.yaml`: `provider.natural_key = ["npi"]`, `claim.natural_key = ["claim_id"]`, `beneficiary.natural_key = ["beneficiary_id"]`.
- `GraphService.upsert_entities` uses the natural key for MERGE semantics: second write of the same logical entity is a no-op modulo property updates. Neo4j adapter creates unique constraints on natural-key properties at startup.
- `RawRecordStore.append` already dedupes on `content_hash` (existing behavior, kept).
- Document chunks deduplicated on `(document_id, chunk_index, content_hash)`.
- Vector store points are keyed by `(kb_id, source_kind, source_id, chunk_id)`; re-embedding overwrites cleanly.

### Re-Upload Semantics

- `POST /knowledgebases/{kb_id}/documents`: if a document with the same `(filename, content_hash)` exists in this KB, the API calls `GraphService.delete_by_source_document(kb_id, document_id)` and `VectorService.delete_by_source_document(...)` synchronously, then re-ingests. The response includes `replaced_document_id` so the caller knows it was a re-upload.
- `POST /records/{kb_id}/files`: existing content-hash dedup returns deterministic no-op for the raw_records row; the mapping step still runs, and because mapping is idempotent at the graph and vector layers, the net effect is no change.
- Concurrency: the API takes an in-process advisory lock per `(kb_id, document_id)` before delete+reinsert to prevent races. (Process-distributed coordination is deferred to prod hardening.)
- 409 Conflict if the KB has a non-idle workflow (per existing workflow tracker state) so the user is not allowed to delete-then-reinsert under an in-flight pipeline run.

### KB Delete Cascade

- `DELETE /knowledgebases/{kb_id}` performs:
  1. Workflow-busy check → 409 if non-idle.
  2. `GraphService.delete_knowledge_base(kb_id)`
  3. `VectorService.delete_knowledge_base(kb_id)`
  4. `RawRecordStore.delete_by_kb(kb_id)`
  5. Object-store cleanup under `kb/{kb_id}/`
  6. `KnowledgeBaseRepository.delete(kb_id)`
  7. Publish `KnowledgeBaseDeletedEvent`
- Steps execute in order, fail fast on the first transient failure of an *individual* step but continue to the next so the caller can see total state in the response. On any partial failure the API returns 207 Multi-Status with `{step, status, error}` entries, writes a `pending_cleanup` marker to KB metadata, and emits the deletion event with a `cleanup_pending: true` flag so the worker's `handle_knowledge_base_deleted` retries the residual steps.
- On full success the API returns 204 No Content.

## Error Handling

- **LLM extraction**: per-provider retry policy → on exhaustion fall through to `FallbackLlmClient` next provider. If all providers exhaust, emit `extraction.provider_chain_exhausted` metric, write a `failed_extraction` workflow event with stage info, mark the document `extraction_failed` in KB projection. Invalid JSON → one structured-output-mode retry with a stricter prompt → on second failure, drop the chunk (do not poison the graph) and log. Valid JSON with entities that fail `validate_entity` → drop only those entities, log dropped count, keep the rest.
- **Records validation**: existing behavior (skip + count + surface in `RecordsIngestionResponse.validation_errors[]`); no change.
- **Graph writes**: transient errors retried inside the adapter; constraint violations skipped + logged + counted (do not fail the whole batch); bulk failure (e.g. Neo4j down) bubbles up to the coordinator, which retries per existing workflow tracker policy, then lands in the DLQ with full context.
- **Vector store writes**: embedding-generation failure retried once, then logged; the entity remains in the graph, the vector index is partial, and the KB projection surfaces `vector_indexed_count < entity_count` so the user is aware. Vector-store-down behaves like graph-store-down (retry → DLQ).
- **Cascade delete**: 207 Multi-Status with per-step detail + worker-driven `pending_cleanup` retry (see KB Delete Cascade).
- **Deliberately deferred** to prod hardening: circuit breakers on LLM providers, dead-letter UI, per-tenant rate limiting.

## Testing Strategy

### Unit Tests

- `backend/llm/tests/test_ollama_adapter.py` — mocked `httpx`, contract conformance to `LlmClient`, JSON-mode handling, timeout/retry, error propagation.
- `backend/llm/tests/test_fallback_llm_client.py` — primary fails → fallback called; primary succeeds → fallback not called; both fail → chain-exhausted exception.
- `backend/ingestion/tests/test_llm_extractor.py` — schema generation from `DomainConfig`, JSON parsing, entity validation, dedup by natural key, relationship-pass behavior, fallback to `PatternDocumentExtractor` when no provider configured.
- `backend/records/tests/test_nppes_mapper.py` — row → entity transformation, edge cases (missing NPI, deactivated provider, invalid date).
- `backend/records/tests/test_desynpuf_mapper.py` — same for each DE-SynPUF feed mapper, including `submitted_by` and `beneficiary_of` relationship emission.
- `backend/graph/tests/test_graph_idempotency.py` — natural-key upsert semantics, double-write is a no-op modulo property updates, property update on re-upsert.
- `backend/graph/tests/test_graph_cascade_delete.py` — KB delete drops all KB-scoped state, leaves other KBs untouched, `delete_by_source_document` removes only entities/relationships with that provenance.
- `backend/vectorstore/tests/test_vectorstore_cascade_delete.py` — same for vector store, document-scoped delete removes only the matching points.
- `backend/api/tests/test_kb_delete_endpoint.py` — orchestration order, 409 on busy workflow, 207 on partial failure (mocked store failure), `pending_cleanup` marker written.
- `backend/api/tests/test_document_reupload.py` — POST twice with same hash → second call deletes then reinserts; `replaced_document_id` returned.
- `tools/tests/test_build_tennessee_subset.py` — fixture-scale tests on synthetic NPPES/DE-SynPUF micro-files; deterministic remap is stable; manifest fields populated.

### Integration Tests

- `backend/tests/records/test_cms_ingestion.py` — extend the existing test to exercise the TN subset (≤ 1 000 rows of each file checked into `backend/tests/records/fixtures/` to keep CI fast); assert graph entity/relationship counts; assert vector index has points.
- `backend/tests/ingestion/test_documents_e2e_with_ollama.py` — requires a local Ollama; uses two tiny markdown policy fixtures; asserts entities extracted, validated, persisted, embedded. Marked `@pytest.mark.integration` and skipped when `OLLAMA_BASE_URL` is unreachable.
- `backend/tests/api/test_kb_lifecycle_e2e.py` — create KB → upload doc → upload records → re-upload doc → assert dedup → delete KB → assert clean.

### End-to-End

- `backend/tests/e2e/test_full_pipeline.py` (extend) — build a mini TN subset on the fly from checked-in micro-fixtures (~20 rows each), create a KB, ingest, assert graph + vector + KB projection counts, search by RAG. Runs in `make test`.

### Coverage

- ≥ 85% per package, enforced by existing pytest-cov config. All new modules must clear the gate before merge.

## Build Sequence

Each increment ends green and is independently mergeable. Approach A (thin slice first, then thicken) — earliest increments exercise the seams; later increments deepen quality.

### Increment 1 — Thin Vertical Slice (no LLM, no real data)

- Add provenance fields to graph and vector contracts.
- Add `delete_knowledge_base` cascade to graph and vector store services and their adapters.
- Wire the embed-and-index step into `handle_records_ingested` in the coordinator.
- E2E test: create KB, POST a 3-row records CSV fixture, assert graph entities + vector points exist, DELETE KB, assert clean state.

### Increment 2 — KB Lifecycle Hardening

- `DELETE /knowledgebases/{id}` orchestrator with 207 Multi-Status partial-failure semantics and `pending_cleanup` retry path.
- Re-upload idempotency on `POST /documents` and `POST /records`.
- Advisory lock and 409-on-busy-workflow behavior.
- Unit and integration tests for the lifecycle behavior.

### Increment 3 — NPPES + DE-SynPUF Feed Mappers + Config

- Author the NPPES mapper(s) and DE-SynPUF mappers.
- Update `medicare_fraud_cms_desynpuf.yaml`: add `beneficiary` entity + `beneficiary_of` relationship, natural keys on all entities, feeds for NPPES providers + DE-SynPUF beneficiaries/claims, `llm.provider: openai`. The `llm.fallback.provider: ollama` line is deliberately deferred to Increment 5 because the `LlmConfig.provider` literal does not include `"ollama"` until that increment lands; adding it earlier would break config validation at load time.
- Unit tests on fixture-scale micro datasets.

### Increment 4 — Tennessee Subset Materializer

- `tools/sample_data/build_tennessee_subset.py` with `--strategy={natural,remap,synthetic}` and `--sample-rate` flags.
- Default strategy: `remap`.
- Manifest + idempotency.
- Smoke run: build the subset, run Increment 3's records flow against it.

### Increment 5 — Ollama Adapter + Fallback Chain

- `backend/llm/adapters/ollama_adapter.py` implementing the `LlmClient` protocol.
- `FallbackLlmClient` decorator + `LlmConfig.fallback` field.
- Factory wiring + `[ollama]` optional extra in `pyproject.toml` (no new third-party dependency — `httpx>=0.28` is already a direct dependency; the extra exists only to mark adapter intent and to give the factory a consistent feature gate alongside other adapters).
- Add `"ollama"` to the `LlmConfig.provider` literal **in this increment** (not earlier).
- Land the `llm.fallback.provider: ollama` line in `medicare_fraud_cms_desynpuf.yaml` here, now that the literal accepts it.
- Unit tests + integration test (skipped when no local Ollama).

### Increment 6 — `LlmDocumentExtractor`

- Flesh out the stubbed extractor as described in the architecture section.
- Add two tiny markdown policy fixtures under `backend/tests/ingestion/fixtures/policies/` so the integration test has real input.
- Tests.

### Increment 7 — End-to-End Demo Verification + Documentation

- Full E2E test exercising both records flow (TN subset) and documents flow (markdown fixtures) in the same KB.
- `make demo-tn-subset` Make target.
- Update READMEs: root, `backend/`, `backend/ingestion/`, `backend/records/`, `backend/graph/`, `backend/llm/`, `backend/vectorstore/`, `backend/agent/`.
- Update `docs/architecture.md` for the new provenance fields, lifecycle guarantees, and adapter inventory.
- Update `CLAUDE.md` adapter inventory to add Ollama.
- Write `docs/superpowers/specs/notes/synthetic-policy-corpus.md` for the deferred follow-up.

## Open Implementation Questions

These remain explicitly open at spec time and will be resolved during the build with documented rationale captured in the relevant PR or in the MANIFEST:

1. **DE-SynPUF provider linkage strategy** — `natural`, `remap`, or `synthetic`. Default is `remap`; final choice depends on how dense the natural overlap turns out to be when the actual files are inspected.
2. **Ollama default model** — `llama3.1:8b` and `qwen2.5:7b` are both reasonable candidates for the extractor's structured-output behavior. To be picked during Increment 5 based on a quick quality eyeball on the two policy fixtures.
3. **JSON-mode flag propagation** — whether the `format: json` request flag belongs on the `LlmClient` protocol as a typed argument or stays internal to the extractor → adapter contract. To be decided in Increment 5 once both cloud and Ollama adapters are side-by-side.

## Out of Scope (Deferred to Production Hardening Spec)

- Production-grade KB metadata DB (still on object store for the demo).
- Cross-tenant isolation.
- Real-time observability dashboards beyond the existing structured logs and metrics.
- Streaming LLM output.
- Risk scoring, alerts, evidence packs (separate downstream pipeline).
- Distributed/process-cluster advisory locking for re-upload (single-process in-memory lock for the demo).
- Production secrets management for `OLLAMA_BASE_URL`, API keys, etc.
- Authoring the actual synthetic policy corpus (captured in `docs/superpowers/specs/notes/synthetic-policy-corpus.md`).
