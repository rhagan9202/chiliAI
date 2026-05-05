# TODO and Stub Audit - 2026-05-05

## Scope

Scanned the repository for explicit TODO markers and common stub/placeholder language. Dependency, build, and cache output was excluded: `.git`, `node_modules`, `backend/.venv`, `dist`, `build`, `__pycache__`, pytest/ruff caches, and `backend/chili_backend.egg-info`.

Commands used:

```bash
rg --hidden --line-number --glob 'backend/**/*.py' --glob '!backend/.venv/**' --glob '!backend/chili_backend.egg-info/**' 'TODO\(production\)' backend
rg --hidden --line-number --glob '!**/.git/**' --glob '!**/node_modules/**' --glob '!**/.venv/**' --glob '!backend/chili_backend.egg-info/**' --glob '!**/dist/**' --glob '!**/build/**' --glob '!**/__pycache__/**' '\b(FIXME|HACK|XXX|TBD)\b' .
rg --hidden --line-number --glob 'backend/**/*.py' --glob '!backend/.venv/**' --glob '!backend/chili_backend.egg-info/**' 'NotImplementedError|pytest\.skip|@pytest\.mark\.skip|@pytest\.mark\.xfail|pass\s*(#.*)?$' backend
rg --hidden --line-number --glob 'backend/**/*.py' --glob '!backend/.venv/**' --glob '!backend/chili_backend.egg-info/**' 'stub|Stubbed answer|stub-request|not yet implemented|not implemented' backend
rg --hidden --line-number --glob 'chili_app/src/**' -i 'stub|stubbed|placeholder|not implemented|disabled until|TODO|FIXME|HACK|XXX|TBD' chili_app/src
```

No `FIXME`, `HACK`, `XXX`, or `TBD` markers were found outside excluded directories.

## Summary

| Category | Count | Notes |
| --- | ---: | --- |
| Source `TODO(production)` markers | 48 | All are in backend Python source. |
| Runtime/product stubs or not-yet-implemented flows | 9 | Config save, evidence endpoint, analytics router defaults, RAG chat canned answer, LLM streaming defaults, test-only LLM echo adapter. |
| Test-only stubs/placeholders/skips | 26 | Mostly protocol test doubles, optional integration-test skips, and harmless `pass` statements. |
| Frontend UI placeholder matches | 21 | Mostly legitimate input placeholder text, empty states, CSS class names, and tests. |
| Historical documentation/planning references | Many | Existing audits, backlog files, and story prompts contain historical stub/TODO mentions; see final section. |

## Source TODO Inventory

| File:line | Area | Record |
| --- | --- | --- |
| `backend/agent/adapters/protocols.py:14` | Agent | Extend workflow run store with list, delete, and query methods. |
| `backend/agent/protocols.py:14` | Agent | Add workflow lifecycle methods such as status lookup and cancellation. |
| `backend/agent/service.py:17` | Agent | Add idempotency key to prevent duplicate workflow submissions. |
| `backend/analytics/explainability/adapters/protocols.py:14` | Explainability | Extend context source with batch loading and richer context queries. |
| `backend/analytics/explainability/service.py:30` | Explainability | Integrate SHAP/LIME for model-agnostic feature attribution. |
| `backend/analytics/gnn/adapters/protocols.py:14` | GNN | Extend graph snapshot source with incremental/streaming graph loading. |
| `backend/analytics/gnn/service.py:40` | GNN | Replace heuristic scoring with real GNN inference. |
| `backend/analytics/risk/adapters/protocols.py:14` | Risk | Extend risk signal source with batch loading and real-time signal streaming. |
| `backend/analytics/timeseries/adapters/protocols.py:15` | Timeseries | Extend history source with batch/streaming and date range filtering. |
| `backend/api/app.py:38` | API | Read allowed CORS origins from config or `ALLOWED_ORIGINS`. |
| `backend/api/routers/config.py:13` | API/config | Add config management endpoints, schema endpoint, reload endpoint, feature flags, caching headers, and audit logging. |
| `backend/config/loader.py:30` | Config | Support config overlay/merging, such as base plus environment-specific layers. |
| `backend/config/schema.py:179` | Config/monitoring | Extend monitoring settings with dedup window, max alerts per entity, and suppression rules. |
| `backend/embeddings/adapters/protocols.py:14` | Embeddings | Extend embedder protocol with model introspection and health methods. |
| `backend/embeddings/service.py:17` | Embeddings | Implement graph-metric embedding flow. |
| `backend/events/adapters/in_memory.py:43` | Events | Track consumer groups and pending message state so in-memory adapter mirrors Redis Streams semantics. |
| `backend/events/adapters/redis_streams.py:37` | Events | Add connection error handling with retry/backoff. |
| `backend/events/adapters/redis_streams.py:99` | Events | Add `XPENDING`/`XCLAIM` support for reprocessing stale messages. |
| `backend/events/codec.py:42` | Events | Replace manual event registry with auto-discovery from `EventBase` subclasses. |
| `backend/events/runtime.py:50` | Events | Wire event bus settings from `DomainConfig` YAML rather than only environment/defaults. |
| `backend/graph/adapters/in_memory.py:20` | Graph | Add referential integrity checks for relationships. |
| `backend/graph/adapters/protocols.py:16` | Graph | Extend adapter protocol with additional graph reads required by dashboard/investigation flows. |
| `backend/graph/protocols.py:16` | Graph | Add `get_subgraph(kb_id, entity_ids)` once repository adapters expose filtered subgraph reads. |
| `backend/graph/service.py:29` | Graph | Add service-level `get_subgraph` once repository adapters support it. |
| `backend/ingestion/extractor.py:36` | Ingestion | Replace regex-based baseline extractor with a production extractor. |
| `backend/ingestion/service.py:28` | Ingestion | Add idempotency checks and deduplicate by content hash. |
| `backend/ingestion/validator.py:20` | Ingestion | Add confidence-threshold filtering for extracted candidates. |
| `backend/llm/adapters/in_memory.py:13` | LLM | Test-only echo stub; production adapters need retries, timeouts, streaming, token usage, and safety metadata. |
| `backend/llm/adapters/protocols.py:14` | LLM | Extend adapter protocol with streaming, batch, and token counting methods. |
| `backend/llm/service.py:19` | LLM | Add provider retry/backoff, streaming support, token budget checks, capability registry, and fallback models. |
| `backend/monitoring/adapters/protocols.py:14` | Monitoring | Extend observation sources with streaming and real-time observation support. |
| `backend/monitoring/protocols.py:21` | Monitoring | Add async/streaming service methods for continuous monitoring. |
| `backend/rag/adapters/protocols.py:22` | RAG | Add retrieval min score, cursor pagination, and richer filter model. |
| `backend/rag/adapters/protocols.py:40` | RAG | Add graph expansion depth, entity type filters, and timeouts. |
| `backend/rag/adapters/protocols.py:55` | RAG | Add token budget awareness and citation formatting to answer generation. |
| `backend/rag/service.py:43` | RAG | Add retry/backoff around retrieval and generation failures. |
| `backend/shared/protocols.py:18` | Shared | Add cross-cutting protocols consumed by multiple modules. |
| `backend/shared/types.py:115` | Shared | Replace bare severity `str` with a `SeverityLevel` enum. |
| `backend/shared/types.py:127` | Shared | Remove deprecated `acknowledged` field in favor of `status`. |
| `backend/shared/types.py:144` | Shared | Enrich `EvidencePack` with structured fields. |
| `backend/shared/types.py:161` | Shared | Add `domain_config_version` to knowledge base records. |
| `backend/shared/utils.py:25` | Shared | Add cross-module utilities such as JSON serialization and retry helpers. |
| `backend/storage/adapters/in_memory.py:13` | Storage | Add thread-safety for concurrent access. |
| `backend/storage/models.py:25` | Storage | Add timestamps, etag/version id, storage class, and checksum fields. |
| `backend/storage/protocols.py:31` | Storage | Extend object store protocol with list, metadata, signed URL, and multipart methods. |
| `backend/vectorstore/adapters/protocols.py:14` | Vector store | Extend adapter protocol with CRUD and lifecycle operations. |
| `backend/vectorstore/protocols.py:19` | Vector store | Add delete and lifecycle methods. |
| `backend/vectorstore/service.py:23` | Vector store | Add delete flow for knowledge base teardown/reindexing. |

## Runtime/Product Stubs

| File:line | Behavior | Impact |
| --- | --- | --- |
| `chili_app/src/pages/ConfigEditor.tsx:7` | Save endpoint `PUT /config/domain` is not implemented; Save button is permanently disabled with tooltip. | Config editor is read-only except reset/reload. |
| `backend/api/routers/config.py:13` | Backend only exposes `GET /config/domain`; write/schema/reload/features endpoints are TODO. | Blocks full config editor workflow. |
| `chili_app/src/components/investigation/EvidencePanel.tsx:41` | Evidence endpoint is labeled not implemented and panel shows static placeholder data sourced from alert pipeline. | Investigation evidence is not backed by a persisted evidence-pack API. |
| `backend/api/routers/analytics.py:30` | Analytics router default dependencies are `_stub_*` in-memory sources. | Risk/timeseries/GNN API defaults are demo/local data unless dependencies are overridden. |
| `backend/rag/adapters/in_memory.py:132` | `InMemoryRagService` backs chat-router scaffold with canned answers. | Chat can return non-retrieved content. |
| `backend/rag/adapters/in_memory.py:143` | Default canned answer is `"Stubbed answer."`. | User-visible stub if real RAG service is not wired. |
| `backend/llm/service.py:77` | Default `LlmService.generate_stream()` raises `NotImplementedError`. | LLM streaming requires an adapter/service override. |
| `backend/llm/protocols.py:28` | Protocol default `generate_stream()` raises `NotImplementedError`. | Concrete LLM clients may omit streaming. |
| `backend/llm/adapters/in_memory.py:13` | In-memory LLM client is explicitly a test-only echo stub. | Valid for tests/local scaffolding, not production generation. |

## Test-Only Stubs, Skips, And Harmless Passes

These were recorded but are not product TODOs unless the project decides to remove test doubles.

| File:line | Record |
| --- | --- |
| `backend/tests/api/test_chat_router.py:25` | Deterministic `StubRagService` for chat router tests. |
| `backend/tests/api/test_chat_router.py:44` | Test stub `stream_answer()` raises `NotImplementedError`. |
| `backend/tests/rag/test_llm_bridge.py:33` | Protocol test double raises `NotImplementedError`. |
| `backend/tests/rag/test_graph_bridge.py:74` | Protocol test double raises `NotImplementedError`. |
| `backend/tests/analytics/gnn/test_service.py:133` | Test source method raises `NotImplementedError`. |
| `backend/tests/analytics/gnn/test_service.py:142` | Test source method raises `NotImplementedError`. |
| `backend/tests/analytics/risk/test_service.py:113` | Test source method raises `NotImplementedError`. |
| `backend/tests/analytics/risk/test_service.py:134` | Test source method raises `NotImplementedError`. |
| `backend/tests/analytics/timeseries/test_service.py:115` | Test source method raises `NotImplementedError`. |
| `backend/tests/analytics/timeseries/test_service.py:137` | Test source method raises `NotImplementedError`. |
| `backend/tests/analytics/timeseries/test_service.py:171` | Test source method raises `NotImplementedError`. |
| `backend/tests/analytics/timeseries/test_service.py:194` | Test source method raises `NotImplementedError`. |
| `backend/tests/graph/test_neo4j_adapter.py:428` | Integration test skip when Neo4j dependency is missing. |
| `backend/tests/graph/test_neo4j_adapter.py:434` | Integration test skip when Neo4j test env vars are missing. |
| `backend/tests/graph/test_neo4j_adapter.py:449` | Integration test skip when Neo4j test database is unavailable. |
| `backend/tests/storage/test_s3_adapter.py:180` | Integration test skip when optional dependency is missing. |
| `backend/tests/storage/test_s3_adapter.py:187` | Integration test skip when installed Moto lacks `mock_aws`. |
| `backend/tests/vectorstore/test_qdrant_adapter.py:241` | Integration test skip when `QDRANT_URL` is missing. |
| `backend/tests/shared/test_protocols.py:14` | Empty concrete test class uses `pass`. |
| `backend/tests/shared/test_tracing.py:49` | Intentional no-op body in trace test. |
| `backend/tests/shared/test_tracing.py:59` | Intentional no-op body in trace test. |
| `backend/tests/shared/test_tracing.py:75` | Intentional no-op body in trace test. |
| `backend/tests/shared/test_tracing.py:93` | Intentional no-op body in trace test. |
| `backend/tests/analytics/explainability/test_shap_adapter.py:243` | Intentional pass in optional import/branch path. |
| `backend/tests/e2e/conftest.py:209` | Placeholder dependency lambda not used by KB router. |
| `backend/tests/agent/test_coordinator.py:1539` | No-op test class body. |

## Frontend Placeholder Matches

These are mostly normal UI empty/loading states or form placeholder attributes, not implementation stubs.

| File:line | Record |
| --- | --- |
| `chili_app/src/components/chat/MessageInput.tsx:46` | Input placeholder text. |
| `chili_app/src/components/dashboard/__tests__/KpiCard.test.tsx:22` | Test for missing-value placeholder. |
| `chili_app/src/components/investigation/EntityDetailPanel.tsx:54` | Loading placeholder. |
| `chili_app/src/components/investigation/EntityDetailPanel.tsx:62` | Select-node placeholder. |
| `chili_app/src/components/investigation/EntityDetailPanel.module.css:44` | Placeholder CSS class. |
| `chili_app/src/components/investigation/EvidencePanel.tsx:44` | Product stub notice, also listed above. |
| `chili_app/src/components/investigation/EvidencePanel.tsx:48` | Select-node placeholder. |
| `chili_app/src/components/investigation/EvidencePanel.tsx:53` | Loading placeholder. |
| `chili_app/src/components/investigation/EvidencePanel.tsx:56` | Error placeholder. |
| `chili_app/src/components/investigation/EvidencePanel.tsx:61` | Empty evidence placeholder. |
| `chili_app/src/components/investigation/EvidencePanel.module.css:43` | Placeholder CSS class. |
| `chili_app/src/components/investigation/GraphCanvas.tsx:158` | Empty graph placeholder. |
| `chili_app/src/components/investigation/GraphCanvas.module.css:14` | Placeholder CSS class. |
| `chili_app/src/components/investigation/__tests__/EntityDetailPanel.test.tsx:26` | Placeholder behavior test. |
| `chili_app/src/components/investigation/__tests__/EvidencePanel.test.tsx:24` | Placeholder behavior test. |
| `chili_app/src/components/investigation/__tests__/EvidencePanel.test.tsx:37` | No-evidence placeholder behavior test. |
| `chili_app/src/components/investigation/__tests__/GraphCanvas.test.tsx:106` | DOM geometry stub for tests. |
| `chili_app/src/components/investigation/__tests__/GraphCanvas.test.tsx:167` | Empty graph placeholder behavior test. |
| `chili_app/src/hooks/useNeighborhood.ts:40` | TanStack Query `placeholderData`; normal cache behavior. |
| `chili_app/src/hooks/useWebSocket.ts:17` | Test injection comment for stub `WebSocket`. |
| `chili_app/src/pages/InvestigationWorkbench.tsx:185` | Search input placeholder text. |

## Documentation And Planning References

Historical planning and documentation files also contain TODO/stub language. I did not count these as source TODOs because most are backlog/story-prompt context, completed-story notes, or known-gap descriptions rather than executable code.

Notable documentation records:

| File | Notes |
| --- | --- |
| `chili_app/README.md` | Known prototype gaps: config save disabled, persisted evidence endpoint incomplete, graph/entity discovery incomplete, RAG chat may be stubbed/local. |
| `docs/archive/codebase_audit_2026-04-27.md` | Prior audit with production hardening TODOs and stubbed chat/evidence findings. |
| `docs/archive/config_engine_plan.md` | Historical plan to replace an inline config stub. |
| `docs/archive/graph_workflow_validation_2026-04-27.md` | Notes analytics placeholder caveat for some non-graph analytics inputs. |
| `docs/archive/planning/backlog.md` | Archived backlog references many placeholder/stub stories and states. |
| `docs/archive/planning/backlog_addendum.md` | Archived addendum references evidence endpoint, config save, Kafka stub, and related gaps. |
| `docs/archive/planning/story_prompts/` | Story prompt archive includes many historical "replace placeholder" and "stub" instructions, several marked complete. |
| `.github/prompts/` | Agent prompt templates include scaffold TODO examples and instructions, not product TODOs. |
| `infra/README.md` | Kubernetes worker HPA CPU value is documented as a placeholder. |
