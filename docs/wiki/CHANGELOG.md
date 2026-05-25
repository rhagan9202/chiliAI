# Wiki CHANGELOG

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
