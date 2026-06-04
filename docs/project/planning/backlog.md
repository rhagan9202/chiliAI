# chiliAI v1 Consolidated Backlog

> Owned by the Project Manager agent. The single source of truth for v1-scoped, prioritized work items.
> Version: 1 · Last updated: 2026-05-26
>
> This file is a **curated v1 backlog** that consolidates and prioritizes work derived from:
> - `docs/project/planning/requirements.md` (canonical requirements)
> - The 24 module backlogs under `docs/backlog/**` (395 raw stories — see [docs/backlog/README.md](../../backlog/README.md))
> - Drift items identified by the PM run on 2026-05-26
>
> The module backlogs remain the authoritative per-module breakdown. This file selects, prioritizes, and dependency-orders items for v1.

## Legend

- **Priority**: `P0` (v1 blocker, ship-stopping) · `P1` (v1 required, important) · `P2` (v1 nice-to-have) · `P3` (post-v1 / deferred)
- **Milestone**: `v1` · `v1.1` · `post-v1`
- **Status**: `todo` · `in-progress` · `done` · `blocked`
- **Drift origin**: links to a `D-XX` in the PM run drift table (when applicable)
- **Module source**: links the canonical module story (`docs/backlog/<module>.md#story-<id>`)

## Drift resolution summary (from 2026-05-26 PM run)

| Drift | Resolution | Backlog ID |
|---|---|---|
| D-01 KB snapshots/restore | ACCEPT-AS-BACKLOG | BL-020 |
| D-02 Graph backup/restore | ACCEPT-AS-BACKLOG | BL-021 |
| D-03 Live RAG service wiring | CODE-CHANGE (P0 v1-blocker) | **BL-001** |
| D-04 RAG citations/provenance | CODE-CHANGE (P0 v1-blocker) | **BL-002** |
| D-05 GNN PyG/DGL inference | ACCEPT-AS-BACKLOG (post-v1) | BL-030 |
| D-06 Evidence pack subgraph extraction | CODE-CHANGE (P1) — **RESOLVED** (Sprint 2026-23) | BL-005 |
| D-07 Evidence pack alert attachment | CODE-CHANGE (P1) — **RESOLVED** (Sprint 2026-23) | BL-006 |
| D-08 Mount GraphCanvas in workbench | CODE-CHANGE (P0 v1-blocker) | **BL-003** |
| D-09 OIDC hardening (JWKS rotation, id_token validation) | ACCEPT-AS-BACKLOG | BL-022 |
| D-10 CI dependency scanning | CODE-CHANGE (P1) | **BL-004** |
| D-11 Event replay operationalization | ACCEPT-AS-BACKLOG | BL-023 |
| D-12 Load testing / SLO baselines | ACCEPT-AS-BACKLOG | BL-024 |
| D-13 Config editor read-only polish | ACCEPT-AS-BACKLOG | BL-025 |
| D-14 Case Management surface | ADD-REQUIREMENT (REQ-CASE-*) + BL | BL-010 |
| D-15 Policy Intelligence surface | ADD-REQUIREMENT (REQ-POLICY-*) + BL — **RESOLVED (Sprint 2026-24)** | BL-011 |
| D-16 SSE/WebSocket transport policy | REQUIREMENT-CHANGE (REQ-UI-005 amended) | n/a |
| D-17 Two default configs ship | REQUIREMENT-CHANGE (REQ-CONFIG-001 amended) | BL-026 (test) |
| D-18 Postgres/TimescaleDB stack | No action | n/a |

---

## Reconciliation pass (2026-06-04)

A code-level audit of every non-done BL story was run on 2026-06-04 (statuses were systemically stale — multiple "in-progress" 8/13 SP stories were ~95% complete). Verified status and **genuine remaining** effort (judge from code, not the nominal estimate):

| BL | Story | Nominal | Verified status | Remaining | Notes |
|----|-------|---------|-----------------|-----------|-------|
| BL-012 | De-seed `ApiState` | 5 | partial ~30% | **~4–5 SP** | 6 `_seed_*` remain (`_seed_policy_gaps` already removed); needs conversation repo + workflow-store wiring + unwire graph/alerts detail |
| BL-013 | Ingestion Studio UI | 8 | **~95% done** | **~3 SP** | full studio shipped (9 components, 89 tests, wired); remaining = upload progress/retry + Playwright e2e |
| BL-014 | Ingestion E2E demo | 13 | **~95% done** | **~2 SP** | provenance, cascade delete, TN-subset tool + `make demo-tn-subset`, Ollama+fallback, LLM extractor, 6 e2e variants all done; remaining = synthetic policy corpus |
| BL-015 | Records submission dedup | 5 | partial | **~3 SP** | per-row hash + validation + DB dedup done; remaining = submission idempotency + format-rejection |
| BL-016 | Config save + wizard (write) | 8 | todo 0% | 8 SP | **contested** — conflicts with REQ-CONFIG-005 (read-only) + post-v1 hot-reload; needs requirements decision + design spec |
| BL-017 | Graph integrity + version/merge | 8 | todo 0% | 8 SP | explicit TODOs in both adapters; no integrity checks, no merge, no version conflict |
| BL-018 | Neo4j index strategy | 5 | **done** | 0 | `neo4j_adapter._ensure_schema` ships constraint + 4 indexes + fulltext |
| BL-019 | Embeddings + Vectorstore 1.0 hardening | 13 | partial ~50% | **~7 SP** | text+graph foundation, adapters, audit, events done; remaining = caching, retry, cost tracking, namespace lifecycle, arch guards |
| BL-020 | KB snapshots & restore | 8 | todo 0% | 8 SP | only an internal transport model; no snapshot repo/endpoints |
| BL-021 | Graph backup/restore | 5 | todo 0% | 5 SP | no export/restore on service or adapters |
| BL-022 | OIDC hardening (JWKS rotation, id_token) | 5 | partial ~30% | **~4 SP** | JWKS cache + aud/iss/exp present; remaining = kid-aware rotation, nonce/id_token validation, IdP templates, rotation tests |
| BL-023 | Event replay operationalization | 5 | partial ~35% | **~3 SP** | reclaim + DLQ-stream + retry done; remaining = DLQ persistence + replay API/script + runbook |
| BL-024 | Load testing & SLO baselines | 8 | todo 0% | 8 SP | no harness/benchmarks anywhere |
| BL-025 | Config editor (read-only) polish + tests | 2 | partial ~40% | **~2 SP** | `ConfigurationPage` renders read-only; no tests + minor polish |
| BL-027 | Resource-level per-KB ACL | 8 | todo 0% | 8 SP | no ACL model/middleware/endpoints; `KnowledgeBase` has no owner/acl |
| BL-028 | Multi-KB scope in RAG | 5 | todo 0% | 5 SP | request accepts a KB list but service projects to `[0]` (documented limitation) |

**Conclusion — the v1 *feature surface* is essentially complete; what remains is a hardening/DR/security-depth tail (mostly P2) plus the BL-012 de-seed.** All P0 + the P1 user-facing verticals (RAG, citations, graph canvas, evidence, cases, policy, ingestion studio, ingestion demo) are done or ~done. Remaining **P1 v1-required** work ≈ BL-012 (~5) + BL-013 (3) + BL-014 (2) + BL-015 (3) + BL-017 (8) + BL-019 (~7) ≈ **28 SP** (of which Sprint 2026-25 commits 13). Everything else is P2 nice-to-have or P3 post-v1. **Not yet reconciled:** the 24 module backlogs under `docs/backlog/**` (428 finer-grained stories) — a separate, lower-priority pass.

---

## P0 — v1 blockers

### BL-001 — Wire live RAG service (embed → retrieve → expand → generate)
- **REQ**: REQ-RAG-001, REQ-RAG-002
- **Drift**: D-03 (RESOLVED)
- **Module source**: [docs/backlog/rag.md#story-rag01](../../backlog/rag.md)
- **Status**: done (Sprint 2026-22)
- **Estimate**: 8 SP
- **Acceptance**:
  - `POST /rag/conversations/{id}/messages` calls a `RagService` that performs: embed query (via `embeddings.Service`), top-k retrieve (via `vectorstore.Service`), graph expand (via `graph.Service`), prompt assemble, LLM generate.
  - In-memory adapter no longer used in non-test code paths.
  - pyright --strict clean; pytest coverage ≥ 85% for `rag/`.
  - One e2e Playwright test sends a query in the RAG Chat surface and asserts a non-seeded answer.
- **Dependencies**: none (all collaborator services built).

### BL-002 — RAG citations & provenance
- **REQ**: REQ-RAG-003
- **Drift**: D-04 (RESOLVED)
- **Module source**: [docs/backlog/rag.md#story-rag03](../../backlog/rag.md)
- **Status**: done (Sprint 2026-22)
- **Estimate**: 3 SP
- **Acceptance**:
  - RAG answer payload includes a `citations: list[Citation]` field with chunk ids, document ids, and entity ids that contributed to the answer.
  - Frontend RAG Chat surface renders citations under each assistant message with click-through to entity detail.
  - Unit + e2e coverage.
- **Dependencies**: BL-001.

### BL-003 — Mount GraphCanvas in Investigation Workbench
- **REQ**: REQ-UI-004
- **Drift**: D-08 (RESOLVED)
- **Module source**: [docs/backlog/frontend.md#story-frontend01](../../backlog/frontend.md)
- **Status**: done (Sprint 2026-22)
- **Estimate**: 5 SP
- **Acceptance**:
  - `GraphCanvas.tsx` is mounted on `InvestigationWorkbenchPage` and loads neighborhoods via `GET /graph/entities/{id}/neighborhood`.
  - Entity click opens detail panel; relationship click highlights edge; depth selector wired.
  - Playwright e2e: search entity → click → see neighborhood render.
  - No accessibility regressions in axe scan of the page.
- **Dependencies**: none.

---

## P1 — v1 required

### BL-004 — CI dependency vulnerability scanning
- **REQ**: REQ-NFR-SEC-005
- **Drift**: D-10 (RESOLVED)
- **Module source**: [docs/backlog/_security.md](../../backlog/_security.md)
- **Status**: done (Sprint 2026-22)
- **Estimate**: 2 SP
- **Acceptance**:
  - GitHub Actions job runs `pip-audit` on `backend/` and `npm audit --omit=dev` on `chili_app/` on every PR and on a nightly schedule.
  - Job fails the PR on `HIGH` or `CRITICAL` findings; `MEDIUM` and below report but do not fail.
  - Findings posted as a PR check summary; nightly findings opened as issues.
- **Dependencies**: none.

### BL-005 — Evidence pack subgraph extraction
- **REQ**: REQ-ANALYTICS-005
- **Drift**: D-06
- **Module source**: [docs/backlog/rag.md#story-rag10](../../backlog/rag.md), [docs/backlog/monitoring.md](../../backlog/monitoring.md)
- **Status**: done (Sprint 2026-23)
- **Estimate**: 5 SP
- **Acceptance**:
  - `EvidencePack` is generated from alert context (seed entities + relationship traversal + metric snapshot) and persisted alongside the alert. ✅ `graph.get_subgraph` + risk factors/score → `ExplanationContext` → object-store `EvidencePackRepository`, written best-effort in the worker explainability stage.
  - Replaces seeded evidence pack data in API responses. ✅ `GET /evidence-packs/{id}` reads the repository (KB-scoped, 404 when absent); de-seed regression test added.
  - Tested with synthetic Medicare alert scenarios. ✅ `tests/agent/test_explainability_stage.py`.
- **Dependencies**: none.

### BL-006 — Evidence pack on alert UI
- **REQ**: REQ-ALERT-003
- **Drift**: D-07
- **Module source**: [docs/backlog/frontend.md#story-frontend02](../../backlog/frontend.md)
- **Status**: done (Sprint 2026-23)
- **Estimate**: 3 SP
- **Acceptance**:
  - Pack viewer renders subgraph (re-using GraphCanvas), metrics snapshot, and reasoning text. ✅ `EvidencePackViewer` (reasoning + metric chips + items + policy citations + subgraph via GraphCanvas) wired into the Investigation Workbench.
  - Evidence pack viewer shown when an alert is selected. ✅ in the Investigation Workbench **and** the Alert Feed (per-row "View evidence" toggle; `knowledge_base_id` added to `AlertListItem`/projection to scope the fetch). Playwright e2e: `alert-feed-evidence.spec.ts`.
- **Dependencies**: BL-003, BL-005.

### BL-010 — Case Management v1 surface
- **REQ**: REQ-CASE-001..004 (new)
- **Drift**: D-14
- **Status**: done (Sprint 2026-23)
- **Estimate**: 8 SP
- **Acceptance**:
  - Cases persisted via durable repository (in-memory + Postgres adapters). ✅ `backend/cases/` + `0002_cases` migration.
  - `POST/GET/PATCH /cases` endpoints with KB scoping. ✅ all routes take `?knowledge_base_id=`; plus `POST /cases/promote`.
  - Frontend `CaseManagementPage` lists, filters, and edits cases; supports "promote from alert". ✅ KB-threaded, status filter, status updates, toasts, promote-from-alert wired to `/cases/promote`.
  - pyright --strict, pytest ≥ 85%, Playwright e2e for promote-alert-to-case. ✅ (`case-promote.spec.ts`; case CRUD/feedback specs updated for KB scoping.)
- **Dependencies**: BL-005 (evidence pack on case).
- **Deferred to BL-012:** analytics `open_cases`/`list_policy_gap_cases` KB-scoping and removal of legacy `ApiState._seed_cases`; durable analyst feedback; rich `alerts[]` on case detail.

### BL-011 — Policy Intelligence v1 surface
- **REQ**: REQ-POLICY-001..004 (new)
- **Drift**: D-15
- **Status**: done (Sprint 2026-24)
- **Estimate**: 8 SP
- **Acceptance**:
  - Domain config schema extended with `policy_rules: list[PolicyRulePack]`. ✅ `DomainConfig.policy_rules: list[PolicyRulePack]` (additive, optional) in `config/schema.py`; example packs in `medicare_fraud.yaml` / `medicare_fraud_dev.yaml`.
  - Worker generates policy items from configured rules against KB state. ✅ `evaluation.evaluate()` (pure) called in `handle_records_ingested`; matches upserted as durable `PolicyItem`s via `PolicyService.record_match` (D-EVAL-IMPL: folded into record-ingest handler, no standalone stage; alert-target rules defined but not yet evaluated).
  - `GET /policy/items`, `GET /policy/items/{id}`, `POST /policy/items/{id}/triage` endpoints with KB scoping. ✅ all routes take `?knowledge_base_id=`; viewer for reads, analyst for triage. Old `/policy/gaps*` + `POST /policy/briefs` removed.
  - Frontend `PolicyIntelligencePage` rebuilt as an item queue + triage; `api/policy.ts` KB-scoped; contracts regenerated (not hand-written). ✅
  - Tests + e2e. ✅ unit tests for evaluation/service/repository + `tests/e2e/policy-triage.spec.ts`.
- **Dependencies**: BL-010 (escalate-to-case action).

### BL-012 — Replace seeded ApiState with real services across remaining endpoints
- **REQ**: REQ-RAG-002, REQ-ALERT-001, REQ-WORKFLOW-002
- **Module source**: [docs/backlog/api.md](../../backlog/api.md) (multiple stories)
- **Status**: done (Sprint 2026-25 — all six `_seed_*` removed; durable conversations module + migration 0005; analytics/graph-entity rewired; regression test enforces no `_seed_*` outside tests)
- **Estimate**: 5 SP
- **Acceptance**: ApiState seeded data fully removed from non-test code paths; replaced with durable repositories.

### BL-013 — Ingestion Studio UI/UX (file upload progress, retry)
- **REQ**: REQ-KB-002, REQ-KB-004
- **Plan**: [docs/superpowers/plans/2026-05-17-ingestion-studio-ui-ux-implementation.md](../../superpowers/plans/)
- **Status**: in-progress — **~95% done** (verified 2026-06-04; full studio shipped + 89 tests). **done (Sprint 2026-25)** — XHR upload progress + retry, receipt counts, ingestion-records e2e.
- **Estimate**: 8 SP (nominal) — **~3 SP remaining**

### BL-014 — Ingestion pipeline E2E demo (TN Medicare subset)
- **REQ**: REQ-KB-003, REQ-REC-001..004, REQ-RAG-002
- **Plan**: [docs/superpowers/plans/2026-05-22-ingestion-pipeline-e2e-demo.md](../../superpowers/plans/)
- **Status**: in-progress — **~95% done** (verified 2026-06-04; provenance, cascade delete, TN-subset tool + `make demo-tn-subset`, Ollama+fallback, LLM extractor, 6 e2e variants). **done (Sprint 2026-25)** — 17-doc synthetic policy corpus + policy/procedure_code/regulation_section config entities + demo/e2e wiring.
- **Estimate**: 13 SP (nominal) — **~2 SP remaining**

### BL-015 — Records submission-level dedup + format enforcement
- **REQ**: REQ-REC-001, REQ-REC-003
- **Module source**: [docs/backlog/records.md](../../backlog/records.md) stories records.01, records.02
- **Status**: partial (verified 2026-06-04 — per-row hash + validation + DB record-ID dedup done). **done (Sprint 2026-25)** — submission-hash dedup (migration 0004) + per-row format-rejection + typed receipt + accepted_formats 415 gate.
- **Estimate**: 5 SP (nominal) — **~3 SP remaining**

### BL-016 — Configuration save endpoint + wizard
- **REQ**: REQ-CONFIG-005
- **Module source**: [docs/backlog/config.md](../../backlog/config.md), [docs/backlog/frontend.md#story-frontend03](../../backlog/frontend.md)
- **Estimate**: 8 SP

### BL-017 — Graph referential integrity + version/merge semantics
- **REQ**: REQ-GRAPH-001
- **Module source**: [docs/backlog/graph.md](../../backlog/graph.md) stories graph.01, graph.02
- **Estimate**: 8 SP

### BL-018 — Neo4j index strategy for scale
- **REQ**: REQ-NFR-SCALE-PROD
- **Plan**: [docs/superpowers/plans/2026-05-21-neo4j-graph-indexes.md](../../superpowers/plans/)
- **Status**: done (verified 2026-06-04 — `neo4j_adapter._ensure_schema` ships the constraint + 4 indexes + fulltext)
- **Estimate**: 5 SP

### BL-019 — Embeddings 1.0 + Vectorstore 1.0 hardening
- **REQ**: REQ-VEC-001..004
- **Plans**: [docs/superpowers/plans/2026-05-19-embeddings-1-0.md](../../superpowers/plans/), [docs/superpowers/plans/2026-05-19-vectorstore-1-0.md](../../superpowers/plans/)
- **Estimate**: 13 SP

---

## P2 — v1 nice-to-have

### BL-020 — KB snapshots & restore (D-01)
- **REQ**: REQ-KB-007, REQ-NFR-DR-001
- **Module source**: [docs/backlog/knowledgebases.md](../../backlog/knowledgebases.md) story knowledgebases.07
- **Estimate**: 8 SP

### BL-021 — Graph backup/restore procedures per adapter (D-02)
- **REQ**: REQ-GRAPH-006, REQ-NFR-DR-002
- **Module source**: [docs/backlog/graph.md](../../backlog/graph.md) story graph.11
- **Estimate**: 5 SP

### BL-022 — OIDC hardening: JWKS rotation, full id_token validation (D-09)
- **REQ**: REQ-AUTH-001
- **Module source**: [docs/backlog/_security.md](../../backlog/_security.md) story _security.01
- **Estimate**: 5 SP

### BL-023 — Event replay operationalization (D-11)
- **REQ**: REQ-WORKFLOW-005, REQ-NFR-DR-003
- **Module source**: [docs/backlog/events.md](../../backlog/events.md)
- **Estimate**: 5 SP

### BL-024 — Load testing & SLO baselines (D-12)
- **REQ**: REQ-NFR-SCALE-PROD
- **Estimate**: 8 SP
- **Notes**: Establishes the latency/throughput targets currently held as `[ASSUMPTION]` in requirements.

### BL-025 — Configuration editor (read-only) polish + tests (D-13)
- **REQ**: REQ-CONFIG-005
- **Estimate**: 2 SP

### BL-026 — Test coverage for both default configs loading (D-17)
- **REQ**: REQ-CONFIG-001
- **Status**: done (Sprint 2026-22 — pre-completed; `tests/config/test_loader.py` covers every default yaml)
- **Estimate**: 1 SP

### BL-027 — Resource-level authorization (per-KB ACL)
- **REQ**: REQ-AUTH-006 (extension)
- **Module source**: [docs/backlog/_security.md](../../backlog/_security.md) story _security.02
- **Estimate**: 8 SP

### BL-028 — Multi-KB scope in RAG retrieval/expansion
- **REQ**: REQ-RAG-002
- **Module source**: [docs/backlog/rag.md](../../backlog/rag.md) story rag.02
- **Estimate**: 5 SP

---

## P3 — post-v1

### BL-030 — GNN inference via PyTorch Geometric / DGL (D-05)
- **REQ**: REQ-ANALYTICS-003
- **Milestone**: post-v1

### BL-031 — Roadmap adapters: Neptune, Memgraph, pgvector, Weaviate, GCS, Azure Blob
- **REQ**: REQ-INT-005
- **Milestone**: post-v1

### BL-032 — Third-party plugin SPI
- **REQ**: covered by §6 Out of Scope; `[ASSUMPTION]` SPI design revisited after v1
- **Milestone**: post-v1

### BL-033 — Tenant isolation across data + tenant management UI
- **REQ**: covered by §6 Out of Scope
- **Milestone**: post-v1

### BL-034 — Production observability stack (Prom/Grafana/Jaeger + retention/alerts)
- **REQ**: covered by §6 Out of Scope; `[ASSUMPTION]` observability stack selection
- **Milestone**: post-v1

### BL-035 — CI/CD pipelines & GitOps
- **REQ**: covered by §6 Out of Scope
- **Milestone**: post-v1

### BL-036 — Frontend RUM & accessibility audit
- **REQ**: covered by §6 Out of Scope (RUM); a11y planned
- **Milestone**: v1.1

### BL-037 — Configuration hot-reload
- **REQ**: covered by §6 Out of Scope
- **Milestone**: post-v1

---

## Cross-cutting reference

Module backlogs (395 stories) remain the authoritative per-module work breakdown. The Project Manager agent triages stories from these into the curated list above each sprint:

- [docs/backlog/_cicd.md](../../backlog/_cicd.md), [_infra.md](../../backlog/_infra.md), [_multitenancy.md](../../backlog/_multitenancy.md), [_observability.md](../../backlog/_observability.md), [_plugins.md](../../backlog/_plugins.md), [_security.md](../../backlog/_security.md)
- [agent.md](../../backlog/agent.md), [analytics.md](../../backlog/analytics.md), [api.md](../../backlog/api.md), [config.md](../../backlog/config.md), [database.md](../../backlog/database.md), [embeddings.md](../../backlog/embeddings.md), [events.md](../../backlog/events.md), [frontend.md](../../backlog/frontend.md), [graph.md](../../backlog/graph.md), [ingestion.md](../../backlog/ingestion.md), [knowledgebases.md](../../backlog/knowledgebases.md), [llm.md](../../backlog/llm.md), [monitoring.md](../../backlog/monitoring.md), [rag.md](../../backlog/rag.md), [records.md](../../backlog/records.md), [shared.md](../../backlog/shared.md), [storage.md](../../backlog/storage.md), [vectorstore.md](../../backlog/vectorstore.md)
