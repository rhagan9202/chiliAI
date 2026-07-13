# chiliAI v1 Consolidated Backlog

> Owned by the Project Manager agent. The single source of truth for v1-scoped, prioritized work items.
> Version: 3 · Last updated: 2026-07-12
>
> This file is a **curated v1 backlog** that consolidates and prioritizes work derived from:
> - `docs/project/planning/requirements.md` (canonical requirements, v1.2 · 2026-07-12)
> - The 24 module backlogs under `docs/backlog/**` (see [docs/backlog/README.md](../../backlog/README.md))
> - Drift items identified in PM runs (see History)
>
> The module backlogs remain the authoritative per-module breakdown. This file selects, prioritizes, and dependency-orders items for v1. Every status below was **code-verified against `prod` on 2026-07-12** (post domain-packs merge ff46080 and af_housing merge 23eed31).

## Legend

- **Priority**: `P0` (v1 blocker, ship-stopping) · `P1` (v1 required, important) · `P2` (v1 nice-to-have) · `P3` (post-v1 / deferred)
- **Status**: `todo` · `in-progress` · `partial` (some acceptance criteria shipped) · `done` · `blocked`
- **Estimate**: remaining effort (SP), re-baselined against code — not the nominal original size
- **Module source**: links the canonical module story (`docs/backlog/<module>.md#story-<id>`)

## Active Items — summary

| BL-ID | Title | REQ-IDs | Priority | Status | Remaining |
|-------|-------|---------|----------|--------|-----------|
| BL-017 | Graph integrity + version/merge | REQ-GRAPH-001 | P1 | todo | 8 SP |
| BL-019 | Embeddings + Vectorstore 1.0 hardening | REQ-VEC-001..004 | P1 | partial ~60% | ~5 SP |
| BL-020 | KB snapshots & restore | REQ-KB-007, REQ-NFR-DR-001 | P2 | todo | 8 SP |
| BL-021 | Graph backup/restore per adapter | REQ-GRAPH-006, REQ-NFR-DR-002 | P2 | todo | 5 SP |
| BL-022 | OIDC hardening | REQ-AUTH-001 | P2 | partial ~35% | ~4 SP |
| BL-023 | Event replay operationalization | REQ-WORKFLOW-005, REQ-NFR-DR-003 | P2 | partial ~35% | ~3 SP |
| BL-024 | Load testing & SLO baselines | REQ-NFR-SCALE-PROD | P2 | todo | 8 SP |
| BL-027 | Resource-level per-KB ACL | REQ-AUTH-006 (ext) | P2 | todo | 8 SP |
| BL-028 | Multi-KB scope in RAG | REQ-RAG-002 | P2 | todo | 5 SP |

**Big picture:** the v1 feature surface is complete (all P0s and P1 user-facing verticals shipped — see Done), and the config surface gained a full write/hot-swap path plus a third domain (Air Force housing scorecards) since 2026-06-23. What remains active is purely a hardening/DR/security-depth tail. Requirements v1.2 (2026-07-12) resolved all prior [NO-REQ]/contested items: BL-016 closed at its v1 bar (wizard + write hardening → post-v1, tracked as BL-040), and BL-038/BL-039 gained the REQ-SCORE-*/REQ-HOUSING-* families.

---

## P1 — v1 required

### BL-017 — Graph referential integrity + version/merge semantics
- **REQ**: REQ-GRAPH-001
- **Module source**: [docs/backlog/graph.md](../../backlog/graph.md) stories graph.01, graph.02
- **Status**: todo (re-verified 2026-07-12 — essentially unmoved since 2026-06-16)
- **Remaining estimate**: 8 SP
- **Acceptance**:
  - [ ] Referential integrity: relationship writes validate endpoint existence — today `upsert_relationships` writes unchecked (`backend/graph/adapters/in_memory.py:41-50`, shipping TODO at `:21-22`); Neo4j `MERGE` silently creates phantom endpoint nodes (`neo4j_adapter.py:226-228`)
  - [ ] Optimistic locking / version-conflict detection — `version` is stored and blindly overwritten (`neo4j_adapter.py:176,188`); `graph/service.py:29` carries the production TODO
  - [ ] Real merge semantics — only a property-dict merge on single-entity update exists (`in_memory.py:77-80`, `neo4j_adapter.py:295-298`)

### BL-019 — Embeddings 1.0 + Vectorstore 1.0 hardening
- **REQ**: REQ-VEC-001..004
- **Plans**: [docs/superpowers/plans/2026-05-19-embeddings-1-0.md](../../superpowers/plans/), [docs/superpowers/plans/2026-05-19-vectorstore-1-0.md](../../superpowers/plans/)
- **Status**: partial ~60% (re-verified 2026-07-12)
- **Remaining estimate**: ~5 SP
- **Acceptance**:
  - [x] Retry/backoff + batching/token budgeting on OpenAI embeddings — `backend/embeddings/adapters/openai_adapter.py:108-134` (`_create_embeddings_with_retry`, 3 attempts, exponential backoff)
  - [x] Namespace lifecycle — `delete_namespace` on both adapters + service (`vectorstore/service.py:200`, `adapters/in_memory.py:105`, `qdrant_adapter.py:232`) with per-namespace dimension guard
  - [x] `delete_by_source_document` wired end-to-end — protocol `vectorstore/protocols.py:39`, service `:216-223`, exercised on the document-replacement path (`api/routers/knowledgebases.py:142-143`); whole-KB delete uses namespace drop via the cleanup cascade (`knowledgebases/cleanup.py:74`)
  - [ ] Embedding cache — none (standing TODO `backend/embeddings/service.py:24`)
  - [ ] Cost/usage tracking — none
  - [ ] Object-store persistence of embeddings; graph-metric hybrid embedding flow; model routing; architecture guards — none

---

## P2 — v1 nice-to-have

### BL-020 — KB snapshots & restore (D-01)
- **REQ**: REQ-KB-007, REQ-NFR-DR-001
- **Module source**: [docs/backlog/knowledgebases.md](../../backlog/knowledgebases.md) story knowledgebases.07
- **Status**: todo (re-verified 2026-07-12 — only the internal transport model `backend/knowledgebases/snapshots.py::KnowledgeBaseStoreSnapshot` exists; no snapshot repository, no snapshot/restore endpoints)
- **Remaining estimate**: 8 SP

### BL-021 — Graph backup/restore procedures per adapter (D-02)
- **REQ**: REQ-GRAPH-006, REQ-NFR-DR-002
- **Module source**: [docs/backlog/graph.md](../../backlog/graph.md) story graph.11
- **Status**: todo (re-verified 2026-07-12 — no export/backup/restore methods anywhere in `backend/graph/`; the only "snapshot" is in-memory transaction-rollback `deepcopy` state, `in_memory.py:316-337`)
- **Remaining estimate**: 5 SP

### BL-022 — OIDC hardening: JWKS rotation, full id_token validation (D-09)
- **REQ**: REQ-AUTH-001
- **Module source**: [docs/backlog/_security.md](../../backlog/_security.md) story _security.01
- **Status**: partial ~35% (re-verified 2026-07-12; no auth-crypto commits since 2026-06-16)
- **Remaining estimate**: ~4 SP
- **Acceptance**:
  - [x] JWKS TTL cache keyed by URI — `backend/api/middleware/auth.py:81` (`JwksCache`)
  - [x] aud/iss/exp + signature validation — `auth.py:196-208` (`jwt.decode(..., audience, issuer, algorithms=["RS256"])`)
  - [x] id_token routed through the validated decode path in the OIDC callback — `backend/api/routers/auth.py:128-134`
  - [x] *(adjacent, landed with ff46080)* Production auth guardrail: incomplete/disabled `AuthConfig` rejected under `CHILI_ENV=staging|production`, at boot and pre-hot-swap — `backend/api/dependencies.py:309` (`enforce_production_guardrail`), `api/app.py:78`
  - [ ] kid-aware key rotation (forced JWKS refresh on unknown `kid`; today cache refresh is TTL-only) + rotation tests
  - [ ] nonce generation + validation in the OIDC flow (PKCE `state` only today, `auth.py:109`)
  - [ ] IdP configuration templates (Keycloak/Okta) — none in repo

### BL-023 — Event replay operationalization (D-11)
- **REQ**: REQ-WORKFLOW-005, REQ-NFR-DR-003
- **Module source**: [docs/backlog/events.md](../../backlog/events.md)
- **Status**: partial ~35% (re-verified 2026-07-12 — unchanged)
- **Remaining estimate**: ~3 SP
- **Acceptance**:
  - [x] Stale-pending reclaim via `xautoclaim` — `backend/events/adapters/redis_streams.py:107-124`
  - [x] DLQ stream publish (`{stream}.dlq`) — `redis_streams.py:160-176`
  - [x] Handler retry/DLQ wrapper (documented `docs/security_checklist.md:136`)
  - [ ] Durable DLQ persistence — no table/migration (in-memory adapter keeps a Python list, `adapters/in_memory.py:25`)
  - [ ] Replay API or operator script — no `replay` surface in `backend/api/` or `scripts/`
  - [ ] Operator runbook — `docs/runbooks/` does not exist

### BL-024 — Load testing & SLO baselines (D-12)
- **REQ**: REQ-NFR-SCALE-PROD
- **Status**: todo (re-verified 2026-07-12 — no harness anywhere; `locust`/`k6` appear only as aspirational lines in module backlogs; `backend/tests/perf/` absent)
- **Remaining estimate**: 8 SP
- **Notes**: Establishes the latency/throughput targets currently held as `[ASSUMPTION]` in requirements. Unblocks resolving the four open `[ASSUMPTION]` items via `/refresh-requirements`.

### BL-027 — Resource-level authorization (per-KB ACL)
- **REQ**: REQ-AUTH-006 (extension)
- **Module source**: [docs/backlog/_security.md](../../backlog/_security.md) story _security.02
- **Status**: todo (re-verified 2026-07-12 — `KnowledgeBase` still has no owner/acl fields, only the production TODO at `backend/shared/types.py:170`; no ACL model/middleware/endpoints)
- **Remaining estimate**: 8 SP

### BL-028 — Multi-KB scope in RAG retrieval/expansion
- **REQ**: REQ-RAG-002
- **Module source**: [docs/backlog/rag.md](../../backlog/rag.md) story rag.02
- **Status**: todo (re-verified 2026-07-12 — retrieval still projects the KB list to `[0]`: `backend/rag/service.py:132` `primary_kb_id = request.knowledge_base_ids[0]`, documented single-KB limitation at `:131,165`)
- **Remaining estimate**: 5 SP

---

## P3 — post-v1

### BL-030 — GNN inference via PyTorch Geometric / DGL (D-05)
- **REQ**: REQ-ANALYTICS-003 · **Milestone**: post-v1

### BL-031 — Roadmap adapters: Neptune, Memgraph, pgvector, Weaviate, GCS, Azure Blob
- **REQ**: REQ-INT-005 · **Milestone**: post-v1

### BL-032 — Third-party plugin SPI
- **REQ**: covered by §6 Out of Scope; `[ASSUMPTION]` SPI design revisited after v1 · **Milestone**: post-v1

### BL-033 — Tenant isolation across data + tenant management UI
- **REQ**: covered by §6 Out of Scope · **Milestone**: post-v1

### BL-034 — Production observability stack (Prom/Grafana/Jaeger + retention/alerts)
- **REQ**: covered by §6 Out of Scope; `[ASSUMPTION]` observability stack selection · **Milestone**: post-v1

### BL-035 — CI/CD pipelines & GitOps
- **REQ**: covered by §6 Out of Scope · **Milestone**: post-v1

### BL-036 — Frontend RUM & accessibility audit
- **REQ**: covered by §6 Out of Scope (RUM); a11y planned · **Milestone**: v1.1

### BL-040 — Config wizard + config-write hardening (post-v1 tail of BL-016)
- **REQ**: REQ-CONFIG-011 (post-v1) + requirements §6 "Sectioned configuration wizard" bullet (requirements v1.2)
- **Module source**: [docs/backlog/frontend.md](../../backlog/frontend.md) (frontend.03/25/26 — sectioned wizard), [docs/backlog/config.md](../../backlog/config.md) (config.06/07/09/14/15 — draft persistence, ETag optimistic concurrency, admin audit events)
- **Milestone**: post-v1 (product-owner ruling 2026-07-12: raw-YAML editor + pack switcher is the v1 bar; audit-trail gap recorded as an accepted deviation in requirements §6)
- **Estimate**: ~3 SP (wizard) + hardening stories per module backlog

---

## Done

| BL-ID | Title | REQ-IDs | Completed | Evidence |
|-------|-------|---------|-----------|----------|
| BL-001 | Wire live RAG service (embed → retrieve → expand → generate) | REQ-RAG-001, REQ-RAG-002 | Sprint 2026-22 | `backend/rag/service.py` + RAG Chat e2e |
| BL-002 | RAG citations & provenance | REQ-RAG-003 | Sprint 2026-22 | citations in RAG payload + rendered in `RagChatPage.tsx` |
| BL-003 | Mount GraphCanvas in Investigation Workbench | REQ-UI-004 | Sprint 2026-22 | `GraphCanvas` on `InvestigationWorkbenchPage` + neighborhood e2e |
| BL-004 | CI dependency vulnerability scanning | REQ-NFR-SEC-005 | Sprint 2026-22 | `.github/workflows/ci.yml:113-132` (pip-audit, fail HIGH/CRITICAL), `:231-232` (npm audit) |
| BL-005 | Evidence pack subgraph extraction | REQ-ANALYTICS-005 | Sprint 2026-23 | `EvidencePackRepository` (`analytics/explainability/`), worker explainability stage, `tests/agent/test_explainability_stage.py` |
| BL-006 | Evidence pack on alert UI | REQ-ALERT-003 | Sprint 2026-23 | `EvidencePackViewer` in workbench + alert feed; `alert-feed-evidence.spec.ts` |
| BL-010 | Case Management v1 surface | REQ-CASE-001..004 | Sprint 2026-23 | `backend/cases/` + migration `0002_cases`; `case-promote.spec.ts` |
| BL-011 | Policy Intelligence v1 surface | REQ-POLICY-001..004 | Sprint 2026-24 | `DomainConfig.policy_rules`, durable `PolicyItem`s, triage routes; `policy-triage.spec.ts` |
| BL-012 | De-seed `ApiState` (all endpoints on durable services) | REQ-RAG-002, REQ-ALERT-001, REQ-WORKFLOW-002 | Sprint 2026-25 | all six `_seed_*` removed; regression test forbids `_seed_*` outside `tests/`; `backend/conversations/` + migration `0005` |
| BL-013 | Ingestion Studio UI/UX (upload progress, retry) | REQ-KB-002, REQ-KB-004 | Sprint 2026-25 | XHR progress + retry, receipt counts; ingestion-records e2e |
| BL-014 | Ingestion pipeline E2E demo (TN Medicare subset) | REQ-KB-003, REQ-REC-001..004, REQ-RAG-002 | Sprint 2026-25 | 17-doc synthetic policy corpus + demo/e2e wiring |
| BL-015 | Records submission-level dedup + format enforcement | REQ-REC-001, REQ-REC-003 | Sprint 2026-25 | migration `0004_record_submissions`, per-row rejection, typed receipts, 415 gate |
| BL-018 | Neo4j index strategy for scale | REQ-NFR-SCALE-PROD | verified 2026-06-04 | `neo4j_adapter.py:139` `_ensure_schema`: unique constraint + KB-scoped indexes + fulltext (re-verified 2026-07-12) |
| BL-025 | Configuration editor polish + tests | REQ-CONFIG-005 | 2026-07-04 (merge ff46080) | subsumed by Config Manager: `ConfigurationPage.test.tsx` (Vitest), `api/__tests__/config.test.ts`, `e2e/config-manager.spec.ts` |
| BL-026 | Test coverage for default configs loading | REQ-CONFIG-001 | Sprint 2026-22 | `tests/config/test_loader.py` covers every default yaml (now 5 packs incl. `department_air_force_housing.yaml`) |
| BL-037 | Configuration hot-reload | was §6 Out of Scope (post-v1) | 2026-07-04 (merge ff46080) | API + worker swap `DomainConfig` without restart: `dependencies.py:1799` generation-guarded cache reset; `coordinator.py:1066` worker rebuild on `config.updated`. **Limitations**: pack must not change the event transport across a swap (restart required); reload-posture ADR + `config_reload_total` metric + cache-coverage audit test remain in module story config.05 |
| BL-016 | Configuration save endpoint (v1 bar: validated YAML editor + pack switcher) | REQ-CONFIG-005..010 (v1.2) | 2026-07-12 (requirements v1.2 ruling) | write path `api/routers/config.py:454,489,509` + swap-once-success `_activate_pack()`; durable pointer `config/store.py:100-142`; hot-swap `dependencies.py:1799` / `coordinator.py:1066`; Config Manager UI (`ConfigurationPage.tsx`); full unit/Vitest/Playwright coverage. Post-v1 tail (sectioned wizard + draft/ETag/audit hardening) split to **BL-040** |
| BL-038 | Scorecards platform module (deterministic evaluator, persisted runs, API) | REQ-SCORE-001..008 (v1.2) | 2026-07-12 (merge 23eed31) | `backend/scorecards/` (evaluation/service/in-memory+Postgres adapters), migration `0008_scorecards`, `api/routers/scorecards.py`, KB cleanup cascade, `ScorecardsConfig` in `config/schema.py`; tests `backend/tests/scorecards/`, `test_scorecards_router.py` |
| BL-039 | Air Force housing domain pack + Housing Executive dashboard | REQ-HOUSING-001..007 (v1.2) | 2026-07-12 (merge 23eed31) | `department_air_force_housing.yaml` (1050 lines), `api/routers/housing.py` + `_housing_read_model.py`, `HousingExecutivePage.tsx` / `ScorecardRunPage.tsx`, seed tooling (`make seed-housing`), e2e `air-force-housing-*.spec.ts` |

---

## [NO-REQ] Items Awaiting Requirement

None. The 2026-07-12 Requirements Gatherer run (requirements v1.2) resolved all flags carried by backlog v2:
- **BL-038** → **REQ-SCORE-001..008** (scorecards platform family); **BL-039** → **REQ-HOUSING-001..007** (housing domain family, supported exemplar-tier per product-owner ruling). Both moved to Done.
- **REQ-CONFIG-005** amended (read-only → managed write; v1 bar = validated YAML editor + pack switcher) and **REQ-CONFIG-006..011** added — closing BL-016 (post-v1 tail → BL-040). **REQ-CONFIG-001** now names all 5 shipped packs.
- The v1 config-change audit-trail gap is recorded as an explicit accepted deviation in requirements §6.

---

## History

Full detail for each pass lives in this file's git history (`git log -p -- docs/project/planning/backlog.md`). Summaries:

- **2026-05-26 PM run (drift resolution)** — 18 drift items (D-01..D-18) adjudicated against requirements v1.1. All CODE-CHANGE items (D-03/04/06/07/08/10/14/15 → BL-001..006, BL-010/011) have since shipped; ACCEPT-AS-BACKLOG items became BL-020..025/030; two REQUIREMENT-CHANGE items were amended into requirements v1.1.
- **2026-06-16 reconciliation pass** — code-level audit of every non-done BL item; corrected systemically stale SP estimates (BL-013 8→~0, BL-014 13→~0, BL-015 5→3, BL-018 already done). Conclusion then (still true): the v1 feature surface is essentially complete; the remainder is a hardening/DR/security-depth tail.
- **2026-07-12 requirements v1.2 reconciliation (v3)** — after the Requirements Gatherer refresh: BL-016 closed at the v1 bar per product-owner rulings (OQ-1..4: wizard post-v1, config-write hardening post-v1, API-only scorecard generation, housing = supported exemplar-tier domain); BL-038/BL-039 moved from [NO-REQ] to Done under the new REQ-SCORE-*/REQ-HOUSING-* families; BL-040 appended for the post-v1 config tail.
- **2026-06-23 PM run (module-backlog dependency-graph cleaning)** — platform-wide audit of all 24 module backlogs: 18 mislabeled/dangling prerequisite edges corrected, 2 new stories added (analytics.33 extraction-quality metric, storage.14 object-store health probes), 3 substantially-shipped stories annotated (api.02/api.03/analytics.11), and 3 PM decisions recorded (frontend.04 → `[api.28, rag.01]`; `_security.06` is the canonical audit-log story with `_observability.10` dropped; `agent.18` owns `PostgresWorkflowRunStore` with `database.01` refocused on the migration).

### Carryover notes (still actionable)

- **`backend/app/...` path nit** — newer narrative-style module stories (most `*.1x`+ across graph/api/config/events/analytics/monitoring) cite code-touch-points under a non-existent `backend/app/...` layout; the real layout is `backend/<module>/`. Doc-convention cleanup, not a status defect.
- **database.08–.13 Alembic revision-ID collision** — those stories carry literal revision IDs `0004_…`–`0008_…` that collide with shipped revisions, which now run through **`0008_scorecards`** (af_housing merge). Renumber at implementation time.
- **No `scorecards.md` module backlog** — the new `backend/scorecards/` module has no engineering-story home under `docs/backlog/**`; hardening stories for it (e.g. peer-stats depth, template versioning) currently have nowhere to land. Flag for the module-backlog owner.
- **Estimate drift is systemic** (2026-25 retro) — verify every committed story against code at sprint kickoff; do not trust nominal SPs.
- Frontend + cross-cutting operational module backlogs still need the reconciliation pass that backend docs got on 2026-06-16.

---

## Cross-cutting reference

Module backlogs remain the authoritative per-module work breakdown (CI-enforced via `scripts/backlog_consistency.py`). The Project Manager agent triages stories from these into the curated list above each sprint:

- [docs/backlog/_cicd.md](../../backlog/_cicd.md), [_infra.md](../../backlog/_infra.md), [_multitenancy.md](../../backlog/_multitenancy.md), [_observability.md](../../backlog/_observability.md), [_plugins.md](../../backlog/_plugins.md), [_security.md](../../backlog/_security.md)
- [agent.md](../../backlog/agent.md), [analytics.md](../../backlog/analytics.md), [api.md](../../backlog/api.md), [config.md](../../backlog/config.md), [database.md](../../backlog/database.md), [embeddings.md](../../backlog/embeddings.md), [events.md](../../backlog/events.md), [frontend.md](../../backlog/frontend.md), [graph.md](../../backlog/graph.md), [ingestion.md](../../backlog/ingestion.md), [knowledgebases.md](../../backlog/knowledgebases.md), [llm.md](../../backlog/llm.md), [monitoring.md](../../backlog/monitoring.md), [rag.md](../../backlog/rag.md), [records.md](../../backlog/records.md), [shared.md](../../backlog/shared.md), [storage.md](../../backlog/storage.md), [vectorstore.md](../../backlog/vectorstore.md)
