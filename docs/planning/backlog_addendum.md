# chiliAI — Backlog Addendum (Epics 11–15)

> **Generated**: April 27, 2026
> **Basis**: Codebase audit against `docs/architecture.md`, `backend/README.md`, `chili_app/README.md`, and the existing `docs/planning/backlog.md` (Epics 1–10).
> **Authors**: Audit Agent (user-perspective gap analysis) + Lead Developer (story decomposition)
> **Format**: User stories with acceptance criteria, priority, size, and dependency tracking — matching the conventions of `backlog.md`.

> **Status note**: This addendum remains useful as a backlog source, but its audit findings are not all current. Production-facing adapters, CI/CD, Kubernetes/Helm manifests, and several frontend/backend surfaces have since landed. Use [`../project_status_report.md`](../project_status_report.md) for live status.

This addendum captures gaps discovered during the April 27, 2026 audit. Epics 1–10 in `backlog.md` remain authoritative for the in-flight work; this document adds Epics 11–15 covering features that the audit identified as missing from the delivered system but required by the architecture or by a real-world analyst user.

---

## Backlog Summary (addendum)

| Epic | Title | Stories | P0 | P1 | P2 | P3 |
|------|-------|---------|----|----|----|----|
| E11 | Authentication, Authorization & Multi-Tenancy | 5 | 3 | 1 | 1 | 0 |
| E12 | Investigation Workbench Completion | 9 | 5 | 1 | 3 | 0 |
| E13 | Active Monitoring & Real-Time Pipeline | 8 | 3 | 4 | 1 | 0 |
| E14 | Analytics, RAG & Adapter Maturity | 13 | 1 | 5 | 7 | 0 |
| E15 | Operations & Quality Bar | 12 | 0 | 4 | 5 | 3 |
| **Total (addendum)** | | **47** | **12** | **15** | **17** | **3** |

Priority and size definitions are unchanged from `backlog.md`.

### Audit findings driving these epics

The April 27 audit confirmed substantial progress against Epics 1–10 (~80 % shipped per `MEMORY.md` notes) and identified five clusters of user-facing or production-blocking gaps. Some items in this list have since moved from missing to partial or complete in the current status report:

1. **Auth, RBAC, multi-tenancy are scaffolded but disabled** — `backend/api/middleware/auth.py` and `rbac.py` exist; no router enforces them; no login UI; no tenant scoping in adapters.
2. **Investigation Workbench is incomplete on the highest-value panels** — Evidence Pack endpoint missing (`chili_app/src/components/investigation/EvidencePanel.tsx:41-46` shows a placeholder), timeline shows only entity metadata, config save button is permanently disabled, cascading delete is designed but not implemented.
3. **The active monitoring path (architecture Flow B) does not run end-to-end** — no real claim-stream ingestion endpoint, WebSocket hub broadcasts in-process only and does not bridge Redis Streams, no audit log, no idempotency keys, no DLQ.
4. **Analytics modules are heuristic substitutes for the architected capabilities** — entity extraction is regex-only, GNN is degree-centrality + Jaccard similarity, time-series is z-score, risk is rule-based, explanations are raw subgraphs (no SHAP/LIME). Vendor coverage is one-of-three for graph DBs (Neo4j) and vector stores (Qdrant); Ollama/vLLM adapter is missing.
5. **Operational hardening gaps** — no HTTP rate limiting, OTel exporter not wired, no Sentry, no E2E tests, hand-rolled API client (no OpenAPI codegen), no pre-commit hooks, no external secrets, no IaC.

The 12 P0 stories below close the must-have gaps for a first real-world deployment.

---

## Epic 11: Authentication, Authorization & Multi-Tenancy

> Flip on the auth, RBAC, and tenancy machinery already scaffolded in `backend/api/middleware/` and add the matching frontend login flow, so the platform can ship to a customer with more than one user.

### E11-S01: Enforce auth middleware in production deployments

**As a** platform operator, **I want** auth middleware enabled by default in non-development configurations, **so that** unauthenticated requests cannot reach business endpoints in production.

**Acceptance Criteria:**
1. `AuthConfig.enabled` defaults to `True` in `docker-compose.yaml`, `infra/helm/chili/values-prod.yaml`, and Kubernetes prod overlays.
2. `/health`, `/metrics`, `/openapi.json`, `/docs`, and `/redoc` remain public; all other routes return `401` without a valid bearer token.
3. Anonymous-user fallback is gated behind an explicit `CHILI_AUTH_ALLOW_ANONYMOUS=true` env flag and disallowed when `AuthConfig.enabled=True`.
4. Integration test boots the API with auth enabled and asserts (a) public endpoints return `200`, (b) protected endpoints return `401` without a token, (c) protected endpoints return `200` with a signed test JWT.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E10-S06 |

**Notes:** The middleware itself (`backend/api/middleware/auth.py`) already implements JWKS caching, RS256 validation, audience and issuer checks. This story is about defaults and enforcement, not new validation logic.

---

### E11-S02: Build login + token-refresh UI

**As an** analyst, **I want** to log in via the configured OIDC provider and have my session refreshed silently, **so that** I am not logged out mid-investigation.

**Acceptance Criteria:**
1. `chili_app/src/pages/Login/` renders a "Sign in" page that initiates the OIDC PKCE authorization-code flow against the configured IdP.
2. Access token is held in memory (Zustand auth store); refresh token is stored in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie set by the API.
3. `chili_app/src/lib/apiClient.ts` retries any `401` response once after triggering a silent refresh; on refresh failure the user is redirected to `/login?return=<path>`.
4. A `<RequireAuth>` route guard wraps all routes except `/login` and `/healthz`; unauthenticated users are redirected to login.
5. Logout clears the in-memory token, calls a `POST /auth/logout` endpoint that invalidates the refresh cookie, and returns to `/login`.
6. Vitest covers token-refresh retry, redirect-on-401, and logout cleanup.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E11-S01 |

**Notes:** The IdP issuer URL and client id come from `GET /config/auth` (a new public endpoint that returns the OIDC discovery hints already present in `AuthConfig`). Avoid bundling client secrets in the SPA — PKCE only.

---

### E11-S03: Apply role guards to all routers

**As a** security reviewer, **I want** every router endpoint to declare a required role, **so that** a "viewer" cannot delete a knowledge base or acknowledge another analyst's alert.

**Acceptance Criteria:**
1. Every operation in `backend/api/routers/*.py` is annotated with `Depends(require_role(Role.X))` from `backend/api/middleware/rbac.py`.
2. A test in `tests/api/test_rbac_matrix.py` enumerates the OpenAPI schema's operations and asserts each one has a non-empty role annotation; the test fails for any unannotated route.
3. Read endpoints accept `viewer | analyst | admin`; mutations accept `analyst | admin`; configuration and KB-deletion endpoints accept `admin` only.
4. Integration tests cover, for at least one endpoint per router, that each of the three roles receives the expected `200` / `403` response.
5. The OpenAPI description for each operation includes the required role for documentation purposes.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E11-S01, E10-S07 |

**Notes:** Use a `default_response_class`-style decorator pattern so that adding a new router automatically inherits a default-deny posture if the developer forgets to annotate.

---

### E11-S04: Tenant scoping in graph, vector, and storage adapters

**As a** customer, **I want** my knowledge bases and graph data isolated from other tenants, **so that** I can safely deploy chiliAI on shared infrastructure.

**Acceptance Criteria:**
1. `tenant_id` is extracted from the JWT (claim name configurable in `AuthConfig`) and made available via a `get_tenant_context()` FastAPI dependency.
2. `tenant_id` is propagated through service-layer calls into adapter calls; adapters accept it as part of an immutable `AdapterContext` value object (no positional argument explosion).
3. Neo4j adapter scopes every Cypher query with a `tenant_id` property filter; in-memory adapter partitions its dictionaries by tenant; Qdrant adapter uses a per-tenant collection name (`{prefix}_{tenant_id}`); object store paths are prefixed with `tenants/{tenant_id}/`.
4. Cross-tenant isolation tests: tenant A creates a KB, tenant B's read/list/delete calls return as if the KB does not exist.
5. The worker (`backend/agent/coordinator.py`) carries `tenant_id` from incoming events through to outgoing events.
6. A migration script for existing single-tenant deployments backfills a `tenant_id="default"` on all entities, relationships, vector records, and object-store keys.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | E11-S01, E11-S03 |

**Notes:** Resist the urge to introduce a request-scoped global. Pass context explicitly through service constructors; the DI layer wires it per-request.

---

### E11-S05: Tenant-aware quotas

**As a** platform operator, **I want** per-tenant limits on resource consumption, **so that** one tenant cannot exhaust shared infrastructure.

**Acceptance Criteria:**
1. `DomainConfig.tenancy.quotas` defines `max_knowledge_bases`, `max_documents_per_kb`, `max_total_storage_bytes`, `max_alerts_per_day`.
2. KB creation, document upload, and alert generation check the relevant quota before proceeding; over-quota returns `429 Too Many Requests` with a `Retry-After` header where applicable.
3. A `GET /admin/tenants/{tenant_id}/usage` endpoint (admin role) returns current consumption against limits.
4. A `<TenantUsage>` panel on the admin Dashboard surfaces quota consumption to operators.
5. Metrics: `tenant_quota_remaining{tenant_id, quota_kind}` (gauge) and `tenant_quota_exceeded_total{tenant_id, quota_kind}` (counter).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E11-S04 |

**Notes:** Storage size can be approximated from object-store metadata to avoid expensive aggregation; document this in the docstring so future operators understand the precision trade-off.

---

## Epic 12: Investigation Workbench Completion

> Close the user-visible gaps in the flagship investigation experience — evidence packs, timelines, cascading deletes, and saveable configuration — so the workbench tells a complete story end to end.

### E12-S01: Implement evidence pack endpoint

**As an** investigator, **I want** to see the reasoning, score breakdown, and supporting subgraph for a flagged entity, **so that** I can decide whether to escalate.

**Acceptance Criteria:**
1. `GET /investigation/entities/{entity_id}/evidence?kb_id=...` returns an `EvidencePack` containing: `reasoning: str` (LLM-summarized), `scores: dict[str, float]` (risk, anomaly, GNN), `subgraph: dict` (node-link JSON, depth ≤ 2), `source_documents: list[SourceCitation]`.
2. The handler delegates to `backend/analytics/explainability/service.py`, which composes the pack from the latest persisted risk, GNN, and timeseries outputs (written back to the graph by the agent coordinator).
3. When no analytics outputs exist for the entity, the response is `404` with a clear `detail` ("no analytics outputs for this entity yet"), not a stub pack.
4. Integration test seeds a fixture KB with enriched analytics properties and asserts the response contains all four fields with non-empty content.
5. The endpoint enforces analyst-or-admin role per E11-S03.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | L | E4 (coordinator analytics writeback), E7 (analytics outputs) |

**Notes:** The `SourceCitation` type already exists for RAG; reuse it. Do not invent a parallel structure.

---

### E12-S02: Wire evidence panel to real endpoint

**As an** investigator, **I want** the Evidence Pack panel in the Investigation Workbench to show live data, **so that** I no longer see the "endpoint not yet implemented" placeholder.

**Acceptance Criteria:**
1. `chili_app/src/components/investigation/EvidencePanel.tsx` consumes a new `useEvidencePack(entityId, kbId)` TanStack Query hook calling `GET /investigation/entities/{id}/evidence`.
2. The placeholder copy at lines 41–46 is removed; loading shows a skeleton, `404` shows an empty state, network errors show an inline error with a retry button.
3. Reasoning text is rendered with line wrapping; scores are shown in a compact card grid; the subgraph is rendered as a thumbnail (force-directed mini-graph) that opens an enlarged modal on click; source documents are clickable and deep-link to the KB document viewer.
4. Vitest covers loading, success, empty, and error states.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | E12-S01 |

**Notes:** The mini-graph can reuse the same `react-force-graph-2d` instance with a smaller canvas; do not pull in a second visualization library.

---

### E12-S03: Time-series anomaly endpoint

**As an** investigator, **I want** a per-entity time-series with anomaly markers, **so that** I can identify unusual periods in claim volume or activity.

**Acceptance Criteria:**
1. `GET /investigation/entities/{entity_id}/timeseries?kb_id=...&metric=<name>&window=<iso8601_duration>` returns `{ points: [{ts, value}], anomalies: [{ts, score, kind}] }`.
2. Supported metrics are declared in `DomainConfig.analytics.timeseries.metrics`; unknown metrics return `400`.
3. The handler reads from the timeseries detector's persisted output (graph entity properties + a per-metric series in the vector store or a dedicated table).
4. When monitoring has not produced any series for the entity, the response is `200` with empty arrays — not `404` — so the UI can render an "insufficient data" state.
5. Integration test asserts anomaly markers are returned for a fixture entity that has been seeded with three-sigma deviations.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E13-S01 (real claim ingestion), E14-S03 (production detector) |

**Notes:** The series storage choice (graph property list vs. dedicated time-series store) is a design call; prefer reusing the vector store with a numeric-payload schema before introducing a new backend.

---

### E12-S04: Render timeline panel against real data

**As an** investigator, **I want** the Timeline panel to show real activity and anomalies for the selected entity, **so that** I no longer see only its `created_at` and `updated_at`.

**Acceptance Criteria:**
1. `chili_app/src/components/investigation/TimelinePanel.tsx` consumes a new `useEntityTimeseries(entityId, kbId, metric)` hook.
2. A sparkline chart (existing chart library or a small SVG component — no new heavy dep) shows `points`; anomaly timestamps are highlighted with a colored marker and an accessible legend.
3. A metric-selector dropdown is populated from `DomainConfig.analytics.timeseries.metrics`; the panel hides itself when the list is empty.
4. Empty-state copy is "Not enough activity data for this entity yet" — not the previous metadata fallback.
5. Vitest covers metric selection, empty state, and anomaly rendering.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E12-S03 |

**Notes:** The current `TimelinePanel` falls back to entity creation/update events; that fallback should be removed once the new endpoint lands — keeping it would mask future data outages.

---

### E12-S05: Cascading delete of document → entities → relationships → embeddings

**As an** analyst, **I want** deleting a document to remove the entities and relationships it produced, **so that** the graph stays consistent with the document inventory.

**Acceptance Criteria:**
1. `DELETE /knowledgebases/{kb_id}/documents/{doc_id}` performs, in order, within a single coordinated workflow: (a) identify entities whose only `source_document_id` is this doc, (b) identify relationships referencing those entities, (c) delete those entities and relationships from the graph, (d) delete the corresponding vector records, (e) delete the raw object-store blob, (f) update KB metadata counts.
2. Entities still referenced by other documents have only the matching provenance entry removed and remain in the graph; their `version` is incremented.
3. The operation is idempotent: replaying the same delete is a no-op.
4. The operation publishes `document.deleted` and `graph.updated` events with correlation id for downstream consumers.
5. Integration test covers the multi-doc shared-entity scenario described in `docs/architecture.md` §7.2.
6. Failures partway through the workflow leave the system in a recoverable state; an admin endpoint or replay tool can complete a partially-failed delete.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | L | E13-S05 (idempotency keys), provenance fields already on `backend/ingestion/models.py` |

**Notes:** Treat this as a saga: each step emits an event the coordinator can retry; do not attempt a single-transaction delete spanning graph + vector + object store.

---

### E12-S06: Domain configuration save endpoint

**As an** admin, **I want** to save edits to the domain configuration through the API, **so that** I do not have to redeploy the API container to retarget the platform.

**Acceptance Criteria:**
1. `PUT /config/domain` accepts a `DomainConfig` payload, validates against the existing Pydantic schema, persists to a configurable backing store (file path or KB), increments `schema_version`'s revision counter, and broadcasts a `config.updated` event.
2. Validation errors return `422` with field-level detail; concurrent-edit conflicts (revision mismatch) return `409`.
3. Subsystems that can pick up changes at runtime (alert thresholds, RAG settings, monitoring intervals) reload on the `config.updated` event; subsystems that cannot (graph backend selection, embedding dimensions) report `restart_required: true` in the response.
4. Endpoint is admin-only per E11-S03.
5. Integration test covers happy path, validation failure, concurrent-edit conflict, and runtime-reload propagation.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E11-S03, `backend/config/loader.py` |

**Notes:** The persistence backing store is configurable so single-tenant deployments can keep the YAML file workflow while multi-tenant ones move to a database row keyed by tenant.

---

### E12-S07: Re-enable config editor save button

**As an** admin, **I want** to save my domain config edits from the browser, **so that** the editor is functionally complete.

**Acceptance Criteria:**
1. The save button at `chili_app/src/pages/ConfigEditor.tsx:60-61` is enabled and the "endpoint pending" tooltip removed.
2. Save submits the YAML via `PUT /config/domain`, surfacing validation errors inline next to the offending field.
3. On a `restart_required: true` response the UI shows a persistent banner instructing the operator to redeploy.
4. The editor blocks navigation away from the page when there are unsaved changes (browser `beforeunload` + react-router prompt).
5. Vitest covers save success, validation failure, conflict, and restart-required banner.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | S | E12-S06 |

**Notes:** Pair with a small "diff preview" affordance that shows what changed since the last loaded version — operators editing live config will appreciate it.

---

### E12-S08: Domain configuration wizard (no-YAML editor)

**As a** product manager, **I want** to onboard a new domain through a form-based wizard, **so that** I do not have to learn YAML to retarget the platform.

**Acceptance Criteria:**
1. A new `chili_app/src/pages/ConfigWizard/` page provides a multi-step form: (1) domain name + description, (2) entity types with property definitions, (3) relationship types, (4) capability toggles, (5) alert thresholds, (6) review.
2. Each step validates against the same `DomainConfig` schema; errors are inline.
3. The wizard round-trips with the YAML editor: switching to YAML view shows the form-produced config; switching back parses YAML into form state.
4. Submit calls `PUT /config/domain`; on success the user is routed to the Dashboard with the new config active.
5. Vitest covers each step's validation, round-trip with the YAML editor, and submit.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | L | E12-S06 |

**Notes:** Keep the YAML view as the source of truth; the wizard is a façade. This keeps two surfaces in sync without divergence risk.

---

### E12-S09: Investigation export (PDF / CSV)

**As an** investigator, **I want** to export an entity's evidence pack and timeline as a self-contained PDF or CSV, **so that** I can share findings with reviewers and external stakeholders.

**Acceptance Criteria:**
1. An "Export" action on the entity detail panel offers PDF and CSV options.
2. PDF includes: entity properties, evidence-pack reasoning, score cards, a rendered subgraph image, and the timeline chart, all laid out for letter-size print.
3. CSV variant emits tabular evidence (one row per supporting fact) plus a header block with entity metadata.
4. Export endpoints are role-gated (analyst, admin) and tenant-scoped per E11-S04.
5. Integration test renders a fixture entity to PDF and verifies the file opens as a valid PDF and contains the expected text spans.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E12-S01, E12-S03 |

**Notes:** Use a server-side renderer (e.g., WeasyPrint for PDF) to keep the SPA bundle small; do not rely on `window.print` for the canonical export format.

---

## Epic 13: Active Monitoring & Real-Time Pipeline

> Make the live monitoring path of the architecture (Flow B) actually run end-to-end — claim ingestion, distributed real-time push, audit trails, and pipeline reliability primitives.

### E13-S01: Claim ingestion API endpoint

**As an** upstream system, **I want** to push claim records to chiliAI over HTTP, **so that** they enter the analysis pipeline without a custom integration per source.

**Acceptance Criteria:**
1. `POST /ingest/claims` accepts a JSON batch (`{ batch_id?, claims: [...] }`) of up to a configurable max size (default 1000).
2. Each claim is validated against the entity definition for `claim` in the active `DomainConfig`; validation failures return per-record errors and a `207 Multi-Status` response.
3. Valid claims emit `claims.received` events with a `correlation_id` and `tenant_id`; the response is `202 Accepted` with the resulting `batch_id`.
4. The endpoint enforces analyst-or-admin role and respects the per-tenant alert/storage quotas from E11-S05.
5. Integration test publishes 100 claims and verifies (a) the corresponding entities and relationships appear in the graph, (b) at least one alert is generated when seeded with anomalous claims, (c) duplicate batch ids are de-duplicated.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E11-S04, events bus already wired |

**Notes:** Schema-on-the-fly: do not add `Claim` as a hardcoded type. Use the generic `Entity(type="claim", properties=...)` pattern per `CLAUDE.md` rule #3.

---

### E13-S02: Polled-feed claim source adapter

**As an** operator, **I want** a worker variant that polls a configured source for claim files, **so that** existing batch-export workflows can feed chiliAI without standing up a push integration.

**Acceptance Criteria:**
1. A new worker adapter polls one of: (a) S3 prefix for new objects, (b) HTTP endpoint with cursor-based pagination, (c) Kafka topic (stub adapter behind a protocol).
2. Source configuration is declared in `DomainConfig.ingestion.sources[]`; the worker discovers and starts one consumer per declared source on boot.
3. Each polled record is normalized into a `claims.received` event identical to the API-push path.
4. Consumer state (cursor, last-seen object key) is persisted in Redis so restarts are idempotent.
5. Integration test runs the S3 variant against MinIO with a fixture prefix and asserts events match the file contents.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E13-S01 |

**Notes:** The Kafka adapter can be a stub initially — declare the protocol and add a `NotImplementedError` adapter; do not block the epic on a real Kafka deployment.

---

### E13-S03: WebSocket bridge to Redis pub/sub

**As an** analyst, **I want** alerts produced by any worker to reach my browser, **so that** running multiple API replicas does not silently drop real-time updates.

**Acceptance Criteria:**
1. `backend/api/routers/ws.py` subscribes to a Redis pub/sub channel populated by the alert and pipeline producers; the in-process broadcast path is removed for these event classes.
2. Existing client filtering by KB and severity is preserved via subscription metadata; per-client tenant scoping is enforced from the JWT.
3. The "Epic 8" comment at `backend/api/routers/ws.py:7` is removed.
4. Integration test runs two API replicas + one worker (Compose-based) and asserts both connected clients receive an alert produced by the worker.
5. Reconnect storms are bounded by exponential backoff at the server side (in addition to the existing client-side backoff) to prevent thundering herds against Redis on a restart.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | events bus, E11-S04 |

**Notes:** Use Redis pub/sub (not Streams) for fan-out — every replica needs every message. Keep Streams for the consumer-group pipeline events that need at-least-once delivery.

---

### E13-S04: KB ingestion progress over WebSocket

**As an** analyst, **I want** a progress meter on the KB detail page during ingestion, **so that** I know whether parsing, embedding, and indexing are progressing.

**Acceptance Criteria:**
1. The ingestion pipeline publishes `kb.progress` events at parse, chunk, extract, embed, and index milestones, including `processed`, `total`, and `current_step`.
2. The frontend subscribes to `/ws/kb/{kb_id}` and renders a progress bar plus a step label on the KB detail page.
3. When ingestion completes, a `kb.ready` event flips the KB status to `ready` in the UI without a manual refresh.
4. On error the progress bar shows an error state with the failure message and a retry affordance (admin only).
5. Vitest covers the progress hook with a mocked WebSocket; integration test seeds an ingestion job and asserts the expected sequence of events.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E13-S03 |

**Notes:** Keep the events coarse-grained — one event per milestone, not per chunk. Per-chunk events would saturate the WS hub on large KBs.

---

### E13-S05: Idempotency keys on ingestion and analysis events

**As a** platform operator, **I want** every pipeline event to carry an idempotency key, **so that** stream replays and consumer redeliveries do not corrupt the graph with duplicate writes.

**Acceptance Criteria:**
1. `EventBase.idempotency_key: str` is added (defaults to a deterministic hash of the event payload's natural key).
2. The graph builder, vector indexer, and alert evaluator de-duplicate against a Redis SET (`idem:{stream}:{key}`) with a configurable TTL (default 24 h).
3. A duplicate event is acknowledged on the stream but produces no side effects; a `pipeline_event_deduplicated_total` metric is incremented.
4. Integration test replays a 1000-event stream and asserts (a) graph entity counts match a single-pass run, (b) the dedup metric reports 1000 deduplications.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | events bus |

**Notes:** Natural keys: for `documents.uploaded` use `(kb_id, content_hash)`; for `claims.received` use `(tenant_id, claim_id)`; document the convention in `events/types.py`.

---

### E13-S06: Dead-letter queue for failed events

**As an** operator, **I want** events that exceed their retry budget to land on a DLQ, **so that** I can inspect and replay failures instead of losing them in logs.

**Acceptance Criteria:**
1. Each consumer's retry policy includes a `max_retries` and on exhaustion publishes the original event plus a `failure_reason` and `retry_count` to `<stream>.dlq`.
2. `GET /admin/events/dlq?stream=...&limit=...` lists DLQ entries (admin only).
3. A `scripts/replay_dlq.py` CLI replays selected DLQ entries back to their source stream after manual inspection.
4. `pipeline_dlq_total{stream, failure_kind}` metric is incremented on every DLQ write.
5. Integration test forces a consumer to fail beyond `max_retries` and asserts the event ends up on the DLQ with the failure reason.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | events bus |

**Notes:** Keep DLQ schema identical to the source stream's envelope plus a wrapping `dlq_metadata` field, so replay can re-emit verbatim.

---

### E13-S07: Audit log of analyst actions

**As a** compliance officer, **I want** every analyst action recorded with actor, timestamp, and payload, **so that** investigations are auditable for SOC 2 and HIPAA reviewers.

**Acceptance Criteria:**
1. Structured audit events are emitted for: KB create/delete, document upload/delete, alert acknowledge/resolve, configuration change, RAG query (with redacted PII per `DomainConfig.audit.redaction_rules`).
2. Audit records are written to a tamper-evident append-only store (JSONL on object storage, partitioned daily, with each record's hash chained to the previous record).
3. `GET /admin/audit?from=...&to=...&actor=...&action=...` returns paginated results; admin role required.
4. The audit stream is replicated, not just logged: log loss does not cause audit loss.
5. Integration test triggers each auditable action class and asserts a corresponding record appears with the expected fields and a valid hash chain.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | M | E11-S01, storage adapters |

**Notes:** Hash chaining is light-weight tamper evidence; full WORM storage can be added later by swapping the backing store.

---

### E13-S08: Alert routing to email, Slack, and webhook channels

**As an** on-call analyst, **I want** alerts to reach the channels I already monitor, **so that** I do not have to keep the workbench open at all times.

**Acceptance Criteria:**
1. `DomainConfig.monitoring.routing[]` declares per-tenant rules mapping severity and entity type to one or more channels.
2. Channel adapters: SMTP (email), Slack incoming webhook, generic webhook (configurable JSON template), each behind a `NotificationChannel` protocol with retry + backoff.
3. The monitoring service evaluates routing rules on alert generation and dispatches asynchronously; failures retry with backoff and ultimately land in the DLQ from E13-S06.
4. `notification_sent_total{channel, status}` and `notification_failed_total{channel, reason}` metrics.
5. Integration test asserts an alert produces the expected dispatch fan-out for a fixture routing rule set.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E13-S06, monitoring service |

**Notes:** Webhook templates use Jinja2; document a small set of safe variables to avoid SSRF or accidental PII leakage in URL paths.

---

## Epic 14: Analytics, RAG & Adapter Maturity

> Replace heuristic placeholders with the analytics the architecture promises, expand vendor coverage to match the spec, and harden the RAG pipeline against real-world failure modes.

### E14-S01: LLM-backed entity extractor

**As an** analyst, **I want** entities extracted with semantic understanding, **so that** the graph is a useful analysis surface instead of a noisy regex dump.

**Acceptance Criteria:**
1. `LlmDocumentExtractor` implements the existing `DocumentExtractor` protocol; selectable via `DomainConfig.ingestion.extractor.kind = "llm"`.
2. Per entity type, a structured-output prompt is generated from `DomainConfig.entities[].properties[]` using the LLM service's tool-calling or JSON-mode interface.
3. Coreference resolution and de-duplication run across chunks within a document via a deterministic key (lowercased canonical name + entity type) plus an embedding-based fuzzy match for near-duplicates.
4. Confidence calibration: confidences come from the LLM's logprobs or self-rating prompt, not from a regex coverage heuristic.
5. The pattern extractor remains as a fallback when the LLM service is unavailable, declared explicitly in config (`fallback: "pattern"`).
6. A regression suite at `tests/ingestion/regression/` runs the extractor against a fixed corpus and asserts precision/recall stays above a configured baseline (failing the build on regression).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P0 | L | LLM service, `backend/ingestion/extractor.py` |

**Notes:** TODOs at `backend/ingestion/extractor.py:36-44` enumerate the original design intent; this story closes them. Cross-chunk relationship extraction can be a separate follow-up if scope creeps.

---

### E14-S02: Real GNN inference module

**As an** analyst, **I want** real graph neural network outputs (link prediction, node classification), **so that** the "GNN" capability claim is honest and useful.

**Acceptance Criteria:**
1. PyTorch Geometric is integrated as an optional extra (`pip install -e ".[gnn]"`); imports are guarded for environments without the extra.
2. A `GnnInferenceService` implementation with GraphSAGE as the default architecture (configurable: GCN, GAT) sits behind the existing `GnnAnalyzer` protocol.
3. A `scripts/train_gnn.py` CLI reads a graph snapshot from the graph adapter, trains the model, and persists weights to object storage (`tenants/{tenant_id}/models/gnn/{run_id}.pt`).
4. Inference loads the latest persisted weights at startup and refreshes on a `model.updated` event; falls back to the existing heuristic when no weights are available.
5. Integration test trains on a fixture graph, persists weights, runs inference, and asserts link-prediction precision exceeds the heuristic baseline.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | L | storage, graph adapters |

**Notes:** Keep the heuristic fallback. Greenfield deployments do not have a trained model on day one and should still produce useful (if weaker) outputs.

---

### E14-S03: Production time-series detector

**As an** analyst, **I want** time-series anomaly detection grounded in established algorithms, **so that** alerts are not dominated by simple z-score false positives.

**Acceptance Criteria:**
1. A pluggable detector behind the existing protocol; default: Isolation Forest (scikit-learn).
2. Optional adapters for Prophet and ARIMA gated behind extras (`pip install -e ".[timeseries-prophet]"`, `".[timeseries-arima]"`).
3. Per-metric model selection in `DomainConfig.alerts.thresholds[entity_type][metric].detector`.
4. Models train on a rolling window and persist to object storage like the GNN models.
5. Backtest CLI (`scripts/backtest_timeseries.py`) scores precision/recall against a labeled fixture series and prints a comparison table.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | analytics/timeseries, storage |

**Notes:** Z-score remains as a fallback when no model is trained for a metric. Document the trade-off in `docs/architecture.md` §6.3.

---

### E14-S04: ML-based risk scorer with backtest harness

**As an** analyst, **I want** risk scores grounded in historical fraud labels, **so that** rule-based scoring is supplemented (and ultimately replaced) by a calibrated model.

**Acceptance Criteria:**
1. A label store (Postgres table or object-store JSONL) records `(entity_id, label, labeled_by, labeled_at, confidence)` for confirmed-fraud / cleared cases sourced from the audit log (E13-S07).
2. A gradient-boosting model (LightGBM) trains on labeled features extracted from the graph and analytics outputs; persisted via the same model-storage convention as E14-S02 / E14-S03.
3. The risk scoring service ensembles the trained model with the existing rules engine using a configurable weight; falls back to rules-only when no model is trained.
4. `scripts/backtest_risk.py` produces a calibration plot (reliability diagram) and PR curve.
5. Integration test asserts ensembled scores beat rules-only on the fixture label set above a configured margin.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E13-S07 |

**Notes:** The label store must respect tenant scoping and PII redaction policies — fraud labels are sensitive.

---

### E14-S05: Local explanations (SHAP) on risk and anomaly scores

**As an** investigator, **I want** to see which features pushed an entity's score up or down, **so that** I can defend the decision to escalate or clear an alert.

**Acceptance Criteria:**
1. SHAP values are computed for each risk and anomaly score and attached to the `EvidencePack`'s `scores` field as `{score: float, contributions: [{feature, value, shap}]}`.
2. The Evidence panel renders contributions as a horizontal bar chart with positive (red) and negative (green) factors.
3. SHAP computation has a configurable timeout; when exceeded the response includes `scores` without `contributions` and logs a warning (graceful degradation).
4. Integration test seeds an entity with known features and asserts the SHAP contributions sum to (model output − baseline) within tolerance.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E12-S01, E14-S04 |

**Notes:** For tree models, use TreeSHAP for speed; document the constraint that swapping in a non-tree model requires KernelSHAP and a higher timeout budget.

---

### E14-S06: Memgraph adapter

**As a** platform operator, **I want** a Memgraph adapter, **so that** I can deploy a lighter-weight graph backend than Neo4j without writing my own integration.

**Acceptance Criteria:**
1. `backend/graph/adapters/memgraph.py` implements `GraphRepository` with the same surface as the Neo4j adapter.
2. Selectable via `DomainConfig.graph.backend = "memgraph"`.
3. Integration tests run against the Memgraph container in CI when an opt-in flag is set (`pytest -m integration --memgraph`).
4. `infra/` includes a Memgraph service definition for the dev compose file (commented-out by default).
5. README documents the parity surface and any feature differences vs. Neo4j.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E2 graph protocol |

**Notes:** Memgraph speaks Cypher; the Neo4j adapter's queries should mostly transfer. Watch for differences in transaction semantics and `apoc` dependencies.

---

### E14-S07: Neptune adapter

**As an** AWS-native operator, **I want** a Neptune adapter, **so that** I can deploy chiliAI on managed AWS infrastructure.

**Acceptance Criteria:**
1. `backend/graph/adapters/neptune.py` implements `GraphRepository` using the openCypher endpoint (preferred) with a Gremlin fallback.
2. Authentication uses IAM SigV4; documented role pattern in `infra/README.md`.
3. Integration tests can be run against a real Neptune cluster via a `pytest -m integration --neptune` flag and a connection-string env var; CI does not require a live cluster by default.
4. The adapter handles Neptune-specific quirks (no `MERGE`, eventual consistency on read replicas) and documents them in the module docstring.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E2 graph protocol |

**Notes:** Test fixtures should run against the in-memory adapter for unit tests; Neptune integration tests are opt-in to keep CI fast and cheap.

---

### E14-S08: pgvector adapter

**As an** operator with an existing PostgreSQL footprint, **I want** a pgvector adapter, **so that** I can collocate vectors with my relational data instead of running a separate Qdrant cluster.

**Acceptance Criteria:**
1. `backend/vectorstore/adapters/pgvector.py` implements the `VectorStore` protocol.
2. A migration script (alembic or hand-written SQL) provisions the `vector` extension and the embedding tables per tenant collection.
3. Distance metrics: cosine, dot, euclidean — selectable per collection.
4. Integration tests run against a `pgvector` Docker image in CI.
5. Performance smoke test asserts query latency stays under a documented threshold for a fixture collection of 100k vectors (advisory, not a hard gate).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | vector protocol |

**Notes:** Use PostgreSQL ≥ 15 and `pgvector` ≥ 0.6 for HNSW indexing. Document the version requirements in `infra/README.md`.

---

### E14-S09: Weaviate adapter

**As an** operator preferring Weaviate, **I want** a Weaviate adapter, **so that** I can use schema-rich vector storage.

**Acceptance Criteria:**
1. `backend/vectorstore/adapters/weaviate.py` implements the `VectorStore` protocol.
2. Class schema is generated from the `EmbeddingsConfig` and `DomainConfig.entities[]` so existing embeddings can be hydrated with entity metadata at query time.
3. Integration tests run against a Weaviate Docker image in CI.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | vector protocol |

**Notes:** Skip Weaviate's hybrid search initially; add it as a follow-up once the basic adapter is stable.

---

### E14-S10: Ollama / vLLM LLM adapter

**As an** on-premises operator, **I want** an Ollama or vLLM LLM adapter, **so that** I can run chiliAI without egress to OpenAI or Anthropic.

**Acceptance Criteria:**
1. `backend/llm/adapters/ollama.py` (and a thin `vllm.py` wrapper if their APIs diverge) implements the `LlmClient` protocol with streaming support.
2. Selectable via `DomainConfig.llm.provider = "ollama"`.
3. Documented model-pull procedure in `infra/README.md`; default model declared in the medicare_fraud config example.
4. Smoke test runs against an Ollama container with a small model in CI.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | LLM protocol |

**Notes:** vLLM exposes an OpenAI-compatible API; consider whether the existing OpenAI adapter can be reused with a base-URL override before writing a fresh adapter.

---

### E14-S11: RAG resilience pass

**As an** analyst, **I want** the RAG pipeline to handle slow LLM responses, transient failures, and graph-expansion outages gracefully, **so that** chat is reliable in real-world conditions.

**Acceptance Criteria:**
1. Per-stage timeouts (`embed_query`, `vector_retrieval`, `graph_expansion`, `answer_generation`) are configurable in `DomainConfig.rag.timeouts` and enforced in `backend/rag/service.py`.
2. Retry-with-exponential-backoff on transient LLM errors (rate limits, 5xx) with a configurable budget.
3. An in-process LRU cache on `(query_hash, kb_id)` with a short TTL (default 60 s) reduces repeated identical queries.
4. A circuit breaker on the graph-expansion stage degrades gracefully — RAG continues with vector-only context when the graph is unavailable, marking the response as `degraded: true`.
5. The TODOs at `backend/rag/service.py:43-46` are removed.
6. Tests cover each resilience primitive with a fault-injecting bridge.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | RAG service |

**Notes:** Consider whether the cache should be per-tenant or shared; default to per-tenant to avoid leaking signals across tenancy boundaries.

---

### E14-S12: Persisted RAG conversations

**As an** analyst, **I want** my chat conversations to survive a page refresh, **so that** I can return to a thread the next day.

**Acceptance Criteria:**
1. Server-side conversation store (database table) keyed by `(tenant_id, user_id, conversation_id)`.
2. `GET /chat/conversations` (paginated list), `GET /chat/conversations/{id}` (full transcript), `DELETE /chat/conversations/{id}` endpoints.
3. The frontend chat store rehydrates from the API on load instead of starting empty.
4. Tenant + user scoping enforced at the adapter layer per E11-S04.
5. Integration test creates a conversation, refreshes (simulated), and asserts the transcript is returned intact.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E11-S01, E11-S04 |

**Notes:** Put a retention policy in `DomainConfig.rag.retention_days` so conversations expire predictably under data-minimization requirements.

---

### E14-S13: Citations clickable into Investigation Workbench

**As an** analyst, **I want** the source citations in a chat answer to deep-link to the Investigation Workbench, **so that** I can pivot from "what did the LLM say?" to "show me the entity."

**Acceptance Criteria:**
1. Each `SourceCitation` carries `entity_id` and/or `document_id` plus `chunk_id` where applicable.
2. Citations render as buttons; clicking an entity citation navigates to `/investigation?entity=<id>&kb=<id>` and selects the entity; clicking a document citation opens the document viewer scrolled to the chunk.
3. Vitest covers both navigation paths.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E14-S12 |

**Notes:** This is the connective tissue between the conversational and graph experiences — small change, high analyst-perceived value.

---

## Epic 15: Operations & Quality Bar

> Production hardening that is not feature-shaped but is required to ship: rate limiting, observability completion, E2E coverage, type-safe API client, secrets, autoscaling, IaC, and user documentation.

### E15-S01: HTTP rate limiting middleware

**As a** platform operator, **I want** HTTP rate limiting on the API, **so that** a runaway client cannot exhaust resources or cost.

**Acceptance Criteria:**
1. A token-bucket middleware applies per-`(tenant_id, route_class)` limits configured in `DomainConfig.api.rate_limits`.
2. Limit exceeded returns `429 Too Many Requests` with a `Retry-After` header and a structured error body.
3. The metrics endpoint and health checks are exempt; auth endpoints have stricter limits than read endpoints.
4. `http_rate_limited_total{tenant_id, route_class}` metric.
5. Integration test bursts requests above the configured limit and asserts the expected `429`s plus eventual recovery.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | E11-S04 |

**Notes:** Use a Redis-backed token bucket so rate limits are consistent across replicas; the in-process variant is a fallback for single-replica deployments.

---

### E15-S02: OpenTelemetry exporter wired

**As an** operator, **I want** OpenTelemetry traces flowing to my tracing backend, **so that** I can debug cross-service requests in production.

**Acceptance Criteria:**
1. OTLP exporter configured by env (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`).
2. Trace ids propagate through Redis Stream events via the existing `correlation_id` field, so worker spans connect to API spans.
3. Documentation covers Jaeger and Tempo as reference targets; sample dashboards in `infra/observability/`.
4. Integration test asserts a representative request produces a connected span tree with API + worker + adapter spans.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | `backend/shared/tracing.py` |

**Notes:** Avoid sampling in CI tests so the assertion is deterministic; document a recommended production sampling ratio.

---

### E15-S03: Frontend Sentry integration

**As a** frontend developer, **I want** unhandled exceptions and slow page loads reported to Sentry, **so that** I can find regressions without watching the browser console.

**Acceptance Criteria:**
1. Sentry SDK initialized in `chili_app/src/main.tsx` with DSN from a build-time env var.
2. Release tagged with the CI commit SHA; source maps uploaded to Sentry as part of the production build.
3. Sample rates configurable; default `traces_sample_rate=0.1` in production.
4. PII scrubbing rules redact tokens and user identifiers from breadcrumbs.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | S | None |

**Notes:** Disable Sentry in dev by default; opt in via env var to avoid noisy local sessions.

---

### E15-S04: Browser-based E2E test suite (Playwright)

**As a** lead developer, **I want** browser-based E2E tests on the golden path, **so that** cross-stack regressions are caught in CI before release.

**Acceptance Criteria:**
1. A Playwright suite at `e2e/` covers: login, create KB, upload doc, watch ingestion finish, see alert, ack alert, open investigation, view evidence, run RAG query, save config.
2. Tests run against the dev compose stack started by a CI job.
3. Failure artifacts (video, trace) uploaded to the run.
4. Suite runs on every PR and on `main`; flaky tests quarantined behind a known-flaky marker, not silently ignored.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P1 | M | E11-S02 |

**Notes:** Keep the suite small and golden-path focused; resist the urge to mirror unit-test coverage. E2E is for the seams.

---

### E15-S05: Pre-commit hooks for ruff, pyright, eslint, prettier

**As a** developer, **I want** local pre-commit hooks that run the same lint/type checks as CI, **so that** I do not push code that will fail the pipeline.

**Acceptance Criteria:**
1. `.pre-commit-config.yaml` covers ruff (check + format), pyright (changed files), eslint, and prettier.
2. README documents the one-line install (`pre-commit install`).
3. CI verifies the config is in sync (running `pre-commit run --all-files` should match CI's lint/type results).

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E10-S01 |

**Notes:** Pyright on full repo is slow; the hook should run only on changed files. CI keeps the full check.

---

### E15-S06: Generated TypeScript API client

**As a** frontend developer, **I want** a generated TypeScript API client from the backend's OpenAPI spec, **so that** type drift between FE and BE becomes impossible.

**Acceptance Criteria:**
1. A build step runs `openapi-typescript-codegen` (or a comparable tool) against the running API and writes the client to `chili_app/src/api/generated/`.
2. The hand-rolled `apiClient.ts` is migrated incrementally to the generated client; existing TanStack Query hooks wrap the generated functions.
3. CI fails when the generated client is out of sync with the OpenAPI spec.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | None |

**Notes:** Migrate hooks one router at a time to avoid a multi-thousand-line diff. The migration is mechanical but reviewable.

---

### E15-S07: External secrets integration

**As an** operator, **I want** secrets resolved from Vault or AWS Secrets Manager, **so that** I do not have to bake them into Kubernetes Secrets manually.

**Acceptance Criteria:**
1. A pluggable `SecretResolver` protocol with adapters for env, Vault, and AWS Secrets Manager.
2. All `*_env_var` indirections in `DomainConfig` route through the resolver; legacy env-var resolution remains the default.
3. The Helm chart documents the External Secrets Operator integration as a recommended deployment pattern.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | None |

**Notes:** Avoid runtime secret rotation in this story; keep it boot-time only. Rotation is a separate, larger piece of work.

---

### E15-S08: KEDA autoscaling on Redis Stream depth

**As an** operator, **I want** the worker to scale on pending message count rather than CPU, **so that** ingestion bursts get more replicas in time.

**Acceptance Criteria:**
1. A `ScaledObject` for `chili-worker` driven by KEDA's Redis Streams scaler, targeting pending-message count.
2. Default thresholds documented in `infra/helm/chili/values.yaml`; production override in `values-prod.yaml`.
3. Existing CPU-based HPA replaced (not duplicated) to avoid conflicting autoscalers.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P3 | S | infra/helm |

**Notes:** Validate against a synthetic load test before declaring the thresholds production-grade.

---

### E15-S09: Bulk document upload with per-file progress

**As an** operator onboarding a large KB, **I want** to upload many documents at once with per-file progress, **so that** I can leave the page and return to find the batch finished.

**Acceptance Criteria:**
1. The KB document upload UI accepts multi-file selection or drag-drop of a folder.
2. Each file is uploaded in parallel (configurable concurrency) with its own progress bar; failures are isolated and retryable.
3. The backend handles concurrent uploads against the same KB without graph corruption (relies on E13-S05 idempotency).
4. Vitest covers progress updates, retry, and partial-batch failure.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | M | E13-S05 |

**Notes:** Push the parallelism control down to a small util used by both this UI and any future scripted bulk-upload tool.

---

### E15-S10: Analyst quick-start guide

**As a** first-time analyst user, **I want** a quick-start guide, **so that** I can run my first investigation without reading the architecture document.

**Acceptance Criteria:**
1. `docs/user-guide.md` covers: signing in, creating a KB, uploading documents, monitoring ingestion progress, working through an alert, exploring an entity, asking a RAG question, exporting a report, editing the domain configuration.
2. Screenshots are taken from the dev compose stack and re-generatable via a documented procedure.
3. Linked from the workbench Help menu.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P2 | S | E11-S02, E12-S01..S07, E13-S04, E14-S11 |

**Notes:** Defer this until the user-visible epics above land; the screenshots will rot otherwise.

---

### E15-S11: Workflow state persistence in agent coordinator

**As an** operator, **I want** in-flight pipelines to resume after a worker restart, **so that** routine deploys do not leave half-processed documents behind.

**Acceptance Criteria:**
1. Pipeline state for in-flight workflows is persisted in Redis (or a database) with the workflow id as key.
2. On boot, the coordinator scans for in-flight workflows owned by the same logical worker pool and resumes them at the next pending step.
3. At-least-once + idempotency (E13-S05) guarantees correctness across resumes.
4. Integration test starts a workflow, kills the worker mid-flight, restarts, and asserts the workflow completes with the same final graph state as a no-restart run.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P3 | M | E13-S05 |

**Notes:** Resist designing a full workflow engine. Persist the minimum state needed to resume; let the event bus do the heavy lifting.

---

### E15-S12: Terraform module for AWS reference deployment

**As an** AWS operator, **I want** a Terraform module that provisions a reference chiliAI environment, **so that** I do not have to translate the Helm chart and Kubernetes manifests by hand.

**Acceptance Criteria:**
1. `infra/terraform/aws/` contains modules for: VPC, EKS, ElastiCache (Redis), S3, IAM roles for the API and worker, and a Helm release that deploys the chart from `infra/helm/chili/`.
2. A `terraform plan` against the example tfvars produces no changes after a first `apply` (idempotency).
3. README documents prerequisites (AWS account, region, kubectl, helm) and the apply procedure.
4. Reference module is smoke-tested manually before tagging a release; not gated on CI to avoid AWS spend.

| Priority | Size | Dependencies |
|----------|------|--------------|
| P3 | L | infra/helm |

**Notes:** Keep modules small and composable; do not produce a single mega-module. Document what is intentionally excluded (e.g., DNS, ACM, observability stack) so users know what to add.

---

## Cross-References to Existing Backlog

Several stories in this addendum extend or depend on work already tracked in `backlog.md`:

| Addendum story | Extends / depends on |
|----------------|----------------------|
| E11-S01 | E10-S06 (Auth middleware) |
| E11-S03 | E10-S07 (RBAC) |
| E12-S05 | E5 (KB router), E2 (graph upserts), E13-S05 (idempotency) |
| E12-S06 | E5 (config router) |
| E13-S03 | E8 (alert events), E13-S05 |
| E13-S07 | E11-S01, storage adapters |
| E14-S01 | E6 (RAG / LLM service), `backend/ingestion/extractor.py` |
| E14-S02..S04 | E7 (analytics suite) |
| E15-S05 | E10-S01 (CI) |
| E15-S08 | E10-S11 (Helm chart) |

The 12 P0 stories in this addendum represent the closing-the-must-have set: turning auth on (E11-S01..S03), making the Investigation Workbench tell a complete story (E12-S01..S07), wiring the live pipeline (E13-S01, S03, S07), and replacing regex extraction (E14-S01).
