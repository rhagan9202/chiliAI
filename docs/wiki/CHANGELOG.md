# Wiki CHANGELOG

---

## 2026-05-28 — Pass 6: Docs/Wiki Cleanup Validation

### Changes

**Code files read:** `backend/ingestion/parsers/registry.py`, `backend/ingestion/parsers/html.py`, `backend/api/routers/analytics.py`, `backend/api/dependencies.py`, `backend/events/types.py`, `backend/events/codec.py`, `backend/api/routers/rag.py`, `backend/api/app.py`, `backend/api/middleware/metrics.py`, `backend/api/routers/events.py`, `backend/api/routers/ws.py`, `backend/api/routers/policy.py`, `backend/agent/adapters/protocols.py`, `backend/agent/adapters/redis_store.py`, `backend/agent/workflow_tracking.py`, `backend/monitoring/service.py`, `backend/monitoring/service_models.py`, `backend/config/schema.py`, `backend/knowledgebases/`, `chili_app/src/app/router.tsx`, `chili_app/src/app/providers.tsx`, `chili_app/src/api/contracts.ts`, `chili_app/src/api/analytics.ts`, `chili_app/src/api/realtime.ts`, `chili_app/src/stores/uiStore.ts`

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/knowledgebases.md` | Added dedicated module page for `backend/knowledgebases/`, including repository protocol, document metadata model, in-memory/object-store adapters, and test locations |
| `modules/api.md` | Removed retired `_kb_store.py` ownership, documented `knowledgebases/` repository dependency, refreshed metrics/realtime route notes, and updated DI service list |
| `modules/ingestion.md` | Corrected HTML parser status: `HtmlParser` is registered; remaining backlog is richer heading/link/table fidelity |
| `modules/analytics.md` | Replaced stale router-local stub factory description with current `api/dependencies.py` analytics service wiring and remaining `ApiState` read-model gap |
| `modules/agent.md` | Added `update_run_if_current`, stale workflow reconciliation, and corrected Redis workflow-store status |
| `modules/monitoring.md` | Corrected threshold source: request overrides or `MonitoringConfig` defaults, not `AlertsConfig.thresholds` |
| `modules/frontend.md` | Replaced obsolete frontend type-drift table with generated OpenAPI contract status and refreshed router/provider/API notes |
| `modules/events.md` and `contracts/events.md` | Added `VectorsDeletedEvent` / `vectors.deleted` to the registered event surfaces |
| `contracts/api-routes.md` | Corrected analytics route paths/query parameters, `/events`/`/ws` paths, `/metrics`, and current analytics wiring status |
| `contracts/domain-config.md` | Added current repository/event/workflow runtime environment variables |
| `README.md` | Added the new `modules/knowledgebases.md` page to wiki navigation |

---

## 2026-05-22 — Pass 5: Refresh 10 Backlog Pages (Dev-Wiki-Curator)

### Changes

**Code files read:** `backend/shared/provenance.py`, `backend/ingestion/extractor.py`, `backend/ingestion/validator.py`, `backend/ingestion/service_models.py`, `backend/graph/protocols.py`, `backend/graph/models.py`, `backend/vectorstore/protocols.py`, `backend/vectorstore/service_models.py`, `backend/records/adapters/protocols.py`, `backend/records/mappers/feed_mapper.py`, `backend/agent/coordinator.py`, `backend/agent/workflow_tracking.py`, `backend/llm/factory.py`, `backend/llm/adapters/ollama_adapter.py`, `backend/llm/adapters/fallback.py`, `backend/api/routers/knowledgebases.py`, `backend/api/_kb_busy.py`, `backend/config/schema.py`, `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`, `backend/shared/types.py`

**Wiki pages updated:**

| Page | Gap closed |
|------|-----------|
| `modules/shared.md` | Added `shared/provenance.py` section with all 6 key constants and 2 value constants; documented usage pattern in document and records paths |
| `modules/graph.md` | Added `delete_by_source_document` to `GraphServiceProtocol`; fixed `get_entity`/`search_entities` to use `list[str]` KB IDs; added `GraphDeleteByProvenance` model; bumped date |
| `modules/vectorstore.md` | Added full `VectorServiceProtocol` surface (batch_search, get_record, count, delete_record, delete_knowledge_base, delete_by_source_document); added `VectorDeleteResponse` model; fixed `VectorSearchRequest.knowledge_base_ids` (now list); bumped date |
| `modules/records.md` | Added `RawRecordStore` adapter protocol section with `delete_by_kb`; updated `map_batch` docstring to note provenance stamping; added provenance table; bumped date |
| `modules/ingestion.md` | Added full `PatternDocumentExtractor` and `LlmDocumentExtractor` class docs with constructors; added `create_document_extractor` factory; added provenance stamping section; updated `DocumentReceipt` with `replaced_document_id`; bumped date |
| `modules/agent.md` | Expanded coordinator section with `create_llm_client` factory usage and `"kb.delete"` subscription; documented `handle_records_ingested` (embed-and-index step) and new `handle_knowledge_base_deleted` handler with full signatures; expanded `WorkflowEventTracker` with `is_busy` method; bumped date |
| `contracts/api-routes.md` | Updated `DELETE /knowledgebases/{kb_id}` to document 207/409 semantics and per-step body; documented idempotent re-upload flow and `replaced_document_id`; documented busy/pending_cleanup 409 guard and `api/_kb_busy.py`; bumped date |
| `contracts/domain-config.md` | Updated `LlmConfig` with `provider="ollama"`, `base_url`, `fallback`; added `medicare_fraud_cms_desynpuf.yaml` feed inventory, natural_key table, and llm section example; bumped date |
| `flows/ingestion-flow.md` | Updated step 4 to document `LlmDocumentExtractor` alongside `PatternDocumentExtractor`; updated step 5 to document provenance stamping; added "Idempotent Re-upload" section; updated source files list; bumped date |
| `flows/records-ingestion-flow.md` | Updated mapping phase to show provenance metadata on entities/relationships; added optional embed-and-index step in worker handler; updated Key Differences table with new Embedding and Provenance rows; updated source files list; bumped date |

---

## 2026-05-22 — Pass 4: Ingestion Pipeline E2E Demo Merge (feature/ingestion-pipeline-e2e-demo)

### Changes

**Code changes merged:** 47 commits covering LLM extractor, Ollama adapter, FallbackLlmClient, KB delete 5-step cascade, document re-upload idempotency, `delete_by_source_document` on graph+vector, `delete_by_kb` on raw records, provenance constants, NPPES/DE-SynPUF feed configs, vector embed+index in `handle_records_ingested`, and Tennessee subset tooling.

**Wiki pages updated:**

| Page | Changes |
|------|---------|
| `modules/llm.md` | Added Ollama adapter row to adapters table; added `FallbackLlmClient` and `create_llm_client` factory sections; updated verification date |
| `contracts/events.md` | Added `cleanup_pending: bool = False` field to `KnowledgeBaseDeletedEvent`; updated verification date |
| `contracts/shared-types.md` | Added `natural_key: list[str] = []` field to `EntityDefinition` with usage note; updated verification date |

**Ledger created:** `docs/ledger/` — module map, protocol contracts, event catalog, HTTP routes, config schema, tooling inventory.

### Deferred wiki updates (for next pass)

The following wiki pages are now stale against the 2026-05-22 merge and should be updated in a dedicated wiki-curator pass:

- `modules/ingestion.md` — should document `LlmDocumentExtractor`, `create_document_extractor` dispatcher, natural-key dedup
- `modules/agent.md` — should document enhanced `handle_records_ingested` (embed+index step) and `handle_knowledge_base_deleted` retry handler
- `modules/graph.md` — should document `delete_by_source_document` on service + adapter protocols
- `modules/vectorstore.md` — should document `delete_by_source_document` on service + adapter protocols
- `modules/records.md` — should document `delete_by_kb` on `RawRecordStore` + the 9-feed DE-SynPUF/NPPES config
- `modules/shared.md` — should document `shared/provenance.py` constants
- `contracts/api-routes.md` — should document 207 partial-failure semantics on `DELETE /knowledgebases/{id}`, `replaced_document_id` on document upload, `pending_cleanup` 409 guard
- `contracts/domain-config.md` — should document `LlmConfig.fallback`, `LlmConfig.base_url`, `LlmConfig.provider="ollama"`, `EntityDefinition.natural_key`
- `flows/ingestion-flow.md` — should add LLM extractor path and provenance metadata section
- `flows/records-ingestion-flow.md` — should add embed+index step to the handler description

---

## 2026-05-20 — Pass 3: Flow Refresh, AlertGroup, Risk Models, API Contracts, Frontend Drift

### Changes

**Code files read:** `backend/api/contracts.py`, `backend/api/dependencies.py`, `backend/monitoring/models.py`, `backend/analytics/risk/models.py`, `backend/records/service.py`, `backend/records/service_models.py`, `backend/records/mappers/feed_mapper.py`, `backend/events/types.py`, `backend/rag/service_models.py`, `backend/shared/types.py`, `backend/vectorstore/service_models.py` (partial), `chili_app/src/types/api.ts`, `chili_app/src/api/contracts.ts` (partial)

**Wiki pages updated:**

| Page | Changes |
|------|---------|
| `modules/monitoring.md` | Added full "Internal Models" section documenting `MonitoringObservation`, `MonitoringBatch`, `AlertCandidate`, `SuppressionRule`, `AlertGroup`, `AlertHistoryRecord` from `monitoring/models.py`; clarified `AlertGroup` reference in `MonitoringEvaluationResponse` |
| `modules/analytics.md` | Added "Internal Models" sub-section under `risk/` documenting `RiskSignal`, `RiskProfile`, `RiskFactor`, `RiskAssessmentResult`, `RankedRiskEntry`, `RiskAssessmentRecord` from `analytics/risk/models.py`; cross-linked to event wire shape `RiskFactorReference`; added cross-link from "Current Wiring Status" to `contracts/api-routes.md` static payload shapes section |
| `contracts/api-routes.md` | Added "Static payload shapes (api/contracts.py)" subsection under Analytics documenting `AnalyticsOverviewResponse`, `RiskFactorResponse`, `RiskScoreResponse`, `EntityTimeseriesPointResponse`, `EntityTimeseriesResponse`; documented `api/dependencies.py` dependency chain for entity-scoped routes; noted `RiskFactorResponse` drops `raw_value`/`weight` vs internal `RiskFactor` |
| `modules/frontend.md` | Added "Frontend ↔ Backend Type Drift" table comparing `src/types/api.ts` vs `shared/types.py` + `api/contracts.py`; documents 8 drift cases (3 safe optional extensions, 2 wire mismatches: `AlertListResponse` shape, `EvidencePack` vs `EvidencePackResponse`) |
| `flows/ingestion-flow.md` | Added "Event Payload Reference" table with exact wire shapes for all 9 document-pipeline events; added "Structured Records Path" section documenting the parallel synchronous records ingest flow; updated source files list |
| `flows/query-flow.md` | Fixed `RagQueryResponse` field list (added `knowledge_base_id`, `graph_summary`); clarified `RagAnswer.content` mapping from `RagQueryResponse.answer`; fixed `RagCompletedEvent` wire shape (event_type literal + `RagCompletionReference` fields) |
| `README.md` | Added `flows/records-ingestion-flow.md` to the Flows navigation table |

**Wiki pages created:**

| Page | Purpose |
|------|---------|
| `flows/records-ingestion-flow.md` | Full step-by-step flow for structured records ingestion: API → `RecordsService.register_records()` → `RecordsIngestedEvent` → worker mapper (`map_batch`, `map_observations`) → graph upsert + monitoring |

### Drift discovered

1. **`AlertListResponse` shape mismatch** (`chili_app/src/types/api.ts` vs `backend/api/contracts.py`): Frontend expects `{ items: Alert[], total: number }`; backend returns `{ items: list[AlertListItem], page: PageInfo }`. Frontend `Alert` is also missing `entity_label`, `confidence`, `tags` fields that backend `AlertListItem` carries. Documented in `modules/frontend.md` drift table.

2. **`EvidencePack` wire mismatch** (`chili_app/src/types/api.ts` vs `backend/api/contracts.py::EvidencePackResponse`): Frontend `EvidencePack` uses `subgraph_nodes`/`subgraph_edges` (matching internal `shared/types.py`), but the API route `/evidence-packs/{id}` returns `EvidencePackResponse` which uses `subgraph_node_ids`/`subgraph_edge_ids`. Frontend will read `undefined` for those fields. Also missing `items: list[EvidenceItemResponse]` and `policy_citations`. Documented in `modules/frontend.md` drift table.

3. **`RiskFactorResponse` field reduction** (`api/contracts.py`): The frontend-facing `RiskFactorResponse` exposes only `factor_name`, `contribution`, `rationale` — dropping `raw_value` and `weight` from internal `RiskFactor`. This is intentional API-boundary narrowing, not a bug. Noted in `contracts/api-routes.md`.

4. **`RecordsIngestedEvent` missing from flow docs** (prior gap): The structured records path had no flow documentation. Now covered in new `flows/records-ingestion-flow.md`.

---

## 2026-05-20 — Pass 2: UNVERIFIED Resolution + Frontend Decomposition + Investigation Router

### Changes

**Code files read:** `backend/graph/service_models.py`, `backend/graph/models.py`, `backend/vectorstore/service_models.py`, `backend/llm/service_models.py`, `backend/monitoring/service_models.py`, `backend/agent/models.py`, `backend/agent/adapters/protocols.py`, `backend/analytics/timeseries/protocols.py`, `backend/analytics/timeseries/service_models.py`, `backend/analytics/gnn/protocols.py`, `backend/analytics/gnn/service_models.py`, `backend/analytics/risk/protocols.py`, `backend/analytics/risk/service_models.py`, `backend/analytics/explainability/protocols.py`, `backend/analytics/explainability/service_models.py`, `backend/analytics/metrics/models.py`, `backend/analytics/metrics/adapters/protocols.py`, `backend/api/routers/analytics.py`, `backend/api/routers/investigation.py`, `backend/records/mappers/feed_mapper.py`, `backend/shared/exceptions.py`, `backend/shared/alerts.py`, `backend/events/codec.py`, `backend/rag/service_models.py`, `chili_app/src/app/router.tsx`, `chili_app/src/stores/appStore.ts`, `chili_app/src/stores/chatStore.ts`, `chili_app/src/stores/ingestionStudioStore.ts`, `chili_app/src/stores/uiStore.ts`, `chili_app/src/api/client.ts`, `chili_app/src/api/contracts.ts`, `chili_app/src/api/investigation.ts`

**Wiki pages updated:**

| Page | Changes |
|------|---------|
| `modules/graph.md` | Replaced UNVERIFIED service_models and models blocks with exact Pydantic field signatures for `GraphBuildTask`, `GraphBuildReceipt`, `NeighborhoodRequest`, `EntityDetailResponse`, `NeighborhoodResponse`, `EntitySearchResponse`, `GraphMetricsResult`, `GraphUpsertResult`, `SubgraphResult`, `GraphMetrics` |
| `modules/vectorstore.md` | Replaced UNVERIFIED service_models block with exact fields for `VectorIndexSubmission`, `VectorIndexRequest`, `VectorIndexReceipt`, `VectorSearchRequest`, `VectorSearchMatch`, `VectorSearchResponse` |
| `modules/llm.md` | Replaced UNVERIFIED service_models block with exact fields for `ChatMessageInput`, `PromptTemplate`, `GenerateRequest`, `CompletionResponse` |
| `modules/monitoring.md` | Replaced UNVERIFIED service_models block with exact fields for `MonitoringEvaluationRequest`, `MonitoringEvaluationResponse`, `AlertListRequest`, `AlertListResponse`, `ResolutionRequest`, `AlertActionResponse` |
| `modules/agent.md` | Replaced UNVERIFIED workflow run state block with exact Pydantic models (`RetryPolicy`, `HealthSettings`, `WorkflowStepStatus`, `WorkflowRunStatus`, `TERMINAL_RUN_STATUSES`, `WorkflowStepState`, `WorkflowRun`, `WorkflowRunUpdate`) and exact `WorkflowRunStoreProtocol` with all 6 methods |
| `modules/analytics.md` | Replaced all 5 UNVERIFIED protocol blocks and all UNVERIFIED model blocks; added exact service model shapes for all 5 sub-modules; added "Current Wiring Status" section documenting `@lru_cache` stub routing pattern and production gap |
| `modules/rag.md` | Replaced UNVERIFIED service_models block with exact fields for `RagQueryRequest`, `RagCitation`, `RagQueryResponse`, `RagAnswer`, `RagStreamChunk` |
| `modules/shared.md` | Replaced UNVERIFIED exceptions block (only `ConfigurationError` exists); replaced UNVERIFIED alerts block with exact `AlertSeverity` type and `normalize_severity` signature |
| `modules/events.md` | Replaced UNVERIFIED codec block with exact `encode_event`/`decode_event` signatures and full `EVENT_TYPE_REGISTRY` key list |
| `modules/records.md` | Added new "Mappers" section documenting `map_batch()`, `map_observations()`, `MappedGraph`, entity/relationship ID format, deduplication semantics; expanded directory structure listing |
| `modules/frontend.md` | Expanded from single-table treatment to full decomposition: exact Zustand store interface shapes (all 4 stores), page inventory with API calls and stores per page, API client function/hook list per module, shared component inventory by category |
| `contracts/api-routes.md` | Replaced UNVERIFIED investigation block with full route table (3 routes), request/response shapes, and drift note on `total` field; updated analytics wiring note with cross-link |

**Wiki pages created:**

| Page | Purpose |
|------|---------|
| `CHANGELOG.md` | This file — dated change log of wiki updates |

### UNVERIFIED markers resolved: 33 of 33 (all markers cleared)

### Drift discovered

1. **`EntitySearchResponse.total` in investigation router** (`api/routers/investigation.py:87`): `total` is set to `len(items)` — it reflects the returned slice count, not the true total match count. This breaks pagination use-cases. Documented as drift note in `contracts/api-routes.md`.

2. **Duplicate `selectedEntityId` across `appStore` and `uiStore`**: Both Zustand stores track this field independently. Potential for stale-state divergence in components that read from different stores. Documented as drift note in `modules/frontend.md`.

3. **Analytics router stub wiring** (`api/routers/analytics.py`): `@lru_cache(maxsize=1)` stub factories hardcode `kb-demo` data. The real analytics services are not wired to the API layer. Now documented in `modules/analytics.md — Current Wiring Status` and cross-linked from `contracts/api-routes.md`.

4. **`WorkflowRunStoreProtocol` TODO** (`agent/adapters/protocols.py:24`): Code comment explicitly notes durable adapters (`PostgresWorkflowRunStore`, `RedisWorkflowRunStore`) are not yet implemented. Documented as drift note in `modules/agent.md`.

---

## 2026-05-20 — Pass 1: Initial Wiki Build

Created 25 files under `docs/wiki/`: 17 module pages, 4 contract pages, 3 flow pages, 1 index (README.md). All pages stamped "Verified against codebase: 2026-05-20" with 33 UNVERIFIED markers deferred to Pass 2.
