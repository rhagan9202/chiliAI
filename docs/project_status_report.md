# chiliAI — Project Status Report

> **Date**: April 17, 2026  
> **Compiled by**: Project Manager (synthesized from Code Quality Agent + Requirements Agent reviews)  
> **Team**: 4–5 engineers  
> **Release scope**: All capabilities — no phasing; single final release target

---

## Executive Summary

chiliAI is an **architecturally sound platform** at approximately **80% overall implementation**. The foundational patterns — hexagonal architecture, protocol-first design, domain reconfigurability, event-driven pipelines — are well-executed and consistent with `docs/architecture.md`. Backend modules are largely complete (RAG, monitoring, all four analytics sub-modules, optional production adapters for Neo4j/Qdrant/OpenAI/Anthropic/sentence-transformers/S3), and the frontend application is now feature-complete across all 13 E9 stories. Remaining gaps are primarily cross-cutting (auth/RBAC hardening, observability rollout, CI/CD, K8s/IaC) plus a handful of optional adapter wirings.

### Verdict

| Dimension | Rating |
|-----------|--------|
| **Architectural Integrity** | STRONG — protocols, adapters, boundaries respected |
| **Code Quality** | GOOD — types consistent, no contract slippage, clean boundaries |
| **Implementation Completeness** | HIGH (~80%) — backend pipelines + frontend application complete; remaining gaps are cross-cutting (auth, observability, CI/CD, K8s) |
| **Production Readiness** | PARTIAL — production adapters present (Neo4j, Qdrant, OpenAI, Anthropic, sentence-transformers, S3); auth scaffolded but not enforced; observability and CI/CD still pending |
| **Test Coverage** | STRONG — backend 822 tests / ~93% total coverage; frontend 53 vitest tests across stores, hooks, pages, and components |

---

## 1. Code Quality Findings

### 1.1 Contract Slippage — PASS

All protocol definitions in `protocols.py` files align with their service implementations. Method signatures, return types, and parameter types are consistent across:

- `ingestion`, `graph`, `embeddings`, `vectorstore`, `rag`, `llm`, `agent`, `monitoring` — protocols match services
- `shared/types.py` canonical types (`Entity`, `Relationship`, `Alert`, `KnowledgeBase`) used consistently — no shadow definitions

**One concern**: `shared/types.py` still has production TODOs on some platform records, mainly around a proper alert severity enum plus future `KnowledgeBase` ownership/config-version fields. These must be added before release.

### 1.2 Boundary Bleeding — PASS

No forbidden cross-module imports detected. Modules import only from `shared/` or their own internals. No hidden shared state, globals, or singleton leakage outside DI patterns. `api/dependencies.py` uses `@lru_cache` properly for singleton lifecycle.

### 1.3 Hexagonal Architecture — PASS (with coverage gaps)

Every external system has a proper protocol:

| System | Protocol | Production Adapter | Status |
|--------|----------|--------------------|--------|
| Graph DB | `GraphRepository` | Optional Neo4j adapter plus in-memory scaffolding | ⚠️ Optional dependency; integration requires configured Neo4j |
| Vector Store | `VectorStoreProtocol` | Optional Qdrant adapter plus in-memory scaffolding | ⚠️ Optional dependency; integration requires configured Qdrant |
| Object Storage | `ObjectStore` | Local filesystem adapter, optional S3/MinIO adapter, plus in-memory scaffolding | READY - config-driven API and coordinator selection wired; optional dependencies/env still required for S3-compatible stores |
| LLM | `LlmClientProtocol` | Optional OpenAI and Anthropic adapters plus in-memory scaffolding | READY - config-driven API and coordinator selection wired; provider credentials still required |
| Embeddings | `EmbedderProtocol` | Optional OpenAI and sentence-transformers adapters plus in-memory scaffolding | READY - config-driven API and coordinator selection wired; optional dependencies/env still required |
| Event Bus | `EventBus` | Redis Streams ✅ + InMemory ✅ | READY |

Business logic never imports vendor SDKs directly. DI wiring injects only via protocol types.

### 1.4 Design Drift — CONCERN

| Area | Drift | Impact |
|------|-------|--------|
| Missing API routers | ~~6 of 8 target routers not created (`alerts`, `investigation`, `rag`, `ws`, `analytics`, `evidence`)~~ Resolved 2026-04-26 in E5: routers/alerts, /investigation, /chat, /ws, /analytics, /knowledgebases (extended) all registered in `api/app.py`. Only `evidence_packs` router remains. | ~~Frontend cannot communicate with backend for critical paths~~ Frontend can now talk to all major backend resources. |
| Graph service query surface partial | Read/query methods now exist for entity lookup, neighborhood traversal, search, and metrics, but `get_subgraph` and production-backed query adapters are still missing | Investigation and RAG can proceed on in-memory scaffolding only |
| Agent coordinator incomplete | `steps.py` missing; multi-step state machine not fully wired | Event-driven orchestration loop incomplete |
| Production adapter matrix incomplete | Resolved for initial adapter selection: API DI and worker coordinator now select in-memory/local, Neo4j, Qdrant, S3/MinIO, OpenAI, Anthropic, and sentence-transformers adapters from config | Production deployment still depends on installed optional dependencies, credentials, and live service configuration |
| Analytics modules empty | All 4 sub-modules (`timeseries/`, `gnn/`, `risk/`, `explainability/`) contain only `__init__.py` | Flow B (Active Monitoring) cannot progress past graph/vector updates |

### 1.5 Vendor Lock-in — PASS

Zero direct vendor SDK imports in business logic. Redis-specific code isolated to `events/adapters/redis_streams.py`. Config sections and adapter interfaces are in place, and API/worker composition roots now select OpenAI, Anthropic, embeddings, vectorstore, graph, and storage adapters at runtime.

### 1.6 Consistency & Duplication — PASS

No shadow type definitions. UTC timestamp generation is consolidated through `shared.utils.utc_now()`, and the prior module-local `_utc_now()` helpers have been removed.

### 1.7 Overall Code Quality — GOOD

- Type annotations comprehensive and pyright-strict-ready (no `Any` found)
- Domain exceptions well-defined per module (`exceptions.py` in each)
- Tests use in-memory adapters properly (mock at adapter boundary)
- No dead code or unused imports detected
- No security vulnerabilities found (no SQL injection risk, no hardcoded secrets)

---

## 2. Module-by-Module Implementation Status

### Backend (16 modules)

| Module | Implementation | Tests | Coverage | Key Gap |
|--------|---------------|-------|----------|---------|
| **shared/** | 95% | ✅ | **97%** | Core audit fields are in place; remaining gaps are alert severity enum and KB metadata TODOs |
| **config/** | 97% | ✅ | ~98% | Config sections are defined; DI/runtime wiring still needs E1-S07 |
| **events/** | 90% | ✅ | **96%** | DLQ in protocol/in-memory/Redis; no XPENDING/XCLAIM fault tolerance |
| **ingestion/** | 85% | ✅ | **93%** | LLM-powered extraction deferred; no async I/O |
| **agent/** | 95% | ✅ | **87%** | Pipeline now reaches `kb.ready`: vector indexing, kb.ready, retry/backoff, DLQ routing, SIGTERM/SIGINT graceful shutdown, and stdlib `/health` endpoint all wired; durable retry state still in-process |
| **api/** | 80% | ✅ | **97%** | 7 of 8 target routers wired (config, knowledgebases, alerts, investigation, chat, analytics, ws); evidence-packs router still pending; no auth middleware; no file validation |
| **graph/** | 55% | ✅ | **90%** | In-memory and optional Neo4j adapters implemented; upserts use per-batch transaction semantics; live Neo4j integration requires configured test database |
| **vectorstore/** | 45% | ✅ | ~85% | In-memory and optional Qdrant adapters implemented; advanced metadata filtering remains future work |
| **embeddings/** | 55% | ✅ | **88%** | Optional sentence-transformers and OpenAI adapters implemented; DI/coordinator wiring remains future work |
| **storage/** | 50% | ✅ | **92%** for current storage tests | In-memory, local filesystem, and optional S3/MinIO adapters implemented; DI/coordinator provider selection and streaming upload remain future work |
| **llm/** | 45% | ✅ | **92%** | Optional OpenAI and Anthropic adapters implemented; DI/coordinator wiring and RAG integration remain future work |
| **rag/** | ~95% | ✅ | **~95%** | E6-S01..S08 complete: embed → retrieve → graph-expand → generate pipeline with citations, streaming, and domain-configurable system prompts; 88 tests covering all bridge adapters and error paths |
| **monitoring/** | ~95% | ✅ | **~99%** | E8-S01..S08 complete: time-window aggregation, deduplication, suppression rules, rate limiting, lifecycle state machine, alert grouping, and stream consumer wired into the coordinator (`risk.scored` → `MonitoringService.evaluate` → `alerts.created`). 64 tests covering all paths |
| **analytics/timeseries** | 95% | ✅ | **94%** | Z-score, STL decomposition, isolation forest, sliding window all wired (E7-S01..S03) |
| **analytics/gnn** | 95% | ✅ | **97%** | Node scoring, Louvain communities, Laplacian embeddings (E7-S04, E7-S05) |
| **analytics/risk** | 95% | ✅ | **96%** | Pluggable scoring strategies + temporal trend comparison (E7-S06, E7-S07) |
| **analytics/explainability** | 95% | ✅ | **96%** | Structured narrative + optional SHAP adapter (E7-S08, E7-S09) |

### Frontend

| Area | Status | Notes |
|------|--------|-------|
| Build tooling (Vite, TS, ESLint) | ✅ Ready | TS strict + ESLint clean; `npm run build` and `npm run lint` pass |
| Routing (React Router v7) | ✅ Done | `App.tsx` mounts dashboard, knowledgebases (+detail), alerts, investigation, chat, config, 404 under `AppShell` (E9-S01) |
| Pages | ✅ Done | Dashboard (E9-S05), KB Manager + detail/upload (E9-S06, S07), Alert Feed (E9-S08), Config Editor (E9-S09), Investigation Workbench (E9-S10, S11), RAG Chat (E9-S13) |
| API client (typed `apiClient.ts`) | ✅ Done | Hand-rolled fetch wrapper with typed envelopes in `lib/apiClient.ts` (E9-S03) |
| State management (Zustand) | ✅ Done | `appStore.ts` + `chatStore.ts`; covered by store unit tests (E9-S04) |
| Server state (TanStack Query) | ✅ Done | `lib/queryClient.ts` + per-resource hooks (`useKnowledgeBases`, `useAlerts`, `useEntity`, `useNeighborhood`, …) (E9-S03) |
| Graph visualization | ✅ Done | `react-force-graph-2d` canvas with type-coloured nodes, risk-scored sizing, edge tooltip, click-to-select wired to Zustand (E9-S10) |
| Investigation side panels | ✅ Done | EntityDetail, EvidencePanel (expandable), TimelinePanel; collapsible split layout (E9-S11) |
| WebSocket (real-time) | ✅ Done | `useWebSocket` hook with exponential-backoff reconnect (max 5 retries), keep-alive ping filter, typed event union (`WsAlertCreated`, `WsPipelineProgress`); `ConnectionStatus` indicator wired into Alert Feed (E9-S12) |
| Domain-driven dynamic UI | ✅ Done | `DomainConfigContext` fetches `/config/domain` at app boot; entity labels/icons/feature gates rendered from config (E9-S02) |
| Test coverage | ✅ 53 vitest tests passing | Stores, hooks (`useWebSocket`, `useDashboardMetrics`), pages (RagChat, ConfigEditor, InvestigationWorkbench), and core components (GraphCanvas, EntityDetail, Evidence, AlertTable, KbTable, KpiCard, DropZone, CreateKbForm) |

### Infrastructure

| Area | Status |
|------|--------|
| Dockerfiles (app, backend) | ✅ Ready |
| docker-compose.dev.yaml | ✅ Functional (all services) |
| docker-compose.yaml (prod) | ✅ Configured (4 workers, env_file) |
| Makefile (dev, test, clean, prod) | ✅ Ready |
| K8s manifests | ❌ 0% (`infra/` empty) |
| CI/CD (GitHub Actions) | ❌ 0% |
| Secrets management | ❌ Env vars only |
| TLS/HTTPS | ❌ Not configured |

---

## 3. Pipeline Status

### Flow A — Knowledge Base Creation: **~100% functional**

```
✅ POST /knowledgebases/{id}/documents → 202 Accepted
✅ Upload to object store → publish docs.uploaded
✅ Worker: docs.uploaded → parse → docs.parsed
✅ Worker: docs.parsed → chunk → docs.chunked
✅ Worker: docs.chunked → extract entities → entities.extracted
✅ Worker: entities.extracted → validate → entities.validated
✅ Worker: entities.validated → graph upsert → graph.updated
✅ Worker: graph.updated → embeddings.complete
✅ Worker: embeddings.complete → vectors.indexed
✅ Worker: vectors.indexed → kb.ready (terminal event)
✅ Failed events route to {stream}.dlq after retry exhaustion
✅ SIGTERM/SIGINT graceful shutdown; stdlib /health endpoint
```

**Verified in tests**: 9 event hops with retry/DLQ wrapping; full chain
covered by `test_full_pipeline_chain_documents_uploaded_through_kb_ready`.

### Flow B — Active Monitoring: **functional through `alerts.created` with continuous monitoring stage**

```
✅ Worker: graph.updated → handle_graph_updated_for_analytics (Flow B)
✅ Per upserted entity: GNN analyze → risk assess → explainability generate
✅ Coordinator writes risk_score, risk_level, risk_assessed_at,
   community_id, centrality_score back to graph entity properties
   (E7-S11 self-reinforcing loop)
✅ Worker: publishes alerts.created with severity + evidence_pack_id
✅ Failures emit analysis.failed without aborting Flow A (embeddings)
✅ Worker: risk.scored → handle_risk_scored → MonitoringService.evaluate
   (window aggregation, dedup, suppression, rate limit, grouping)
   → alerts.created (E8-S01..S07)
```

Remaining work (post-E8): WebSocket push of `alert.created` to frontend,
observability traces.

---

## 4. Critical Issues (Ranked)

### Tier 1 — Architectural Blockers (blocks multiple downstream features)

| # | Issue | Files Affected | Blocks | Effort |
|---|-------|----------------|--------|--------|
| ~~1~~ | ~~Production adapter wiring still incomplete~~ — **Resolved (E4-S08, April 26 2026)**: `agent/coordinator.build_worker_dependencies()` now selects object-store, graph, vector store, embeddings, and LLM adapters from `DomainConfig` via per-subsystem registries with lazy-imported optional adapters and `ConfigurationError` on misconfiguration. | `agent/coordinator.py` | — | — |
| ~~2~~ | ~~Vector indexing not wired in coordinator~~ — **Resolved (E4-S02 / S03, April 26 2026)**: `handle_embeddings_complete` upserts vectors into `VectorStoreProtocol` and publishes `vectors.indexed`; `handle_vectors_indexed` now publishes the terminal `kb.ready` event. | `agent/coordinator.py` | — | — |

### Tier 2 — Capability Gaps (blocks specific features)

| # | Issue | Files Affected | Blocks | Effort |
|---|-------|----------------|--------|--------|
| 5 | **Embeddings adapter wiring in DI/coordinator** | `api/dependencies.py`, `agent/coordinator.py` | End-to-end use of production embedding adapters | M (2-3 days) |
| 7 | **LLM production wiring** | `api/dependencies.py`, `agent/coordinator.py` | RAG answers, provider choice, end-to-end LLM usage | M (2-3 days) |
| 8 | **Production storage adapter (S3/MinIO)** | `storage/adapters/s3_adapter.py` | Adapter complete; DI/coordinator wiring still needed for runtime use | M (2-3 days) |
| ~~9~~ | ~~**RAG pipeline implementation + tests**~~ — **Resolved (E6-S01..S08, April 26 2026)**: full embed → retrieve → graph-expand → generate pipeline with citations, streaming, domain-configurable system prompts, and 88 tests / ~95% coverage. | ~~`rag/service.py`, `rag/adapters/`, new tests~~ | ~~RAG chat endpoint~~ | ~~L (4-5 days)~~ Done |
| 10 | ~~**6 missing API routers**~~ Resolved 2026-04-26 in E5: alerts, investigation, chat, ws, analytics, knowledgebases all wired in `api/app.py`. Only `evidence.py` remains. | ~~`api/routers/alerts.py`, `investigation.py`, `rag.py`, `ws.py`, `analytics.py`, `evidence.py` (all new)~~ | ~~Frontend API communication~~ | ~~L (4-5 days)~~ Done |
| ~~11~~ | ~~**Analytics: timeseries anomaly detection**~~ — **Resolved (E7-S01..S03, April 26 2026)**: z-score, STL decomposition, isolation forest, sliding window. | ~~`analytics/timeseries/...`~~ | — | — |
| ~~12~~ | ~~**Analytics: GNN link prediction + clustering**~~ — **Resolved (E7-S04, E7-S05, April 26 2026)**: Louvain community detection + spectral node embeddings. | ~~`analytics/gnn/...`~~ | — | — |
| ~~13~~ | ~~**Analytics: risk scoring**~~ — **Resolved (E7-S06, E7-S07, April 26 2026)**: pluggable `RiskScoringStrategyProtocol` with `LinearScoringStrategy` + temporal trend comparison. | ~~`analytics/risk/...`~~ | — | — |
| ~~14~~ | ~~**Analytics: explainability**~~ — **Resolved (E7-S08, E7-S09, April 26 2026)**: structured narrative grouping + optional SHAP adapter behind the `[analytics]` extra. | ~~`analytics/explainability/...`~~ | — | — |
| ~~15~~ | ~~**Monitoring service**~~ — **Resolved (E8-S01..S08, April 26 2026)**: window aggregation, dedup, suppression, rate limit, lifecycle state machine, grouping, and `risk.scored` stream consumer in the coordinator. | ~~`monitoring/service.py`, `consumer.py`, `alerting.py`~~ | — | — |

### Tier 3 — Quality & Operations

| # | Issue | Effort |
|---|-------|--------|
| 16 | **Test coverage for 5 zero-coverage modules** (rag, llm, analytics/*, monitoring) | L (5+ days) |
| 17 | **Observability** (structlog, Prometheus metrics, OpenTelemetry tracing) | M (2-3 days) |
| 18 | **Auth/RBAC middleware** (JWT/OIDC, role enforcement) | M (2-3 days) |
| 19 | **CI/CD pipeline** (GitHub Actions: lint + typecheck + test + build) | S (1-2 days) |
| 20 | **Input validation hardening** (file size limits, content-type whitelist, filename sanitization) | S (1 day) |
| 21 | **Utility consolidation** (`_utc_now()` duplication across 4+ files → `shared/utils.py`) | Complete |
| 22 | **Shared type follow-up** (severity enum, remaining KB metadata, future alert lifecycle polish) | S (0.5 days) |
| 23 | **K8s manifests + IaC** (deployments, services, configmaps, Helm/Terraform) | L (5+ days) |
| 24 | **Frontend — entire application** (routing, 6 pages, graph viz, API client, state mgmt, WebSocket) | XL (4-6 weeks) |

---

## 5. Gap-Closure Plan

### Team Allocation (4-5 engineers)

| Engineer | Focus Area | Duration |
|----------|-----------|----------|
| **E1** (Backend Lead) | Graph query API → production Neo4j adapter → analytics integration | Weeks 1-10 |
| **E2** (Pipeline) | Embeddings wiring → RAG implementation → LLM adapter → monitoring | Weeks 1-8 |
| **E3** (Adapters + Infra) | Config-driven DI → all production adapters → CI/CD → observability → auth | Weeks 1-10 |
| **E4** (Frontend Lead) | App shell → graph visualization → Investigation Workbench → all pages | Weeks 2-12 |
| **E5** (Analytics) | Risk scoring → timeseries → GNN → explainability → evidence packs | Weeks 3-12 |

### Phase 1: Foundation (Weeks 1-3)

**Objective**: Unblock all downstream work by closing architectural blockers.

| Task | Owner | Duration | Dependencies | Deliverable |
|------|-------|----------|-------------|-------------|
| 1.1 Graph query API (get_entity, query_neighborhood, search) | E1 | Complete | None | graph/service.py read methods + in-memory adapter + tests |
| 1.2 Config schema and initial adapter selection | E3 | Complete | None | config/schema.py subsystem sections plus config-driven API/worker selection for graph, vectorstore, storage, embeddings, and LLM adapters |
| 1.3 Embeddings wiring in coordinator | E2 | Complete | None | `agent/coordinator.py` handles `graph.updated` and emits `embeddings.complete` |
| 1.4 Shared type completion + utility consolidation | E2 | Complete | None | shared/types.py audit fields, shared/utils.py `utc_now()` |
| 1.5 CI/CD pipeline (GitHub Actions) | E3 | 2 days | None | Lint + typecheck + test + build on every PR |
| 1.6 Input validation hardening | E2 | 1 day | None | File size limits, content-type whitelist in routers |
| 1.7 Frontend app shell + routing | E4 | 3 days | None | React Router, layout, config fetching |
| 1.8 Neo4j graph adapter | E1 | Complete | 1.1 | graph/adapters/neo4j_adapter.py + integration tests |
| 1.9 Production vector adapter (Qdrant) | E3 | Complete | 1.2 | vectorstore/adapters/qdrant_adapter.py + tests |
| 1.10 Production LLM wiring | E2 | 3 days | 1.2 | `api/dependencies.py` and `agent/coordinator.py` provider selection |

**Exit criteria**: Graph read/write functional with Neo4j. Config selects adapters. Pipeline runs upload → graph → embeddings → vectors. CI green.

### Phase 2: Core Capabilities (Weeks 4-7)

**Objective**: Implement all service pipelines end-to-end.

| Task | Owner | Duration | Dependencies | Deliverable |
|------|-------|----------|-------------|-------------|
| 2.1 RAG pipeline implementation + tests | E2 | 5 days | 1.3, 1.9, 1.10 | Full embed→retrieve→expand→generate pipeline + 85% coverage |
| 2.2 API routers (alerts, investigation, rag, ws) | E1 | 5 days | 1.1, 1.8 | 6 new routers wired to services |
| 2.3 Production embeddings adapter (sentence-transformers) | E3 | Done | 1.2 | `embeddings/adapters/sentence_transformers_adapter.py` + tests |
| 2.4 Production storage adapter (S3/MinIO) | E3 | Done | 1.2 | `storage/adapters/s3_adapter.py` + tests |
| 2.5 Risk scoring engine | E5 | 4 days | 1.1, 1.8 | analytics/risk/scorer.py + tests + 85% coverage |
| 2.6 Timeseries anomaly detection | E5 | 6 days | 1.1, 1.8 | analytics/timeseries/detector.py + tests |
| 2.7 Monitoring service + alert generation | E2 | 3 days | 2.5 | monitoring/service.py, alerting.py + tests |
| 2.8 Frontend API client generation | E4 | 2 days | 2.2 | OpenAPI codegen + TanStack Query hooks |
| 2.9 Frontend graph visualization (library eval + impl) | E4 | 7 days | 2.2, 2.8 | GraphCanvas component with Cytoscape.js/Sigma.js |
| 2.10 Frontend KB Manager page | E4 | 3 days | 2.2, 2.8 | KB list, create, upload, document inventory |

**Exit criteria**: Flow A complete (upload → graph → embed → vector → kb.ready). RAG chat functional. Risk scores computed. Alerts generated. Frontend can list/create KBs and visualize graph.

### Phase 3: Analytics & Investigation (Weeks 8-10)

**Objective**: Complete analytics pipeline and investigation workbench.

| Task | Owner | Duration | Dependencies | Deliverable |
|------|-------|----------|-------------|-------------|
| 3.1 GNN link prediction | E5 | 6 days | 2.6 | analytics/gnn/link_prediction.py + tests |
| 3.2 GNN clustering | E5 | 4 days | 3.1 | analytics/gnn/clustering.py + tests |
| 3.3 Explainability / evidence packs | E5 | 4 days | 2.5, 3.1 | analytics/explainability/evidence.py + subgraph.py + tests |
| 3.4 Self-reinforcing analysis loop wiring | E1 | 3 days | 3.1, 3.3 | Analysis results → graph scores → next cycle |
| 3.5 Frontend Investigation Workbench | E4 | 8 days | 2.9, 2.2 | 4-panel layout: graph, entity detail, timeline, evidence |
| 3.6 Frontend Alert Feed page | E4 | 3 days | 2.7, 2.2 | Alert list, severity filters, ack workflow |
| 3.7 Frontend Dashboard page | E4 | 3 days | 2.2 | System overview, recent alerts, KB summaries |
| 3.8 WebSocket real-time push | E1 | 3 days | 2.2 | api/routers/ws.py + frontend WebSocket hook |
| 3.9 Observability (structlog, Prometheus, OpenTelemetry) | E3 | 3 days | None | Structured logging, /metrics endpoint, trace propagation |
| 3.10 Auth/RBAC middleware | E3 | 3 days | None | JWT validation, role enforcement, 3 roles |

**Exit criteria**: Flow B complete (claims → analytics → alerts → frontend). Investigation Workbench operational. Real-time alerts streaming. Observability in place.

### Phase 4: Hardening & Release (Weeks 11-12)

**Objective**: Production readiness, testing, and deployment.

| Task | Owner | Duration | Dependencies | Deliverable |
|------|-------|----------|-------------|-------------|
| 4.1 Frontend RAG Chat page | E4 | 3 days | 2.1, 2.2 | Chat input, message list, citations |
| 4.2 Frontend Config Editor page | E4 | 5 days | 2.2 | Visual domain config editor |
| 4.3 Test coverage gap closure (rag, llm, analytics, monitoring to 85%+) | E2+E5 | 5 days | Phase 3 | All modules at ≥85% coverage |
| 4.4 K8s manifests + Helm chart | E3 | 5 days | Phase 3 | Deployments, Services, ConfigMaps, Secrets |
| 4.5 Secrets management (Vault/K8s Secrets) | E3 | 2 days | 4.4 | Production secrets handling |
| 4.6 TLS/HTTPS (reverse proxy, cert management) | E3 | 2 days | 4.4 | TLS 1.3 for all connections |
| 4.7 Integration testing (full E2E pipeline) | ALL | 3 days | Phase 3 | E2E test: upload → ingest → graph → analytics → alert → frontend |
| 4.8 Performance testing + optimization | E1+E2 | 3 days | 4.7 | Load test; tune batch sizes, concurrency |
| 4.9 Documentation (API docs, module READMEs, runbook) | ALL | 2 days | Phase 3 | Auto-generated OpenAPI docs, deployment playbook |
| 4.10 Security audit + penetration testing | E3 | 2 days | 4.6 | Vulnerability scan, input fuzzing |

**Exit criteria**: All modules ≥85% coverage. E2E pipeline verified. Production deployment operational. Security hardened. Documentation complete.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **Analytics complexity exceeds estimates** (GNN, timeseries require ML expertise) | HIGH | HIGH | E5 must have ML background; consider simpler heuristic fallbacks if blocked |
| **Graph visualization library doesn't scale** (large graphs crash browser) | MEDIUM | HIGH | Prototype with representative dataset (1000+ nodes) in Week 4 before committing |
| **In-memory adapters leak into production** | MEDIUM | CRITICAL | Add runtime guard: reject in-memory adapters when `CHILI_ENV=production` |
| **Event pipeline reliability** (no dead-letter queue, no retry) | MEDIUM | HIGH | Implement dead-letter + XCLAIM in Phase 2; accept risk in Phase 1 |
| **Frontend scope creep** (Investigation Workbench is complex composite) | HIGH | MEDIUM | Strict scope: graph + entity detail + evidence panel only; defer timeline to follow-up |
| **Config schema migration** (no versioning, breaking changes) | LOW | MEDIUM | Add `version` field to DomainConfig now; document breaking changes |
| **Test coverage enforcement not automated** | HIGH | MEDIUM | CI/CD in Phase 1 (task 1.5) with coverage gates |

---

## 7. Timeline Summary

```
Week  1  2  3  4  5  6  7  8  9  10  11  12
      ├──────────┤├─────────────────┤├─────────┤├─────────┤
       Phase 1    Phase 2            Phase 3    Phase 4
       Foundation Core Capabilities  Analytics  Hardening
                                    & Invest.  & Release
```

| Milestone | Target | Go/No-Go Criteria |
|-----------|--------|-------------------|
| **M1**: Foundation Complete | End of Week 3 | Graph R/W with Neo4j; config-driven adapters; CI green; pipeline to embeddings |
| **M2**: Core Pipeline E2E | End of Week 7 | Flow A complete; RAG functional; risk scores; alerts generated; frontend KB Manager + graph viz |
| **M3**: Full Analytics | End of Week 10 | Flow B complete; investigation workbench operational; observability; auth |
| **M4**: Release Candidate | End of Week 12 | All modules ≥85% coverage; E2E verified; security hardened; docs complete |

**Total estimated duration**: 12 weeks (with 4-5 engineers working in parallel)

---

## 8. Decisions & Assumptions

| Decision | Rationale |
|----------|-----------|
| All capabilities in single release (no phasing) | Per PM directive; analytics, auth, observability all in-scope |
| Neo4j as first graph adapter | Most mature; community support; straightforward Bolt driver |
| Qdrant as first vector adapter | Good Python SDK; purpose-built for vector search |
| OpenAI as first LLM adapter | Widest API surface; most documented |
| sentence-transformers as first embeddings adapter | local/offline option; no API costs during development |
| Cytoscape.js as graph viz candidate | Mature; plugin ecosystem; evaluate in Phase 2 week 4 |
| Risk scoring before GNN | Simpler; unblocks alerts faster; GNN enriches later |
| Frontend starts week 2 | Needs backend API routers first; week 1 is app shell only |

---

## Appendix A: Files Requiring Modification

### New Files Required

- `api/routers/alerts.py` — Alert feed endpoints
- `api/routers/investigation.py` — Graph query endpoints
- `api/routers/rag.py` — RAG chat endpoints
- `api/routers/ws.py` — WebSocket hub
- `api/routers/analytics.py` — Analytics endpoints
- `analytics/timeseries/detector.py`, `models.py` — Time-series anomaly detection
- `analytics/gnn/link_prediction.py`, `clustering.py` — GNN analysis
- `analytics/risk/scorer.py` — Risk scoring engine
- `analytics/explainability/evidence.py`, `subgraph.py` — Evidence generation
- `monitoring/consumer.py`, `alerting.py` — Monitoring pipeline
- Tests for all new modules (in `tests/` subdirectories)
- Frontend: all pages, components, stores, hooks, API client (see architecture §8.2)
- `.github/workflows/ci.yml` — CI/CD pipeline
- `infra/` — K8s manifests / Helm chart

### Existing Files Requiring Modification

- `graph/service.py` — Add future `get_subgraph` support
- `graph/adapters/protocols.py` — Extend with query protocol methods
- `graph/adapters/in_memory.py` — Implement query methods
- `api/dependencies.py` — Extend backend selection as production adapters land
- `api/app.py` — Register new routers
- `agent/coordinator.py` — Wire embeddings handler + analytics handlers
- `shared/types.py` — Finish remaining shared-type TODOs (severity enum, KB metadata)
- `chili_app/src/App.tsx` — Replace template with app shell
- `chili_app/package.json` — Add dependencies (React Router, TanStack Query, Zustand, graph viz library)

---

## Appendix B: Test Coverage Targets

| Module | Current | Target | Gap |
|--------|---------|--------|-----|
| shared/ | ~90% | ≥85% | ✅ Met |
| config/ | ~65% | ≥85% | 20% gap |
| events/ | ~85% | ≥85% | ✅ Met |
| ingestion/ | 93% | ≥85% | ✅ Met |
| agent/ | 88% | ≥85% | ✅ Met |
| api/ | 97% | ≥85% | ✅ Met |
| graph/ | 90% | ≥85% | ✅ Met |
| vectorstore/ | ~85% | ≥85% | ✅ Met |
| embeddings/ | ~80% | ≥85% | 5% gap |
| storage/ | ~70% | ≥85% | 15% gap |
| llm/ | 0% | ≥85% | 85% gap |
| rag/ | ~95% | ≥85% | ✅ Met |
| monitoring/ | ~99% | ≥85% | ✅ Met |
| analytics/timeseries | 94% | ≥85% | ✅ Met |
| analytics/gnn | 97% | ≥85% | ✅ Met |
| analytics/risk | 96% | ≥85% | ✅ Met |
| analytics/explainability | 96% | ≥85% | ✅ Met |
