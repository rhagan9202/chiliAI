# api backlog

> **Scope:** FastAPI gateway — route surface, DI wiring, contracts, middleware, realtime channels, auth integration, error envelope, versioning.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story api.01: Replace seeded API graph and evidence reads

**ID:** api.01
**Status:** done
**Prerequisites:** [graph.06, graph.08, ingestion.05, monitoring.01]
**Unblocks:** [api.28]
**Estimated size:** L
**Done:** graph entity reads and evidence-pack reads are service/repository-backed; missing persisted evidence now returns 404 instead of seeded fallback.

### Narrative
As an API consumer,
I want graph and evidence endpoints to read from persisted services,
so that responses reflect imported data rather than seeded in-memory state.

### Current State
Completed. `GET /graph/entities/{id}` is served by `api/_graph_entity_payload.py` through the graph service, and `GET /evidence-packs/{id}?knowledge_base_id=` reads from `EvidencePackRepository` via `get_evidence_pack_repository`. Regression coverage in `backend/tests/api/test_read_model_routers.py` asserts missing persisted evidence returns 404 instead of seeded fallback.

### Acceptance Criteria
- [x] Replace graph endpoint reads with graph service queries backed by persisted storage.
- [x] Replace evidence/document endpoint reads with repository-backed data.
- [x] Preserve response contracts used by the frontend and tests.
- [x] Add not-found behavior for missing persisted records instead of falling back to seed data.

### Verification
- [x] API tests prove graph and evidence responses come from test repositories.
- [x] Seeded demo data is not required for these endpoints to pass.

### Code touch points
- `backend/app/api/**`
- `backend/app/services/**`
- `backend/tests/api/**`

---
## Story api.02: Persist cases behind a CaseRepository protocol

**ID:** api.02
**Status:** planned
**Prerequisites:** [api.29, database.02, _security.05, _multitenancy.04]
**Unblocks:** [_plugins.04]
**Estimated size:** L

**As a** platform engineer,
**I need** `CaseRepository` + Postgres adapter (with Alembic migration, tenant column, RBAC-aware writes, audit hooks),
**so that** `/cases` no longer loses every case on API restart and works across multiple API processes.

### Current State
- Case persistence is implemented under `backend/cases/` with in-memory and Postgres repositories, service methods, migrations `0002_cases.py` and `0007_case_feedback.py`, and route DI through `get_case_repository` / `get_case_service`.
- `/cases` supports KB-scoped list/detail/create/update/feedback plus `POST /cases/promote?knowledge_base_id=...`; cross-KB alert promotion returns 404.
- Completed de-seeding is covered by `backend/tests/api/test_deseed_regression.py` and case route coverage in `backend/tests/api/test_read_model_routers.py`.
- Still pending from the original story: tenant/resource-level authorization and durable audit events for every case mutation.
- **PM status note (2026-06-23):** the core capability is **substantially shipped** (5 of 7 AC checked; cases module + migrations live — verified `backend/cases/`, `database/migrations/versions/0002_cases.py`). Status is kept `planned` (not `in-progress`) only because the consistency validator requires every prerequisite to be `done` for `in-progress`, and this story's residual AC genuinely depend on `_security.05` (identity) + `_multitenancy.04` (tenant column) which are not yet done. Effective state: ~70% done, tenant-auth/audit tail remaining.

### Acceptance Criteria
- [x] `backend/cases/adapters/protocols.py` declares `CaseRepository` with create/get/list/update/add-feedback operations.
- [x] In-memory + Postgres adapters implemented; Postgres migrations create `cases` and `case_feedback`.
- [x] `get_case_*_payload` providers consume the repository and case service, not `ApiState`.
- [x] `ApiState._cases`, `ApiState._feedback`, `ApiState._seed_cases` removed.
- [ ] Tenant/resource-level fields and authorization are added to the case persistence contract.
- [ ] Audit event published on every mutation per `_security.05` audit log shape.
- [ ] Coverage ≥ 85% on the new module/package.

### Verification
- `pytest backend/tests/api/test_cases.py backend/tests/cases/` green.
- `make dev` + restart API container; `POST /cases` then `GET /cases/{id}` after restart still returns the case.
- `make test` coverage report shows ≥ 85% for the cases package.

### Code touch points
- `backend/cases/__init__.py` (new — if new module chosen)
- `backend/cases/protocols.py` (new)
- `backend/cases/adapters/in_memory.py` (new)
- `backend/cases/adapters/postgres.py` (new)
- `backend/database/migrations/versions/<rev>_cases.py` (new)
- `backend/api/dependencies.py` (modify)
- `backend/api/state.py` (modify — remove case state)
- `backend/api/routers/cases.py` (modify if signatures change)
- `backend/tests/cases/` (new)

---

## Story api.03: Persist RAG chat conversations behind a repository

**ID:** api.03
**Status:** planned
**Prerequisites:** [api.29, database.02, rag.10, _multitenancy.04]
**Unblocks:** [rag.05]
**Estimated size:** L

**As a** platform engineer,
**I need** durable RAG conversation storage (conversations + messages + citation references) shared across API workers,
**so that** `/chat/conversations` survives restarts, supports horizontal scale-out, and persists citation provenance produced by `_rag_bridges.py`.

### Current State
- Durable conversation storage is implemented under `backend/conversations/` with in-memory and Postgres repositories and migration `0005_conversations.py`.
- `/chat/conversations` create/read/append routes use `ConversationService` through DI (`get_conversation_repository`, `get_conversation_service`, `get_chat_message_payload`) and no longer call `ApiState` conversation methods.
- The live RAG service is composed in `get_rag_service()` through `_rag_bridges.py`; `ApiState` only holds the service handle/fallback for tests.
- Still pending from the original story: audit-grade citation attachment/provenance persistence beyond the current message/citation response projection.
- **PM status note (2026-06-23):** the core capability is **substantially shipped** (conversations module + migration `0005_conversations.py` verified live, 4 of 7 AC checked). Kept `planned` (not `in-progress`) only because the validator requires all prerequisites `done` for `in-progress`, and the residual AC depend on `rag.10` + `_multitenancy.04` (not yet done). Effective state: ~60% done, citation-provenance + tenant tail remaining.

### Acceptance Criteria
- [x] `backend/conversations/adapters/protocols.py` declares the conversation repository and in-memory + Postgres adapters ship with migration `0005_conversations.py`.
- [x] `_rag_bridges.py` is in the live `get_rag_service()` composition path.
- [x] `ApiState._conversations`/`_seed_conversations` removed.
- [x] `/chat/conversations[/...]` routes consume the repository via DI; streaming path still works.
- [ ] Citation attachment/provenance is persisted at audit grade rather than only projected in message responses.
- [ ] Streaming path (`?stream=true` at `backend/api/routers/rag.py:65-105`) persists assistant tokens and citations on completion.
- [ ] Coverage ≥ 85% on the new repository.

### Verification
- `pytest backend/tests/api/test_chat_router.py backend/tests/rag/test_conversation_store.py` green.
- `make dev`; create a conversation, add a message with `?stream=true`, restart the worker container, GET `/chat/conversations/{id}` — full transcript + citations returned.
- Coverage gate met.

### Code touch points
- `backend/rag/protocols.py` (modify — add `RagConversationRepository`)
- `backend/rag/adapters/in_memory_conversations.py` (new)
- `backend/rag/adapters/postgres_conversations.py` (new)
- `backend/database/migrations/versions/<rev>_rag_conversations.py` (new)
- `backend/api/_rag_bridges.py` (modify — wire into projection path)
- `backend/api/dependencies.py` (modify)
- `backend/api/state.py` (modify — remove conversation state)
- `backend/api/routers/rag.py` (modify)
- `backend/tests/rag/test_conversation_store.py` (new)

---

## Story api.04: Persist policy-intelligence gaps and briefs

**ID:** api.04
**Status:** dropped
**Prerequisites:** [api.29, analytics.15, monitoring.16, database.02]
**Unblocks:** []
**Estimated size:** L

**As a** platform engineer,
**I need** policy gaps and policy briefs persisted in a real `PolicyIntelligenceRepository` linked to analytics + KB lifecycle events,
**so that** `/policy/gaps` and `/policy/briefs` carry audit history, survive restarts, and reflect actual analytics output instead of seeded `PolicyGapRecord` objects.

### Current State
Superseded by the BL-011 policy item surface. The legacy `/policy/gaps`, `/policy/gaps/{id}`, `/policy/gaps/{id}/cases`, and `/policy/briefs` routes are gone; `backend/tests/api/test_policy_router.py` asserts `/policy/gaps` returns 404 and that the old `PolicyGapRecord` / `_seed_policy_gaps` symbols are absent. The active policy routes are `GET /policy/items`, `GET /policy/items/{item_id}`, and `POST /policy/items/{item_id}/triage`, backed by `backend/policy/` repositories and migration `0003_policy.py`.

### Acceptance Criteria
- [ ] `PolicyIntelligenceRepository` protocol (gaps, briefs, citations, trend, affected cases) with in-memory + Postgres adapters.
- [ ] Alembic migration creates `policy_gaps`, `policy_briefs`, `policy_gap_cases`, `policy_gap_trend_points` tables.
- [ ] `analytics.15` (policy-gap detection pipeline) is the source of new gaps; this story consumes that output.
- [ ] `ApiState._policy_gaps`, `_seed_policy_gaps`, `_to_policy_gap_summary`, `list_policy_gaps`, `get_policy_gap_detail`, `list_policy_gap_cases`, `create_policy_brief` deleted.
- [ ] Policy router pagination honours `limit`/`offset` (closes the bug noted in api.10).
- [ ] Coverage ≥ 85% on the new repository.

### Verification
- `pytest backend/tests/api/test_policy_router.py` green with no `ApiState` fixture.
- `make dev` + restart; gaps written via analytics output persist across restart.
- Coverage gate met.

### Code touch points
- `backend/analytics/policy/repository.py` (new — module decision recorded in architecture if non-trivial)
- `backend/analytics/policy/adapters/{in_memory,postgres}.py` (new)
- `backend/database/migrations/versions/<rev>_policy_gaps.py` (new)
- `backend/api/dependencies.py` (modify)
- `backend/api/state.py` (modify — drop policy state)
- `backend/api/routers/policy.py` (modify — honour pagination)
- `backend/tests/analytics/policy/` (new)

---

## Story api.05: Bridge WebSocket hub to Redis Streams

**ID:** api.05
**Status:** planned
**Prerequisites:** [events.01, events.05, monitoring.16, agent.17]
**Unblocks:** [agent.19, api.06, frontend.18]
**Estimated size:** L

**As a** SPA user,
**I need** alerts and pipeline-stage events published by the worker over Redis Streams to be fanned out to my `/ws/alerts` and `/ws/pipeline` subscriptions,
**so that** the dashboard updates in real time without relying on in-process broadcast calls.

### Current State
- `backend/api/routers/ws.py:4-7` documents the gap: "The actual bridge between the event bus (Redis Streams) and this hub is wired in Epic 8 — for now the hub accepts direct broadcast calls".
- `WebSocketHub.broadcast` (`backend/api/routers/ws.py:118-134`) is purely process-local.
- `AlertCreatedEvent` (and pipeline-stage events) are published by the coordinator but never reach connected clients.
- No background task in `create_app` (`backend/api/app.py:102-164`) consumes from the event bus.

### Acceptance Criteria
- [ ] A `WebSocketEventBridge` (new) subscribes to the configured event bus consumer group on API startup and dispatches matching events to `WebSocketHub.broadcast` on the right route.
- [ ] One-bridge-per-API-process model documented in `backend/api/README.md` (each API pod runs a bridge); resolves Open Question on bridge topology.
- [ ] Lifespan hook in `create_app()` starts/stops the bridge (`backend/api/app.py:102-164`).
- [ ] `AlertCreatedEvent` → `/ws/alerts`; pipeline-stage events (start/step/done/fail) → `/ws/pipeline`.
- [ ] Severity filter (`AlertSubscribeFilter`) and `kb_id` filter (`PipelineSubscribeFilter`) are enforced by the bridge dispatcher.
- [ ] Integration test: publish an event on the in-memory bus, assert all connected ws clients receive it; second test with Redis bus + Docker compose.
- [ ] Coverage ≥ 85% on the bridge module.

### Verification
- `pytest backend/tests/api/test_ws_bridge.py` green.
- `make dev`; open `/ws/alerts` with `wscat`, publish an alert through the worker, observe the event payload on the WS connection.

### Code touch points
- `backend/api/routers/ws.py` (modify — remove the Epic 8 TODO)
- `backend/api/ws_bridge.py` (new)
- `backend/api/app.py` (modify — lifespan hook to start/stop bridge)
- `backend/tests/api/test_ws_bridge.py` (new)
- `backend/api/README.md` (modify)

---

## Story api.06: Add WebSocket hub resilience and observability

**ID:** api.06
**Status:** planned
**Prerequisites:** [api.05, _observability.04, _infra.07]
**Unblocks:** [monitoring.01, monitoring.02, monitoring.04, monitoring.05]
**Estimated size:** M

**As a** platform operator,
**I need** the WebSocket hub to bound per-connection backpressure, cap clients, surface Prometheus gauges/counters, ack subscribe failures back to clients, and time out idle connections,
**so that** a slow consumer or accidental client storm cannot exhaust API process memory or silently mask configuration mistakes.

### Current State
- `WebSocketHub` keeps connections in a per-process dict (`backend/api/routers/ws.py:83-141`) with no per-connection send queue, no slow-consumer eviction beyond `WebSocketDisconnect`/`RuntimeError` catches (`backend/api/routers/ws.py:131-134`).
- No max-clients cap; no metrics — `prometheus_client` counters in `backend/api/middleware/metrics.py:29-39` track only HTTP.
- Ping is the only idle protection (`backend/api/routers/ws.py:36`, `_ping_loop` at `backend/api/routers/ws.py:153-160`).
- `subscribe` filter is silently dropped on `ValidationError` (`backend/api/routers/ws.py:169-170,183-184`).

### Acceptance Criteria
- [ ] `WebSocketHub` enforces `CHILI_WS_MAX_CLIENTS_PER_ROUTE` (default 1000) per route; over-limit clients receive 1013 (try-again-later) close.
- [ ] Per-connection bounded send queue with eviction on overflow; counter `chiliai_ws_drops_total` tracks evictions.
- [ ] Gauges `chiliai_ws_connections_active{route}` and `chiliai_ws_messages_sent_total{route}` exported via `/metrics`.
- [ ] Subscribe validation failures send an `{"error": "invalid_subscribe", "details": ...}` frame instead of silent drop.
- [ ] Idle timeout (no client message + no successful send in N seconds, configurable) closes the connection with 1000.
- [ ] Coverage ≥ 85% on `backend/api/routers/ws.py`.

### Verification
- `pytest backend/tests/api/test_ws_router.py` green covering all new branches.
- `make dev`; connect more clients than `CHILI_WS_MAX_CLIENTS_PER_ROUTE`, observe close code 1013.
- `curl :8000/metrics | grep chiliai_ws_` shows the new gauges/counters.

### Code touch points
- `backend/api/routers/ws.py` (modify)
- `backend/api/middleware/metrics.py` (modify — register ws metrics)
- `backend/tests/api/test_ws_router.py` (modify)

---

## Story api.07: Event-driven SSE with reconnect semantics

**ID:** api.07
**Status:** planned
**Prerequisites:** [events.02, _observability.04]
**Unblocks:** [frontend.01, frontend.07, frontend.15, rag.06]
**Estimated size:** M

**As a** SPA user,
**I need** `/events/stream` to push when state actually changes (and resume after disconnect via `Last-Event-ID`) instead of polling every 5 seconds,
**so that** workspace updates arrive promptly and reconnects do not redeliver the entire backlog.

### Current State
- `_stream_workspace_updates` polls every 5 seconds (`backend/api/routers/events.py:30-52`).
- Snapshot rebuild calls `repository.list(limit=500)` + `agent_service.list_workflows(limit=500)` + `count_active_alerts(...)` each tick (`backend/api/routers/events.py:85-109`).
- No `id:` field on emitted events (`backend/api/routers/events.py:50`), no `Last-Event-ID` resume.
- `max_events` is a test-only knob (`backend/api/routers/events.py:41-42,56`).

### Acceptance Criteria
- [ ] SSE loop subscribes to an in-process pub-sub primitive (from `events.02`) and pushes only on alert/workflow/KB state-change events.
- [ ] Each yielded event includes an `id:` line; `Last-Event-ID` header is honoured to resume from a checkpoint (bounded backlog).
- [ ] Per-client concurrency cap (`CHILI_SSE_MAX_CLIENTS`, default 200) with 503 on overflow.
- [ ] Heartbeat keep-alive every N seconds even when no events fire.
- [ ] Snapshot calls capped at one-per-state-change (no per-5s rebuild).
- [ ] Coverage ≥ 85% on `backend/api/routers/events.py`.

### Verification
- `pytest backend/tests/api/test_events_router.py` green.
- `make dev`; connect to `/events/stream`, mutate state via REST, observe a single SSE event within < 500 ms.
- `curl -H "Last-Event-ID: <id>" /events/stream` resumes correctly.

### Code touch points
- `backend/api/routers/events.py` (modify)
- `backend/api/sse_subscription.py` (new — lightweight subscriber)
- `backend/tests/api/test_events_router.py` (modify)

---

## Story api.08: Standardize the API error envelope

**ID:** api.08
**Status:** planned
**Prerequisites:** [shared.07, _observability.03, frontend.06]
**Unblocks:** [api.12]
**Estimated size:** M

**As a** frontend (and external) API consumer,
**I need** every error response to carry a uniform shape — `error_code`, human `message`, `correlation_id`, optional `details` — including Pydantic 422s,
**so that** the SPA, generated clients, and integrators can branch on `error_code` instead of regex-matching `detail` strings.

### Current State
- `HTTPException(detail=str)` in many routers: `backend/api/routers/knowledgebases.py:158-161,193-195`, `backend/api/routers/alerts.py:46-49`, `backend/api/routers/policy.py` indirectly via providers.
- `/knowledgebases/{id}` DELETE returns 207 with `{knowledge_base_id, pending_cleanup, steps[]}` (`backend/api/routers/knowledgebases.py:234-241`).
- `KbBusyError → 409 detail=str(exc)` (`backend/api/routers/knowledgebases.py:200-204`).
- `records` routes funnel three exception classes to three different status codes with raw `detail=str(exc)` (`backend/api/routers/records.py:95-107,132-144`).
- Mutations use `ApiEnvelope{status,message}` (`backend/api/contracts.py:11-15`); not an error model.
- No RFC 7807 shape; default FastAPI 422 body unchanged.

### Acceptance Criteria
- [ ] New `ApiError` Pydantic model (`error_code: str`, `message: str`, `correlation_id: str`, `details: dict | None`) in `backend/api/contracts.py` (or `shared/contracts` per api.09).
- [ ] Decision recorded (RFC 7807 problem+json vs. extended envelope) — see Open Question; pick one and apply consistently.
- [ ] `exception_handlers` in `create_app()` map `HTTPException`, `RequestValidationError`, and chiliai domain exceptions to `ApiError`.
- [ ] Every router migrated; coverage tests assert `error_code` for each documented failure mode (404, 409, 413, 415, 422, 500).
- [ ] `correlation_id` echoed from middleware (api.20).
- [ ] OpenAPI schema documents the error model for every router (api.12).

### Verification
- `pytest backend/tests/api/test_error_envelope.py` green covering 401/403/404/409/413/415/422/500.
- `curl -i :8000/alerts/does-not-exist` returns the standardised body.

### Code touch points
- `backend/api/contracts.py` (modify — or new `backend/api/contracts/errors.py`)
- `backend/api/app.py` (modify — register exception handlers)
- `backend/api/middleware/exceptions.py` (modify)
- `backend/api/routers/*.py` (modify — replace ad-hoc `HTTPException(detail=...)` raises)
- `backend/tests/api/test_error_envelope.py` (new)

---

## Story api.09: Consolidate request/response contracts into a single package

**ID:** api.09
**Status:** planned
**Prerequisites:** [shared.07, rag.11, graph.10, records.06]
**Unblocks:** [api.10, api.12]
**Estimated size:** M

**As a** API maintainer,
**I need** every request/response model to live in one contract package (`backend/api/contracts/` or `backend/shared/contracts/`) with a clean separation from `service_models`,
**so that** contract evolution touches one location, `openapi-typescript` emits stable names, and `service_models.py` stays internal.

### Current State
- Models split across `backend/api/contracts.py` (~37 models), `backend/api/routers/knowledgebases.py:54-91` (router-local `CreateKbRequest`, `DocumentRegistrationResponse`, `DocumentSummary`, `KbListResponse`, `DocumentListResponse`), `backend/api/routers/records.py:23-27` (`RecordPushRequest`), `backend/api/routers/ws.py:39-56` (WS subscribe filters).
- Service-layer models reused directly: `backend/api/routers/records.py:16` imports `RecordIngestReceipt`; `backend/api/routers/investigation.py:10-14` returns `graph.service_models.EntityDetailResponse`.
- Frontend codegen (`chili_app/package.json:13`) consumes whatever name FastAPI emits.

### Acceptance Criteria
- [ ] Decision recorded in `docs/architecture.md` §5.2: contracts under `backend/api/contracts/` (per-router submodule) OR `backend/shared/contracts/`.
- [ ] All router-local models migrated to the chosen package.
- [ ] `service_models` no longer used as a router `response_model`; an explicit API contract is published per surface.
- [ ] Migration regenerates `chili_app/src/lib/api/schema.ts` (see api.15) with stable names; diff reviewed.
- [ ] Coverage ≥ 85% on the contract package.

### Verification
- `rg "^class .*(Request|Response|Filter|Envelope)\b" backend/api/routers/` returns no matches (all moved).
- `npm run codegen:api` (with backend running) regenerates the schema; commit + diff review.
- `pytest backend/tests/api/` green.

### Code touch points
- `backend/api/contracts/__init__.py` (new — if package layout chosen)
- `backend/api/contracts/{alerts,cases,chat,knowledgebases,policy,records,workflows,ws,...}.py` (new)
- `backend/api/contracts.py` (delete after migration)
- `backend/api/routers/*.py` (modify — remove inline models)
- `backend/shared/contracts/` (new — alternative location)
- `docs/architecture.md` (modify — record decision)
- `chili_app/src/lib/api/schema.ts` (regenerated)

---

## Story api.10: Adopt a uniform paginated-collection contract

**ID:** api.10
**Status:** planned
**Prerequisites:** [api.09]
**Unblocks:** [analytics.15, analytics.17, api.11, api.12, frontend.16, records.10, records.13]
**Estimated size:** M

**As a** API consumer,
**I need** every list endpoint to return `{items, page: {page, page_size, total_items, next_cursor?}}` with consistent semantics,
**so that** UI list controls and external clients can paginate uniformly and never see a wrong `total`.

### Current State
- `AlertListResponse` returns `items[] + PageInfo{page,page_size,total_items}` (`backend/api/contracts.py:43-47`).
- `KbListResponse` returns `items[] + total` (`backend/api/routers/knowledgebases.py:67-71`).
- `WorkflowRunListResponse` returns `items[]` only with no total (`backend/api/contracts.py:269-272`).
- `EntitySearchResponse` is `items + total=len(items)` after the search already capped at `limit` (`backend/api/routers/investigation.py:114-115`) — `total` is wrong when paged.
- `PolicyItemListResponse` returns `items[] + total` for `/policy/items`; the legacy `/policy/gaps` route is no longer registered.
- `ApiEnvelope` is the only generic envelope (`backend/api/contracts.py:11-15`).

### Acceptance Criteria
- [ ] Decision recorded (cursor vs offset; see Open Question). Pick one and apply consistently.
- [ ] One `PageInfo` shape used by every list endpoint; every endpoint reports an accurate `total_items`.
- [ ] `WorkflowRunListResponse`, `KbListResponse`, `EntitySearchResponse` migrated to the uniform shape.
- [ ] `/policy/items` either migrates to the common page shape or the common contract explicitly allows simple `total` responses.
- [ ] Tests assert that `total_items > len(items)` when paging produces more results.

### Verification
- `pytest backend/tests/api/test_pagination.py` (new) green; covers every list endpoint.
- `curl :8000/workflows?limit=1` returns a body with `page.total_items` reflecting the real total.

### Code touch points
- `backend/api/contracts/` (modify — unify `PageInfo`)
- `backend/api/routers/workflows.py` (modify)
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/api/routers/investigation.py` (modify — fix `total`)
- `backend/api/routers/policy.py` (modify)
- `backend/tests/api/test_pagination.py` (new)

---

## Story api.11: Uniform filtering and sorting query convention

**ID:** api.11
**Status:** planned
**Prerequisites:** [api.10]
**Unblocks:** [frontend.16]
**Estimated size:** M

**As a** API consumer,
**I need** a documented filter/sort convention (`?sort=field|-field`, `?filter[severity]=high,critical`),
**so that** I can compose list queries without reading per-router code and the SPA can build generic table controls.

### Current State
- Ad-hoc params per router: `/alerts` (`backend/api/routers/alerts.py:22-32`) takes none.
- `/workflows` accepts `knowledge_base_id`, `status`, `limit`, `offset` (`backend/api/routers/workflows.py:24-31`).
- `/knowledgebases` accepts only `limit`/`offset` (`backend/api/routers/knowledgebases.py:126-129`).
- `/investigation/search` uses `q`/`limit`/`offset` (`backend/api/routers/investigation.py:103-107`).
- `/analytics/risk-scores` requires `kb_id` and accepts `entity_type` (`backend/api/routers/analytics.py:39-48`).
- No `?sort=`, no `?filter[...]`, no shared `ListQueryParams`.

### Acceptance Criteria
- [ ] `ListQueryParams` model in `backend/api/contracts/` with `sort: list[str]`, `filter: dict[str, str]`, `limit`, `offset`/`cursor`.
- [ ] Decision (whitelist of filterable/sortable fields per endpoint) recorded per router.
- [ ] At least the four high-volume endpoints (`/alerts`, `/workflows`, `/knowledgebases`, `/investigation/search`) accept the new params.
- [ ] OpenAPI documents allowed sort/filter keys per endpoint.
- [ ] Tests assert filter+sort behaviour and reject unknown keys with `error_code=invalid_filter`.

### Verification
- `pytest backend/tests/api/test_list_query_params.py` (new) green.
- `curl :8000/alerts?filter[severity]=high&sort=-created_at` returns filtered, sorted output.

### Code touch points
- `backend/api/contracts/query_params.py` (new)
- `backend/api/routers/alerts.py` (modify)
- `backend/api/routers/workflows.py` (modify)
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/api/routers/investigation.py` (modify)
- `backend/tests/api/test_list_query_params.py` (new)

---

## Story api.12: Tighten OpenAPI schema quality

**ID:** api.12
**Status:** planned
**Prerequisites:** [api.08, api.09, api.10]
**Unblocks:** [api.13, frontend.16]
**Estimated size:** M

**As a** API consumer (frontend codegen + external integrator),
**I need** stable `operation_id`s, complete `response_model` declarations, declared error responses (401/403/404/409/413/415/422/500), and proper tags on every route,
**so that** generated clients have typed error branches and human-readable method names.

### Current State
- `backend/api/app.py:116-120` sets only `title`/`version`/`description`.
- No route declares `operation_id`; `openapi-typescript` emits names like `register_knowledge_base_documents_knowledgebases__knowledge_base_id__documents_post`.
- `/config/*` endpoints return `dict[str, object]` with no `response_model` (`backend/api/routers/config.py:24-44`).
- `add_message` declares `response_model=None` because it forks JSON vs SSE (`backend/api/routers/rag.py:65-77`).
- `/events/stream` returns `StreamingResponse` and is invisible to the schema (`backend/api/routers/events.py:55-82`).
- No router declares 401/403/404/409/413/415/422/500 response shapes.

### Acceptance Criteria
- [ ] Every operation declares `operation_id` (snake_case, scoped by router tag).
- [ ] `/config/*` endpoints declare typed `response_model` (`DomainConfigResponse`, `DomainConfigFeaturesResponse`, `DomainConfigSchemaResponse`).
- [ ] `/chat/conversations/{id}/messages` splits into two operations (JSON vs SSE) OR declares responses for both branches via `responses=...`.
- [ ] `/events/stream` declares `responses={200: {"content": {"text/event-stream": {}}}}`.
- [ ] Every router declares the error envelope under the appropriate status codes.
- [ ] CI assertion: no route is missing `operation_id`.

### Verification
- `pytest backend/tests/api/test_openapi_quality.py` (new) walks the OpenAPI spec, asserts coverage rules.
- `npm run codegen:api` produces typed error branches in `chili_app/src/lib/api/schema.ts`.

### Code touch points
- `backend/api/routers/*.py` (modify — add `operation_id`, `responses`)
- `backend/api/app.py` (modify — set FastAPI defaults if any)
- `backend/tests/api/test_openapi_quality.py` (new)

---

## Story api.13: Snapshot, publish, and lint the OpenAPI spec in CI

**ID:** api.13
**Status:** planned
**Prerequisites:** [api.12, _cicd.04]
**Unblocks:** [api.14, api.15, api.16, api.27, frontend.02]
**Estimated size:** S

**As a** API maintainer,
**I need** a version-controlled `openapi.json` snapshot, a `make openapi-export` target, and CI gates for schema validity + breaking-change detection,
**so that** the published contract is reviewable in diffs and consumers do not silently break.

### Current State
- No `openapi.json` checked in under `docs/` or `chili_app/`.
- `make openapi-export` does not exist.
- Only consumer is `npm run codegen:api` (`chili_app/package.json:13`) which requires a running `http://localhost:8000/openapi.json`.
- No drift detection, no `oasdiff`, no `openapi-spec-validator`.

### Acceptance Criteria
- [ ] `make openapi-export` writes a canonical `docs/api/openapi.json`.
- [ ] CI job runs `openapi-spec-validator docs/api/openapi.json` on every PR touching `backend/api/`.
- [ ] CI job runs `oasdiff` (or equivalent) against `main` and fails on breaking changes unless PR carries `allow-breaking-api-change` label.
- [ ] `docs/architecture.md` §8.4 updated to point at the snapshot file.

### Verification
- Open a PR that adds/renames a route — CI fails until the snapshot is regenerated.
- `make openapi-export && git diff` shows the new snapshot.

### Code touch points
- `Makefile` (modify — add `openapi-export`)
- `docs/api/openapi.json` (new)
- `.github/workflows/*` (modify — see `_cicd.04`)
- `docs/architecture.md` (modify)

---

## Story api.14: Adopt a public-API versioning strategy

**ID:** api.14
**Status:** planned
**Prerequisites:** [api.13, _cicd.05, frontend.08]
**Unblocks:** [api.27]
**Estimated size:** M

**As a** API maintainer,
**I need** a documented versioning strategy (URL prefix `/v1/...` or `Accept-Version` header) with deprecation/sunset metadata,
**so that** breaking the contract for one consumer does not break every other consumer.

### Current State
- Every router mounted at the bare resource path (`/alerts`, `/knowledgebases`, ...; see `backend/api/app.py:142-156`).
- No `/v1` prefix, no `Accept-Version`, no `Sunset` header, no deprecation banner.
- The SPA in the same repo consumes the latest schema directly.

### Acceptance Criteria
- [ ] Decision recorded in `docs/architecture.md` §8.4 (URL prefix vs header). Pick one.
- [ ] Every router moved under `/v1` (or `Accept-Version` middleware shipped).
- [ ] `Sunset` and `Deprecation` headers helper added; sample deprecated route emits them.
- [ ] Frontend `apiClient` updated to send the version (see frontend.08).
- [ ] OpenAPI document scoped to `v1`.

### Verification
- `curl :8000/v1/alerts` returns 200; `curl :8000/alerts` returns 404 (or redirect — decision recorded).
- `pytest backend/tests/api/test_versioning.py` (new) green.

### Code touch points
- `backend/api/app.py` (modify — mount prefix)
- `backend/api/routers/*.py` (modify — if prefix per-router)
- `backend/api/middleware/version.py` (new — if header approach)
- `docs/architecture.md` (modify)

---

## Story api.15: Generate typed frontend API client from OpenAPI

**ID:** api.15
**Status:** planned
**Prerequisites:** [api.13, frontend.07, _cicd.06]
**Unblocks:** []
**Estimated size:** M

**As a** frontend engineer,
**I need** `chili_app/src/lib/api/schema.ts` and a typed client generated from the published OpenAPI spec, with codegen wired into CI,
**so that** drift between hand-written types and the backend contract is detected at PR review time.

### Current State
- `chili_app/src/types/api.ts` is hand-maintained.
- `chili_app/src/lib/apiClient.ts` is hand-written.
- `chili_app/package.json:13` carries a `codegen:api` script that targets `http://localhost:8000/openapi.json` → `src/lib/api/schema.ts`, but `src/lib/api/` does not exist in the repo and `npm run codegen:api` is not run in CI.

### Acceptance Criteria
- [ ] `chili_app/src/lib/api/schema.ts` and `chili_app/src/lib/api/client.ts` generated from `docs/api/openapi.json`.
- [ ] `apiClient.ts` migrated to consume generated types (see frontend.07).
- [ ] `make codegen` target invokes the codegen with the snapshot as input.
- [ ] CI step regenerates and asserts no diff.
- [ ] Type-check (`npm run build`) gates on the generated types.

### Verification
- Add a property to a response model in backend; regenerate spec; CI fails until the frontend updates.
- `npm run build` clean.

### Code touch points
- `chili_app/package.json` (modify — point at snapshot)
- `chili_app/src/lib/api/schema.ts` (new — generated)
- `chili_app/src/lib/api/client.ts` (new — generated)
- `chili_app/src/lib/apiClient.ts` (modify — wrap generated client)
- `Makefile` (modify — `codegen` target)
- `.github/workflows/*` (modify — see `_cicd.06`)

---

## Story api.16: Backend↔frontend contract tests

**ID:** api.16
**Status:** planned
**Prerequisites:** [api.13, _cicd.07]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** schemathesis-driven property tests against the OpenAPI spec and shape-parity assertions on the SPA test suite,
**so that** the schema is exercised against real responses and consumer expectations are explicit.

### Current State
- No Pact, no schemathesis, no `openapi-spec-validator` step.
- Frontend `.spec.ts` files in `chili_app/e2e/` (`smoke.spec.ts`, `alert-feed.spec.ts`, `knowledge-base-list.spec.ts`) drive the real UI but do not assert response-shape parity with the OpenAPI document.
- Closest coverage is `backend/tests/api/test_read_model_routers.py` (happy-path TestClient shape assertions).

### Acceptance Criteria
- [ ] `schemathesis run docs/api/openapi.json --base-url http://localhost:8000` integrated as a backend test job.
- [ ] At least one consumer-driven contract per page (alerts feed, KB list, investigation entity detail).
- [ ] CI step runs schemathesis on every PR touching `backend/api/` or `docs/api/openapi.json`.
- [ ] Coverage ≥ 85% on contracts; flaky-test budget documented.

### Verification
- `make contract-test` runs locally.
- Open a PR that violates a response shape — CI fails with the schemathesis report.

### Code touch points
- `backend/tests/contracts/test_schemathesis.py` (new)
- `Makefile` (modify — `contract-test` target)
- `.github/workflows/*` (modify — see `_cicd.07`)

---

## Story api.17: Route policy registry with boot-time audit

**ID:** api.17
**Status:** planned
**Prerequisites:** [_security.06, _observability.05, agent.16]
**Unblocks:** [analytics.27, api.25, rag.09]
**Estimated size:** M

**As a** platform operator,
**I need** a declarative route-policy registry that lists `(method, path, required_role, audit_event)` for every endpoint, with optional middleware enforcement and a `GET /admin/policy/routes` introspection surface,
**so that** I can answer "which routes are admin-only", "what changed between commits", and run a single boot-time audit instead of relying on `assert_complete` walking dependants.

### Current State
- Every router today repeats `dependencies=[Depends(require_role("viewer"|"analyst"|"admin"))]` (40+ call sites across `backend/api/routers/*.py`).
- `backend/api/middleware/policy_registry.py:40-56 assert_complete` only checks each route has *some* `require_role` dependency by walking `route.dependant` for `_chiliai_required_role`.
- `SKIP_PREFIXES = ("/auth/", "/health", "/docs", "/openapi.json", "/redoc")` is hand-maintained (`backend/api/middleware/policy_registry.py:12-18`).
- No way to enumerate the full policy from a single artifact.

### Acceptance Criteria
- [ ] `backend/api/middleware/policy_registry.py` extended with a `PolicyRegistry` dataclass listing `(method, path, required_role, audit_event)` for every endpoint.
- [ ] Decision recorded: registry is authoritative + middleware enforces (decorators dropped) OR registry is verification-only (decorators stay).
- [ ] `assert_complete` rewritten to reconcile FastAPI routes against the registry — error on either missing route or missing registry entry.
- [ ] New `GET /admin/policy/routes` returns the registry (admin role).
- [ ] Policy-change audit log fires on registry edits at boot (`_observability.05`).
- [ ] Coverage ≥ 85% on the registry module.

### Verification
- `pytest backend/tests/api/test_policy_registry.py` green.
- Add a route without a registry entry; `assert_complete` raises at app startup.
- `curl :8000/admin/policy/routes` (with admin token) lists the full surface.

### Code touch points
- `backend/api/middleware/policy_registry.py` (modify)
- `backend/api/routers/admin.py` (new — `/admin/policy/routes` endpoint)
- `backend/api/app.py` (modify — register admin router)
- `backend/tests/api/test_policy_registry.py` (modify)

---

## Story api.18: Rate limiting and abuse-control middleware

**ID:** api.18
**Status:** planned
**Prerequisites:** [_security.07, _infra.08, _observability.06]
**Unblocks:** [_multitenancy.16, _security.10, api.22, rag.15]
**Estimated size:** M

**As a** platform operator,
**I need** per-IP, per-user, and per-tenant rate limits on the API gateway (especially `/auth/login`, file uploads, chat streaming, WS open),
**so that** abuse and accidental overload cannot exhaust the gateway or downstream services.

### Current State
- No rate-limit middleware under `backend/api/middleware/`.
- `backend/api/app.py:122-135` registers only CORS + metrics + tracing.
- No per-IP throttle on `/auth/login` (`backend/api/routers/auth.py:58-90`).
- No upload-bytes-per-minute cap on `/knowledgebases/{id}/documents` (`backend/api/routers/knowledgebases.py:401-422`).
- No per-user open-WebSocket cap (`backend/api/routers/ws.py:99-108`).
- No chat-message-per-minute cap on `/chat/conversations/{id}/messages?stream=true` (`backend/api/routers/rag.py:65-105`).

### Acceptance Criteria
- [ ] Token-bucket rate limiter backed by Redis (with in-memory fallback for dev) registered as middleware.
- [ ] Per-route limits declared in `backend/api/middleware/rate_limits.py`; sane defaults applied to `/auth/login`, `/auth/callback`, `/knowledgebases/{id}/documents`, `/chat/conversations/{id}/messages`, `/ws/*` open.
- [ ] `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` headers emitted on 429.
- [ ] Coverage ≥ 85%.

### Verification
- `pytest backend/tests/api/test_rate_limit.py` green.
- `for i in {1..100}; do curl -i -X POST :8000/auth/login; done` produces 429s once the bucket drains.

### Code touch points
- `backend/api/middleware/rate_limits.py` (new)
- `backend/api/app.py` (modify — register middleware)
- `backend/tests/api/test_rate_limit.py` (new)

---

## Story api.19: Split liveness, readiness, and dependency probes

**ID:** api.19
**Status:** planned
**Prerequisites:** [_infra.17, _observability.07, graph.18, vectorstore.05, embeddings.05, storage.05, database.05, events.06]
**Unblocks:** []
**Estimated size:** M

**As a** Kubernetes operator,
**I need** distinct `/livez`, `/readyz`, `/healthz` endpoints with per-dependency status (graph, vectorstore, embeddings, object store, Postgres, event bus, session store) plus a `/version` endpoint,
**so that** the orchestrator can distinguish "process is up" from "ready to serve traffic" and operators can diagnose dependency outages.

### Current State
- `backend/api/app.py:137-139` defines a single `GET /health` that always returns `{"status": "ok"}`.
- No probe of event bus, graph repository, vector store, embeddings, object store, Postgres provider, or session store (`backend/api/dependencies.py:421-440`).
- No version/build-info endpoint.
- `/health` works because the skip list at `backend/api/middleware/policy_registry.py:12-18` lists it.

### Acceptance Criteria
- [ ] `GET /livez` returns 200 unconditionally (process up).
- [ ] `GET /readyz` returns 200 only when every required dependency reports healthy; 503 otherwise with `error_code=dependency_not_ready` + `details: {dep: status}`.
- [ ] `GET /healthz` (legacy alias of `/livez`) preserved.
- [ ] `GET /version` returns `{version, commit, build_time, image}`.
- [ ] Each adapter exposes a `check_health()` method via its protocol (depends on each module's epic).
- [ ] Probes registered in policy registry skip list explicitly with rationale.
- [ ] Coverage ≥ 85% on the new module.

### Verification
- `kubectl describe pod` shows `liveness`/`readiness` probes hitting the new endpoints.
- `pytest backend/tests/api/test_health.py` green.

### Code touch points
- `backend/api/app.py` (modify — replace `/health`)
- `backend/api/routers/health.py` (new)
- `backend/api/middleware/policy_registry.py` (modify — skip list)
- `infra/k8s/*.yaml` (modify — probe wiring)
- `backend/tests/api/test_health.py` (modify)

---

## Story api.20: Per-request correlation IDs across logs, traces, and events

**ID:** api.20
**Status:** planned
**Prerequisites:** [events.05, _observability.03, agent.17]
**Unblocks:** [frontend.23, knowledgebases.06]
**Estimated size:** M

**As a** platform operator,
**I need** every request to carry an `X-Request-Id` / W3C `traceparent` propagated into structured logs, OTel spans, and outbound `EventBase.correlation_id`,
**so that** I can stitch together a single user request across API, worker, and downstream services.

### Current State
- `backend/api/app.py:106 setup_tracing()` instruments HTTP spans via `shared.tracing.instrument_fastapi_app(app)`.
- No middleware reads/generates `X-Request-Id` / `traceparent` and propagates it onto `EventBase.correlation_id` (`backend/events/types.py:14-20`).
- `/knowledgebases` publishes `KnowledgeBaseCreatedEvent` without correlation ID (`backend/api/routers/knowledgebases.py:115-117`).
- `chiliai_session` cookie carries no per-request id.

### Acceptance Criteria
- [ ] `RequestIdMiddleware` generates/echoes `X-Request-Id` and `traceparent`; attaches to `request.state.correlation_id`.
- [ ] Logger context injected per request via `shared.logging` so every log line carries `correlation_id`.
- [ ] Every router that publishes an event sets `EventBase.correlation_id = request.state.correlation_id`.
- [ ] `traceparent` honoured for OTel parenting.
- [ ] Coverage ≥ 85% on the middleware.

### Verification
- `pytest backend/tests/api/test_request_id.py` green.
- `curl -i -H "X-Request-Id: foo-123" :8000/alerts` returns the same header in the response and writes `correlation_id=foo-123` to the structured log.

### Code touch points
- `backend/api/middleware/request_id.py` (new)
- `backend/api/app.py` (modify — register middleware)
- `backend/shared/logging.py` (modify — request-id context var)
- `backend/api/routers/*.py` (modify — pass correlation_id into published events)
- `backend/tests/api/test_request_id.py` (new)

---

## Story api.21: Per-request tenant context middleware + DI keying

**ID:** api.21
**Status:** planned
**Prerequisites:** [_multitenancy.01, _multitenancy.02, _multitenancy.03]
**Unblocks:** [_multitenancy.04, _security.03, rag.17]
**Estimated size:** L

**As a** multi-tenant platform operator,
**I need** a per-request tenant context (`request.state.tenant_id`, exposed via DI), with downstream services keyed by tenant,
**so that** every query, mutation, event publish, and cache lookup is tenant-scoped.

### Current State
- No tenant axis anywhere in `backend/api/middleware/` or `backend/api/dependencies.py`.
- `User` (`backend/api/middleware/auth.py:52-58`) carries `user_id`, `roles`, `email` with no `tenant_id`.
- `get_api_state`, `get_knowledge_base_repository`, `get_alert_repository`, `get_workflow_run_store`, `get_graph_service`, `get_vector_store`, `get_session_store` are process singletons keyed only by env/config (`backend/api/dependencies.py:162-808`).

### Acceptance Criteria
- [ ] `User` model gains `tenant_id: str`; populated from the JWT claim resolved per `_security.08`.
- [ ] `TenantContextMiddleware` sets `request.state.tenant_id`; a `get_tenant_id()` DI returns it.
- [ ] DI providers for tenant-scoped resources (alert repo, KB repo, workflow store, graph service, vector service, session store) take `tenant_id` and resolve a per-tenant instance.
- [ ] Cross-tenant access is impossible at the service layer (tested explicitly).
- [ ] Decision recorded (JWT claim vs `X-Chili-Tenant` vs subdomain) per Open Question.

### Verification
- `pytest backend/tests/api/test_tenant_isolation.py` (new) green; covers per-route per-tenant isolation.
- Manual: two tokens for two tenants returning distinct data on the same route.

### Code touch points
- `backend/api/middleware/auth.py` (modify — add tenant claim)
- `backend/api/middleware/tenant_context.py` (new)
- `backend/api/dependencies.py` (modify — tenant-keyed providers)
- `backend/api/app.py` (modify — register middleware)
- `backend/tests/api/test_tenant_isolation.py` (new)

---

## Story api.22: Harden the BFF auth flow

**ID:** api.22
**Status:** planned
**Prerequisites:** [_security.09, _security.10, api.18]
**Unblocks:** []
**Estimated size:** M

**As a** security engineer,
**I need** the BFF auth flow to add CSRF defense for state-changing endpoints, an allow-list for `post_logout_redirect_uri`, coalesced session refresh, and a wall-clock JWKS TTL,
**so that** open-redirect, CSRF, refresh-storm, and rotation-hiding bugs are closed.

### Current State
- `/auth/login` PKCE state stored after URL builds (good) (`backend/api/routers/auth.py:72-89`); cookie at `backend/api/routers/auth.py:163-172` is `SameSite=lax` with no double-submit token.
- `/auth/logout` accepts `post_logout_redirect_uri` with no allow-list (`backend/api/routers/auth.py:181-204`) — open-redirect surface.
- `_maybe_refresh_session` (`backend/api/middleware/auth.py:251-298`) is per-request, not coalesced; N concurrent requests near expiry issue N refreshes.
- `JwksCache._clock=time.monotonic` (`backend/api/middleware/auth.py:89`) — JWKS TTL is process-uptime, not wall-clock.

### Acceptance Criteria
- [ ] CSRF token middleware (double-submit cookie + `X-Chili-CSRF` header) required on every non-GET non-`/auth/*` endpoint.
- [ ] `AuthConfig.allowed_post_logout_redirect_uris` list enforced on `/auth/logout`; non-matching uri → 400 `error_code=invalid_redirect`.
- [ ] Per-`session_id` async lock coalesces concurrent refresh attempts; only one upstream call to the IdP per refresh window.
- [ ] `JwksCache._clock` defaults to `time.time` (wall-clock); add a smoke test that asserts the JWKS document refreshes after a TTL crossing.
- [ ] Coverage ≥ 85% on the auth middleware + router.

### Verification
- `pytest backend/tests/api/test_auth_router.py backend/tests/api/test_auth_middleware.py` green covering all new branches.
- Manual: trigger concurrent requests near expiry, observe one refresh call.

### Code touch points
- `backend/api/middleware/csrf.py` (new)
- `backend/api/routers/auth.py` (modify)
- `backend/api/middleware/auth.py` (modify)
- `backend/config/schema.py` (modify — add allowed redirect list)
- `backend/tests/api/test_auth_router.py` (modify)
- `backend/tests/api/test_auth_middleware.py` (modify)

---

## Story api.23: Harden the production session store

**ID:** api.23
**Status:** planned
**Prerequisites:** [_security.11, _infra.10, _observability.08]
**Unblocks:** [_security.08]
**Estimated size:** M

**As a** production operator,
**I need** `RedisSessionStore` to be configurable for TLS, connect/socket timeouts, pool sizing, key-prefix discipline, and session revocation events; and `InMemorySessionStore` must not be silently selected outside `local`/`dev`,
**so that** session storage is operationally safe and revocation works.

### Current State
- `RedisSessionStore.__init__` uses `decode_responses=True` only (`backend/api/middleware/session_store.py:87-108`); no connect/socket timeout, no pool sizing, no TLS toggle, no health-check.
- `InMemorySessionStore` (`backend/api/middleware/session_store.py:54-84`) is "Thread-naive" per docstring; selected any time `AuthConfig.enabled=False` regardless of `CHILI_ENV` (`backend/api/dependencies.py:421-440`).
- No revocation event.

### Acceptance Criteria
- [ ] `RedisSessionStore` accepts `socket_timeout`, `socket_connect_timeout`, `max_connections`, `tls: bool`; documented in `backend/api/middleware/session_store.py`.
- [ ] `get_session_store()` refuses `InMemorySessionStore` outside `local`/`dev`/`test`; raises on `staging`/`production`.
- [ ] `SessionRevokedEvent` published on `delete()` and `touch()` of an evicted entry; consumed by auth middleware to expire cached sessions across processes.
- [ ] Health-check method on the store; surfaced via api.19 `/readyz`.
- [ ] Coverage ≥ 85% on the store + DI.

### Verification
- `pytest backend/tests/api/test_session_store.py` green.
- `CHILI_ENV=production REDIS_URL=... uvicorn ...` errors if Redis is unreachable rather than silently falling back.

### Code touch points
- `backend/api/middleware/session_store.py` (modify)
- `backend/api/dependencies.py` (modify — env-aware selection)
- `backend/events/types.py` (modify — add `SessionRevokedEvent`)
- `backend/tests/api/test_session_store.py` (modify)

---

## Story api.24: Open the closed `workflow_type` enum

**ID:** api.24
**Status:** planned
**Prerequisites:** [agent.13, frontend.09]
**Unblocks:** []
**Estimated size:** S

**As a** API maintainer,
**I need** `WorkflowRunResponse.workflow_type` to be an open string (validated by `agent` module enum) rather than a closed `Literal`,
**so that** adding a new workflow family does not require a coordinated contract + frontend change.

### Current State
- `backend/api/contracts.py:260-261` declares `workflow_type: Literal["ingestion", "graph_build", "analytics", "monitoring"]`.
- `backend/api/_workflow_projection.py:87-97 _workflow_type_for_trigger` maps every event prefix to one of those four; a new event family (e.g. `records.*`) is silently bucketed into `"ingestion"`.

### Acceptance Criteria
- [ ] `workflow_type` becomes `str` with a JSON-schema `enum` populated dynamically from `agent.protocols.WORKFLOW_TYPE_NAMES`.
- [ ] `_workflow_type_for_trigger` no longer maps unknown prefixes to `"ingestion"`; instead returns the explicit family.
- [ ] Frontend code that branches on `workflow_type` updated (see frontend.09).
- [ ] Tests cover an unknown-prefix event no longer mis-bucketed.

### Verification
- `pytest backend/tests/api/test_workflow_projection.py` green covering new families.
- `npm run build` clean against regenerated types.

### Code touch points
- `backend/api/contracts.py` (or contracts package) (modify)
- `backend/api/_workflow_projection.py` (modify)
- `backend/tests/api/test_workflow_projection.py` (modify)

---

## Story api.25: Admin write surface for runtime config + ops actions

**ID:** api.25
**Status:** planned
_Note (2026-08-08, supersedes the 2026-07-12 note): `feat/domain-packs-and-config-manager` **merged to prod on 2026-07-03** (`ff46080`) — nine days before that note called it unmerged. The shipped slice is described in the progress note below and was re-verified against the code on 2026-08-08. Status stays `planned`, but for the other reason the old note gave: every prerequisite is itself `planned`, and the CI-enforced DAG invariant requires them all `done` before `in-progress`. Nothing here is waiting on a branch._
**Prerequisites:** [config.07, agent.19, events.16, _security.12, api.17]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** the runtime-config slice of this surface landed (a8573e5, 5b6646c) as admin-gated routes under the existing `/config` router rather than a new `/admin/*` family: `GET /config/packs`, `POST /config/validate|apply|switch` (`require_role("admin")`), with the production auth guardrail enforced on candidate packs and a `ConfigUpdatedEvent` published on swap — this supersedes the `POST /admin/config/reload` intent. Still open: the router-family decision (the shipped routes chose folding into `/config`; revisit or ratify when the rest of the surface is built), DLQ replay, alert backfill, JWKS cache invalidation, session revoke, and `_security.12` audit events for admin actions.
**Unblocks:** []
**Estimated size:** L

**As a** platform admin,
**I need** an admin-only `/admin/*` surface for runtime config updates, DLQ replay, alert backfill, JWKS cache invalidation, session revoke, and config hot reload,
**so that** ops actions are first-class API operations with audit and RBAC rather than container-shell rituals.

### Current State
_Re-verified 2026-08-08 against the running API._
- Runtime config **shipped**, admin-gated, folded into `/config` rather than a new family: `GET /config/packs`, `POST /config/validate|apply|switch` (all `require_role("admin")`).
- DLQ replay **shipped** under `/events`, not `/admin`: `GET /events/dlq`, `GET /events/dlq/{dlq_id}`, `POST /events/dlq/{dlq_id}/replay|discard`, admin-gated.
- Still absent: alert backfill, JWKS cache invalidation, session revoke. There is no `backend/api/routers/admin.py`; the only `/admin/*` path mounted is `POST /admin/dev-seed`.
- **None of the shipped admin actions emit an audit event** — `grep -c audit` is 0 in both `api/routers/config.py` and `api/routers/events.py`, while an `auditlog/` module exists and is used elsewhere. A hot-swap of the active domain pack is currently unattributable.

### Acceptance Criteria
- [x] Decision recorded (separate router family vs folded into existing) — **decided the other way**: the shipped routes fold into the owning routers (`/config/*` for pack actions, `/events/dlq/*` for replay), because each already owns its domain's models and DI. The AC previously prescribed "choose separate router family"; that is superseded by what shipped, not left as an open choice.
- [x] Runtime-config actions gated by `require_role("admin")` — `POST /config/validate|apply|switch`, with non-admin `403` covered in `backend/tests/api/test_config_routes.py`.
- [x] DLQ replay/discard gated by `require_role("admin")`.
- [ ] Remaining ops actions: `POST /alerts/backfill`, JWKS cache invalidation, session revoke.
- [ ] Every admin action emits an audit event per `_security.12` — **none do today**; this is the largest open piece and the reason the story stays `planned`.
- [ ] Coverage ≥ 85% on whichever routers gain the remaining actions.

### Verification
- `pytest backend/tests/api/test_admin_router.py` green.
- `curl -X POST :8000/admin/config/reload` (admin token) returns 200; non-admin returns 403.

### Code touch points
- `backend/api/routers/admin.py` (new)
- `backend/api/app.py` (modify — register router)
- `backend/api/middleware/policy_registry.py` (modify — register admin entries)
- `backend/tests/api/test_admin_router.py` (new)

---

## Story api.26: Fix DI mis-wirings in `dependencies.py`

**ID:** api.26
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S

**As a** API maintainer,
**I need** the three DI mis-wirings in `backend/api/dependencies.py` fixed,
**so that** tests can override every dependency cleanly, storage backends do not silently switch, and the session-store cache respects env mutations.

### Current State
- `get_chat_message_payload` calls `get_knowledge_base_repository()` directly (no `Depends`), bypassing FastAPI override (`backend/api/dependencies.py:248-256`).
- `get_object_store()` returns `InMemoryObjectStore` only when `storage` section equals defaults (`backend/api/dependencies.py:447-453`); silently switches if any non-default value is set.
- `get_session_store` is `@lru_cache(maxsize=1)` (`backend/api/dependencies.py:421-422`) but reads `os.environ["REDIS_URL"]` at first call — env mutations after the first call are ignored; `create_app()` never clears this cache (only `get_domain_config` at `backend/api/app.py:110-111`).

### Acceptance Criteria
- [ ] `get_chat_message_payload` takes `kb_repository = Depends(get_knowledge_base_repository)`; signature updated.
- [ ] `get_object_store()` selects backend based explicitly on `storage_config.backend`, not on whether the section equals defaults.
- [ ] `get_session_store.cache_clear()` invoked in `create_app()` alongside `get_domain_config.cache_clear()` so test env mutations land.
- [ ] Regression tests for each of the three bugs.

### Verification
- `pytest backend/tests/api/test_dependencies.py` green.
- `pyright --strict` clean.

### Code touch points
- `backend/api/dependencies.py` (modify)
- `backend/api/app.py` (modify — additional `cache_clear()`)
- `backend/api/routers/rag.py` (modify — accept the new `Depends`)
- `backend/tests/api/test_dependencies.py` (new or modify)

---

## Story api.27: Document the route surface (machine + curated)

**ID:** api.27
**Status:** planned
**Prerequisites:** [api.13, api.14, _cicd.08, frontend.10]
**Unblocks:** []
**Estimated size:** S

**As a** developer or integrator,
**I need** `docs/api/openapi.json` (machine-readable) plus a curated `docs/api/README.md` enumerating every public route with its required role, contract, error envelope, pagination, idempotency notes, and a `docs/api/deprecated.md` page once versioning lands,
**so that** I do not have to read every router file to understand the public surface.

### Current State
- No `docs/api/` directory.
- Only documentation is auto-generated `/docs` (Swagger UI from FastAPI).
- `docs/architecture.md` §8.4 references the OpenAPI spec but does not enumerate routes.
- README.md files under `backend/` do not list endpoints.

### Acceptance Criteria
- [ ] `docs/api/README.md` lists every public route with role, request/response contract, error envelope, pagination, idempotency notes.
- [ ] `docs/api/openapi.json` checked in (depends on api.13).
- [ ] `docs/api/deprecated.md` page exists (empty initially, populated as routes deprecate per api.14).
- [ ] CI step fails when a new route lands without a matching `docs/api/README.md` entry.
- [ ] `backend/api/README.md` links to `docs/api/README.md`.

### Verification
- Open a PR that adds a route — CI fails until docs are updated.
- `docs/api/README.md` rendered in GitHub shows the full surface.

### Code touch points
- `docs/api/README.md` (new)
- `docs/api/deprecated.md` (new)
- `docs/architecture.md` (modify — point at `docs/api/`)
- `backend/api/README.md` (modify)
- `.github/workflows/*` (modify — see `_cicd.08`)

## Story api.28: Replace seeded API analytics reads

**ID:** api.28
**Status:** planned
**Prerequisites:** [api.01]
**Unblocks:** [api.29, frontend.04]
**Estimated size:** L

### Narrative
As an API consumer,
I want analytics endpoints to read through the analytics service boundary,
so that seeded analytics fixtures can be retired without coupling API persistence cleanup to later GNN adapter work.

### Acceptance Criteria
- [x] Collection analytics routes call the existing analytics service/repository boundary instead of route-local seeded stubs.
- [x] `GET /analytics/overview` is computed from durable alert, case, and KB stores.
- [ ] Entity-scoped `GET /analytics/risk-scores/{entity_id}` and `GET /analytics/timeseries/{entity_id}` no longer depend on the remaining `ApiState` analytics composition.
- [ ] Responses preserve provenance and model metadata where available from the service boundary.
- [ ] Empty-state responses are explicit when no analytics results exist.

### Verification
- [ ] API tests cover analytics responses from service fixtures.
- [ ] Tests prove seeded `ApiState` analytics fixtures are not required.

### Code touch points
- `backend/app/api/**`
- `backend/app/analytics/**`
- `backend/tests/api/**`

---

## Story api.29: Remove seeded ApiState dependency from production API paths

**ID:** api.29
**Status:** planned
**Prerequisites:** [api.28]
**Unblocks:** [analytics.28, api.02, api.03, api.04, graph.12, rag.01, vectorstore.09]
**Estimated size:** M

### Narrative
As a maintainer,
I want production API routes to stop depending on seeded `ApiState`,
so that demo fixtures cannot mask missing persistence wiring.

### Acceptance Criteria
- [x] Removed `_seed_*` production read models for alerts, cases, conversations, workflows, evidence packs, policy gaps, and the demo graph.
- [x] Graph, evidence, alerts, cases, conversations, workflows, and policy items no longer depend on seeded `ApiState` data.
- [x] Dev/e2e deterministic data lives behind non-production `POST /admin/dev-seed`, which writes the real repositories.
- [ ] Entity-scoped analytics routes finish moving off the remaining `ApiState` analytics composition.
- [ ] Documentation identifies any remaining demo-only fixture path.

### Verification
- [ ] API test suite passes with production seed data disabled.
- [ ] Search confirms `ApiState` is absent from production data routes except documented demo paths.

### Code touch points
- `backend/app/api/**`
- `backend/app/demo/**`
- `backend/tests/**`

---
