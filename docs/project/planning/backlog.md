# chiliAI v1 Consolidated Backlog

> Owned by the Project Manager agent. The single source of truth for v1-scoped, prioritized work items.
> Version: 4 · Last updated: 2026-07-12
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
| BL-019 | Embeddings + Vectorstore 1.0 hardening (re-scoped 2026-07-12: cache + cost/usage tracking) | REQ-VEC-001..004 | P1 | code-complete — Sprint 2026-26 (live-stack verification pending, environment) | 0 SP dev |
| BL-041 | Ingestion document-status projection + failure-path closure | REQ-KB-002, REQ-KB-004 | P1 | code-complete — Sprint 2026-26 (full-stack + integration verification pending, environment) | 0 SP dev |
| BL-042 | CI migration drift/replay gate (database.04) | REQ-NFR-002 | P1 | committed — Sprint 2026-26 | 3 SP |
| BL-043 | Ingestion structured stage logs + Prometheus counters | REQ-NFR-SEC-004 | P2 | code-complete — Sprint 2026-26 (live-scrape/full-stack verification pending, environment) | 0 SP dev |
| BL-044 | Config base + overlay layering (config.04) | REQ-CONFIG-001 | P2 | stretch — Sprint 2026-26 | 3 SP |
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

### BL-019 — Embeddings 1.0 + Vectorstore 1.0 hardening (re-scoped 2026-07-12)
- **REQ**: REQ-VEC-001..004
- **Plans**: [docs/superpowers/plans/2026-05-19-embeddings-1-0.md](../../superpowers/plans/), [docs/superpowers/plans/2026-05-19-vectorstore-1-0.md](../../superpowers/plans/)
- **Status**: **code-complete — Sprint 2026-26, 2026-07-14** (all 8 implementation tasks landed: `EmbeddingsConfig` cache knobs + contracts regen, `CachedEmbedding`/`build_embedding_cache_key`, `EmbeddingCacheProtocol` + `InMemoryLruEmbeddingCache` + `create_embedding_cache`/`embedding_cache_namespace`, cache-aware `EmbeddingsService` (standing TODO retired), OpenAI usage capture (`EmbeddingMetadata.total_tokens`), `embeddings/metrics.py` counters + structured usage log, DI wiring at both composition roots with hot-swap safety, this docs task). Backend gates green in-session: `pytest --cov -m "not integration"` full pass, coverage `embeddings`/`vectorstore` both ≥ 85%, `pyright` (0 errors), `ruff check --no-cache` (clean). **Not yet run**: full-stack manual verification (cache hit/miss behavior, `/metrics` scrape, usage log inspection against a running `make dev` stack) — Docker was unavailable this session; tracked as a follow-up verification pass, not additional scope. BL-019 stays **not** flipped to Done pending that verification pass.
- **Remaining estimate**: 0 SP dev (pending live-stack verification)
- **Re-scope ruling (product owner, 2026-07-12)**: acceptance for closing this P1 is **embedding cache + cost/usage tracking**. The roadmap-tier tail (object-store persistence of embeddings, graph-metric hybrid embedding flow, model routing, architecture guards) moved to post-v1 item **BL-045** — REQ-VEC-001..004 do not require it.
- **Acceptance**:
  - [x] Retry/backoff + batching/token budgeting on OpenAI embeddings — `backend/embeddings/adapters/openai_adapter.py:108-134` (`_create_embeddings_with_retry`, 3 attempts, exponential backoff)
  - [x] Namespace lifecycle — `delete_namespace` on both adapters + service (`vectorstore/service.py:200`, `adapters/in_memory.py:105`, `qdrant_adapter.py:232`) with per-namespace dimension guard
  - [x] `delete_by_source_document` wired end-to-end — protocol `vectorstore/protocols.py:39`, service `:216-223`, exercised on the document-replacement path (`api/routers/knowledgebases.py:142-143`); whole-KB delete uses namespace drop via the cleanup cascade (`knowledgebases/cleanup.py:74`)
  - [x] Embedding cache — `EmbeddingCacheProtocol` (`embeddings/adapters/protocols.py`) + `InMemoryLruEmbeddingCache` (`embeddings/adapters/cache_in_memory.py`), SHA-256 key over `namespace + model_name + content`, `EmbeddingsConfig.cache_enabled`/`cache_max_entries`, wired at both composition roots; standing TODO at `embeddings/service.py:24` retired
  - [x] Cost/usage tracking — `embeddings/metrics.py` (`embedding_requests_total`, `embedding_texts_total{cache_result}`, `embedding_tokens_total{provider,model,knowledge_base_id,source}`) + structured usage log per `embed()` call; OpenAI adapter surfaces `usage.total_tokens` on `EmbeddingMetadata`
  - ~~Object-store persistence of embeddings; graph-metric hybrid embedding flow; model routing; architecture guards~~ → moved to **BL-045** (post-v1, ruling 2026-07-12)

### BL-041 — Ingestion document-status projection + failure-path closure
- **REQ**: REQ-KB-002, REQ-KB-004
- **Module source**: [docs/backlog/ingestion.md](../../backlog/ingestion.md) stories ingestion.18 (slice; FE wiring split out), ingestion.32 (coordinator residue closure), ingestion.35 (closure)
- **Status**: **code-complete — Sprint 2026-26, 2026-07-13** (all 10 implementation tasks landed, task-level reviews clean, `pytest -m "not integration"` / `pyright` / `ruff` full green on `ingestion`/`agent`/`api`/`knowledgebases`/`database`). **Full-stack manual verification and the `-m integration tests/database` subset are pending** — the dev-stack Docker environment was unavailable in this session (container networking); tracked as a follow-up verification pass, not additional scope.
- **Estimate**: 6 SP (dev complete; 0 SP remaining pending verification)
- **Acceptance**:
  - [x] `SourceDocumentStatusStore` protocol + Postgres adapter (Alembic migration `0009_document_status`); monotonic transitions (stale `parsing` after `failed` ignored) — `backend/ingestion/adapters/{protocols,in_memory,postgres}.py`
  - [x] Projection consumer subscribes to `documents.uploaded/parsed/failed` + extraction-warning events — `backend/agent/status_projection.py`, wired into the worker's `_dispatch_event` (`agent/coordinator.py`)
  - [x] `GET /knowledgebases/{kb_id}/documents` returns durable `current_status`, `last_error`, validation drop counts/sample reasons; filterable by `?status=`; contracts regenerated
  - [x] Coordinator residue: missing-key/`get_bytes` failures in `handle_documents_parsed/chunked` converted to per-document `DocumentsFailedEvent` (one bad doc no longer poisons its batch)
  - [x] Zero-valid-entity docs surface `EXTRACTED_EMPTY` via the projection (status transition, no new event type)
  - [x] KB-delete cascade purges the projection (`SourceDocumentStatusStore.delete_by_kb`, one step in `knowledgebases.cleanup.kb_deletion_steps`); single-document delete and changed-content reupload purge the superseded row via `delete_by_document`
  - Frontend Studio wiring is explicitly out of scope (follow-on FE story)

### BL-042 — CI migration drift/replay gate
- **REQ**: REQ-NFR-002 (quality-gate; protects REQ-KB-006/REQ-INT-004 persistence)
- **Module source**: [docs/backlog/database.md](../../backlog/database.md) story database.04
- **Status**: committed — Sprint 2026-26 (code-verified 2026-07-12: no `scripts/ci_migration_check.sh`, no `snapshots/head.sql`, no `migrate-check` target; CI runs apply-only `alembic upgrade head` at `ci.yml:87`)
- **Estimate**: 3 SP
- **Acceptance**: `scripts/ci_migration_check.sh` (fresh TimescaleDB → upgrade head → downgrade base → upgrade head + drift check vs committed `snapshots/head.sql`); `make migrate-check` local parity; CI job wired (cross-edge `_cicd.12`). Paired with BL-041's migration `0009` so the new status table gets drift protection from day one.

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

### BL-043 — Ingestion structured stage logs + Prometheus counters
- **REQ**: REQ-NFR-SEC-004 (structured logs); counters are an enabler for post-v1 BL-034
- **Module source**: [docs/backlog/ingestion.md](../../backlog/ingestion.md) story ingestion.17 (logs+counters subset only — OTel spans + Grafana dashboards stay in ingestion.17, blocked on _observability.03/.05/.07)
- **Status**: **code-complete — Sprint 2026-26, 2026-07-14** (`shared/metrics.py` counters + `log_stage` helper; worker `GET /metrics` on the health server, `agent/health.py`; parse-stage log + failure counter in `ingestion/service.py`; chunk/extract/validate stage logs + empty-extraction counter in `agent/coordinator.py`, including failure-counter increments at all four BL-041 per-document `DocumentsFailedEvent` sites; dedup counter at both suppression points. Gates green: `pytest -m "not integration"` full pass, coverage `shared` 97%/`ingestion` 93%/`records` 85%/`agent` 92%; `pyright` 0 errors; `ruff` clean). **Live-scrape/full-stack verification against the running compose stack is pending** — Docker was unavailable this session; tracked as a follow-up verification pass, not additional scope.
- **Estimate**: 2 SP (dev complete; 0 SP remaining pending verification)
- **Acceptance**:
  - [x] Each ingestion stage emits a structured `ingestion_stage` log (`stage=`, `source_document_id=`, `kb_id=`, `duration_ms=`, `outcome=`) — `shared/metrics.py::log_stage`, called from `ingestion/service.py` (parse) and `agent/coordinator.py` (chunk/extract/validate)
  - [x] `ingestion_documents_failed_total{stage,error_class}`, `ingestion_documents_empty_extraction_total`, `ingestion_dedup_suppressed_total{kind}` registered on the default `prometheus_client` registry (`shared/metrics.py`)
  - [x] Worker-side counters scrapeable via the worker's own `GET /metrics` (`agent/health.py`, port 8001) — a separate registry from the API gateway's `/metrics`
  - [ ] Live scrape against `make dev` confirming the counters/log lines appear as expected — deferred, environment

### BL-044 — Config base + environment overlay layering
- **REQ**: REQ-CONFIG-001
- **Module source**: [docs/backlog/config.md](../../backlog/config.md) story config.04
- **Status**: stretch — Sprint 2026-26 (code-verified 2026-07-12: no `overlay.py`, no `CHILI_CONFIG_OVERLAY_PATH`, loader TODO intact at `backend/config/loader.py:31`)
- **Estimate**: 3 SP
- **Acceptance**: merge-semantics ADR; `backend/config/overlay.py` with property-based merge tests; `CHILI_CONFIG_OVERLAY_PATH` (stackable); `medicare_fraud_dev.yaml` shrunk to a minimal overlay; unknown-top-level-key rejection. The ingestion roadmap's named next lever — unblocks ingestion.08/09/13/15 + agent.05/10 + config.08.

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

### BL-045 — Embeddings/vectorstore roadmap tail (re-scoped out of BL-019)
- **REQ**: beyond REQ-VEC-001..004 (roadmap-tier; no v1 requirement demands these)
- **Scope**: object-store persistence of embeddings; graph-metric hybrid embedding flow; model routing; architecture guards — the BL-019 acceptance items moved here by product-owner ruling 2026-07-12 so nothing is silently dropped
- **Plans**: [docs/superpowers/plans/2026-05-19-embeddings-1-0.md](../../superpowers/plans/), [docs/superpowers/plans/2026-05-19-vectorstore-1-0.md](../../superpowers/plans/)
- **Milestone**: post-v1

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
- **2026-07-12 sprint 2026-26 planning (v4)** — Sprint 2026-26 committed (user-approved: 25 SP nominal / 16 SP core, 2026-07-13 → 2026-07-26): appended BL-041/BL-042 (P1, committed), BL-043 (P2, committed), BL-044 (P2, stretch); BL-019 re-scoped by product-owner ruling (acceptance = cache + cost/usage tracking; committed) with its roadmap tail preserved as post-v1 **BL-045**. Supersedes and deletes the June `2026-26-slice-…-DRAFT.md` (residue code-verified 2026-07-12).
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
