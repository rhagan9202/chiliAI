# chiliAI — Project Status Report

> **Date**: April 17, 2026  
> **Compiled by**: Project Manager (synthesized from Code Quality Agent + Requirements Agent reviews)  
> **Team**: 4–5 engineers  
> **Release scope**: All capabilities — no phasing; single final release target

---

## Executive Summary

chiliAI is an **architecturally sound early-stage scaffold** at approximately **30% overall implementation**. The foundational patterns — hexagonal architecture, protocol-first design, domain reconfigurability, event-driven pipelines — are well-executed and consistent with `docs/architecture.md`. However, significant capability gaps remain across 11 of 16 backend modules, the entire frontend, and all cross-cutting concerns (observability, security, CI/CD).

### Verdict

| Dimension | Rating |
|-----------|--------|
| **Architectural Integrity** | STRONG — protocols, adapters, boundaries respected |
| **Code Quality** | GOOD — types consistent, no contract slippage, clean boundaries |
| **Implementation Completeness** | LOW (~30%) — most modules are scaffolds or stubs |
| **Production Readiness** | NOT READY — no production adapters, no auth, no observability |
| **Test Coverage** | INCONSISTENT — 5 modules at 0%; 6 modules at 80%+ |

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
| Vector Store | `VectorStoreProtocol` | **MISSING** (in-memory only) | BLOCKED |
| Object Storage | `ObjectStore` | **MISSING** (in-memory only) | BLOCKED |
| LLM | `LlmClientProtocol` | **MISSING** (echo stub only) | BLOCKED |
| Embeddings | `EmbedderProtocol` | **MISSING** (MD5 stub only) | BLOCKED |
| Event Bus | `EventBus` | Redis Streams ✅ + InMemory ✅ | READY |

Business logic never imports vendor SDKs directly. DI wiring injects only via protocol types.

### 1.4 Design Drift — CONCERN

| Area | Drift | Impact |
|------|-------|--------|
| Missing API routers | 6 of 8 target routers not created (`alerts`, `investigation`, `rag`, `ws`, `analytics`, `evidence`) | Frontend cannot communicate with backend for critical paths |
| Graph service query surface partial | Read/query methods now exist for entity lookup, neighborhood traversal, search, and metrics, but `get_subgraph` and production-backed query adapters are still missing | Investigation and RAG can proceed on in-memory scaffolding only |
| Agent coordinator incomplete | `steps.py` missing; multi-step state machine not fully wired | Event-driven orchestration loop incomplete |
| Production adapter matrix incomplete | Domain configuration and DI selection are now wired, but most subsystems still only have in-memory adapters available | Production deployment still depends on implementing concrete vendor adapters |
| Analytics modules empty | All 4 sub-modules (`timeseries/`, `gnn/`, `risk/`, `explainability/`) contain only `__init__.py` | Flow B (Active Monitoring) cannot progress past graph update |

### 1.5 Vendor Lock-in — PASS

Zero direct vendor SDK imports in business logic. Redis-specific code isolated to `events/adapters/redis_streams.py`. Config-driven adapter selection is now implemented in the DI layer for the currently available adapter set.

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
| **events/** | 80% | ✅ | ~85% | No dead-letter queue; no XPENDING/XCLAIM fault tolerance |
| **ingestion/** | 85% | ✅ | **93%** | LLM-powered extraction deferred; no async I/O |
| **agent/** | 70% | ✅ | **88%** | Embeddings handler missing; no dead-letter; no durable state |
| **api/** | 40% | ✅ | ~80% | 6 of 8 routers missing; no auth middleware; no file validation |
| **graph/** | 35% | ✅ | **96%** | In-memory read/query methods implemented; no production adapters yet |
| **vectorstore/** | 30% | ✅ | ~85% | No production adapters; no metadata filtering |
| **embeddings/** | 20% | ✅ | ~80% | No production adapters; no configurable dimension/model |
| **storage/** | 30% | ⚠️ | ~70% | No S3/MinIO/local adapters; no streaming upload |
| **llm/** | 20% | ❌ | **0%** | No production adapters; 0 tests; no OpenAI/Anthropic/Ollama |
| **rag/** | 10% | ❌ | **0%** | Pipeline is pseudo-code; 0 tests; no error handling |
| **monitoring/** | 5% | ❌ | **0%** | Consumer + alert generation not implemented |
| **analytics/timeseries** | 0% | ❌ | **0%** | Empty module |
| **analytics/gnn** | 0% | ❌ | **0%** | Empty module |
| **analytics/risk** | 0% | ❌ | **0%** | Empty module |
| **analytics/explainability** | 0% | ❌ | **0%** | Empty module |

### Frontend

| Area | Status | Notes |
|------|--------|-------|
| Build tooling (Vite, TS, ESLint) | ✅ Ready | Scaffold correct |
| Routing (React Router v7) | ❌ 0% | Not set up |
| Pages (6 target) | ❌ 0% | `App.tsx` is template placeholder |
| API client (OpenAPI codegen) | ❌ 0% | No integration |
| State management (Zustand) | ❌ 0% | Not configured |
| Server state (TanStack Query) | ❌ 0% | Not configured |
| Graph visualization | ❌ 0% | Library not selected |
| WebSocket (real-time) | ❌ 0% | Not implemented |
| Domain-driven dynamic UI | ❌ 0% | `/config/domain` API ready but not consumed |

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

### Flow A — Knowledge Base Creation: **60% functional**

```
✅ POST /knowledgebases/{id}/documents → 202 Accepted
✅ Upload to object store → publish docs.uploaded
✅ Worker: docs.uploaded → parse → docs.parsed
✅ Worker: docs.parsed → chunk → docs.chunked
✅ Worker: docs.chunked → extract entities → entities.extracted
✅ Worker: entities.extracted → validate → entities.validated
✅ Worker: entities.validated → graph upsert → graph.updated
❌ STOPS HERE — embeddings step not wired
❌ No embedding generation after graph update
❌ No vector indexing
❌ No kb.ready event to frontend
```

**Verified in tests**: 7 event hops, 8 handlers, all passing (test_coordinator.py).

### Flow B — Active Monitoring: **0% functional**

All post-graph stages missing: analytics pipeline empty, monitoring service stubbed, alert generation not implemented, WebSocket push not wired.

---

## 4. Critical Issues (Ranked)

### Tier 1 — Architectural Blockers (blocks multiple downstream features)

| # | Issue | Files Affected | Blocks | Effort |
|---|-------|----------------|--------|--------|
| 1 | **Production adapter implementations still incomplete** — DI selection exists, but several subsystems still only expose in-memory adapters | `embeddings/adapters/*`, `llm/adapters/*`, `storage/adapters/*` | All production deployments; remaining real adapters | M (2-3 days) |
| 2 | **Embeddings not wired in coordinator** — pipeline stops after graph.updated | `agent/coordinator.py` | RAG chat, vector search, entire retrieval path | S (1 day) |

### Tier 2 — Capability Gaps (blocks specific features)

| # | Issue | Files Affected | Blocks | Effort |
|---|-------|----------------|--------|--------|
| 5 | **Production embeddings adapter (OpenAI or sentence-transformers)** | `embeddings/adapters/openai.py` or `sentence_transformers.py` (new) | Real embedding generation | M (2-3 days) |
| 7 | **Production LLM adapter (OpenAI/Anthropic)** | `llm/adapters/openai.py` (new) | RAG answers, entity extraction | M (2-3 days) |
| 8 | **Production storage adapter (S3/MinIO)** | `storage/adapters/s3.py` (new) | Persistent document storage | M (2-3 days) |
| 9 | **RAG pipeline implementation + tests** | `rag/service.py`, `rag/adapters/`, new tests | RAG chat endpoint | L (4-5 days) |
| 10 | **6 missing API routers** | `api/routers/alerts.py`, `investigation.py`, `rag.py`, `ws.py`, `analytics.py`, `evidence.py` (all new) | Frontend API communication | L (4-5 days) |
| 11 | **Analytics: timeseries anomaly detection** | `analytics/timeseries/detector.py`, `models.py` (new) | Anomaly detection alerts | L (6+ days) |
| 12 | **Analytics: GNN link prediction + clustering** | `analytics/gnn/link_prediction.py`, `clustering.py` (new) | Suspicious pattern detection | L (6+ days) |
| 13 | **Analytics: risk scoring** | `analytics/risk/scorer.py` (new) | Per-entity risk scores | M (3-4 days) |
| 14 | **Analytics: explainability** | `analytics/explainability/evidence.py`, `subgraph.py` (new) | Evidence packs for alerts | M (3-4 days) |
| 15 | **Monitoring service** | `monitoring/service.py`, `consumer.py`, `alerting.py` | Alert generation, Flow B | M (2-3 days) |

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
| 1.2 Config-driven adapter selection | E3 | Complete | None | config/schema.py subsystem sections + DI wiring |
| 1.3 Embeddings wiring in coordinator | E2 | 1 day | None | agent/coordinator.py handles embeddings.completed |
| 1.4 Shared type completion + utility consolidation | E2 | Complete | None | shared/types.py audit fields, shared/utils.py `utc_now()` |
| 1.5 CI/CD pipeline (GitHub Actions) | E3 | 2 days | None | Lint + typecheck + test + build on every PR |
| 1.6 Input validation hardening | E2 | 1 day | None | File size limits, content-type whitelist in routers |
| 1.7 Frontend app shell + routing | E4 | 3 days | None | React Router, layout, config fetching |
| 1.8 Neo4j graph adapter | E1 | Complete | 1.1 | graph/adapters/neo4j_adapter.py + integration tests |
| 1.9 Production vector adapter (Qdrant) | E3 | Complete | 1.2 | vectorstore/adapters/qdrant_adapter.py + tests |
| 1.10 Production LLM adapter (OpenAI) | E2 | 3 days | 1.2 | llm/adapters/openai.py + tests |

**Exit criteria**: Graph read/write functional with Neo4j. Config selects adapters. Pipeline runs upload → graph → embeddings → vectors. CI green.

### Phase 2: Core Capabilities (Weeks 4-7)

**Objective**: Implement all service pipelines end-to-end.

| Task | Owner | Duration | Dependencies | Deliverable |
|------|-------|----------|-------------|-------------|
| 2.1 RAG pipeline implementation + tests | E2 | 5 days | 1.3, 1.9, 1.10 | Full embed→retrieve→expand→generate pipeline + 85% coverage |
| 2.2 API routers (alerts, investigation, rag, ws) | E1 | 5 days | 1.1, 1.8 | 6 new routers wired to services |
| 2.3 Production embeddings adapter (sentence-transformers) | E3 | 3 days | 1.2 | embeddings/adapters/sentence_transformers.py + tests |
| 2.4 Production storage adapter (S3/MinIO) | E3 | 3 days | 1.2 | storage/adapters/s3.py + tests |
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

- `graph/adapters/neo4j_adapter.py` — Neo4j graph adapter
- `vectorstore/adapters/qdrant_adapter.py` — Qdrant vector adapter
- `embeddings/adapters/sentence_transformers.py` — sentence-transformers adapter
- `embeddings/adapters/openai.py` — OpenAI embeddings adapter
- `llm/adapters/openai.py` — OpenAI LLM adapter
- `llm/adapters/anthropic.py` — Anthropic LLM adapter
- `storage/adapters/s3.py` — S3/MinIO storage adapter
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
| api/ | ~80% | ≥85% | 5% gap |
| graph/ | ~50% | ≥85% | 35% gap |
| vectorstore/ | ~85% | ≥85% | ✅ Met |
| embeddings/ | ~80% | ≥85% | 5% gap |
| storage/ | ~70% | ≥85% | 15% gap |
| llm/ | 0% | ≥85% | 85% gap |
| rag/ | 0% | ≥85% | 85% gap |
| monitoring/ | 0% | ≥85% | 85% gap |
| analytics/timeseries | 0% | ≥85% | 85% gap |
| analytics/gnn | 0% | ≥85% | 85% gap |
| analytics/risk | 0% | ≥85% | 85% gap |
| analytics/explainability | 0% | ≥85% | 85% gap |
