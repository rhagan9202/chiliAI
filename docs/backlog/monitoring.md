# monitoring backlog

> **Scope:** Claim-stream consumer, alert generation/dedup, prioritization, disposition workflow, routing, evidence-pack assembly, notification delivery, SLO/SLI, tenant scoping.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story monitoring.01: Bridge AlertsCreatedEvent to the WebSocket hub for real-time push

**ID:** monitoring.01
**Status:** planned
**Prerequisites:** [events.02, events.05, api.06]
**Unblocks:** [_plugins.01, api.01]
**Estimated size:** M

**As a** fraud analyst,
**I need** alerts created by the monitoring service to push to my browser the moment they exist,
**so that** I can react to high-severity events without polling `GET /alerts` and without missing volatile, short-lived risk windows.

### Current State
- `MonitoringService.evaluate` publishes `AlertsCreatedEvent` to the configured `EventBus` for every non-empty alert batch (`backend/monitoring/service.py:207-226`).
- `WebSocketHub.broadcast` exists and can fan out JSON payloads filtered by `severity_filter` (`backend/api/routers/ws.py:118-134`); `/ws/alerts` accepts viewer-role subscribers (`backend/api/routers/ws.py:207-213`).
- No production code subscribes the hub to `alerts.created`; the router docstring states "the event bus bridge is added in Epic 8" (`backend/api/routers/ws.py:5-9, 84-90`).
- Frontend WS subscribers therefore receive nothing on alert creation; Flow B's terminal `WS: alerts → Analyst` arrow in architecture §6.2 is unimplemented.

### Acceptance Criteria
- [ ] New `AlertEventBusBridge` (or equivalent name) in `backend/api/_alert_bridge.py` subscribes to `alerts.created` on app startup and shuts down cleanly on app shutdown.
- [ ] Bridge converts each `AlertCreatedReference` in `AlertsCreatedEvent.alerts` into a JSON payload of the WS `AlertCreated` contract shape (alert id, entity id, entity type, severity, title, reasoning, evidence_pack_id, knowledge_base_id, created_at) and calls `WebSocketHub.broadcast("alerts", payload, filter_fn=…)`.
- [ ] `filter_fn` uses each connection's `severity_filter` so subscribers that opted into `{high, critical}` do not receive `medium`/`low` alerts.
- [ ] Bridge survives Redis Streams reconnects (relies on the events module's reconnect/backoff helper from `events.05`).
- [ ] Bridge drops oversized backlog with a `chili_monitoring_ws_bridge_dropped_total` counter (no unbounded growth in the consumer-side queue) and logs at WARNING.
- [ ] Integration test pushes a synthetic `AlertsCreatedEvent` through the in-memory event bus and asserts a connected fake WS receives the projected payload within 100 ms.
- [ ] Wired into `backend/api/app.py` via the lifespan hook; documented in `backend/README.md` Active Monitoring section.

### Verification
- `pytest backend/tests/api/test_alert_bridge.py -v` — green; covers happy path, severity filtering, reconnect, drop-on-overflow.
- `pytest --cov=backend/api/_alert_bridge --cov-report=term-missing` — ≥ 85% on the new module.
- Local smoke: `make dev`, open `wscat -c ws://localhost:8000/ws/alerts` with viewer cookie, `POST /monitoring/evaluate` against a seeded KB, observe the bridge log line and a JSON frame in `wscat`.

### Code touch points
- `backend/api/_alert_bridge.py` (new)
- `backend/api/app.py` (modify — register bridge in lifespan)
- `backend/api/routers/ws.py` (modify — remove stale "wired in Epic 8" docstring)
- `backend/api/state.py` (modify — expose bridge dependency)
- `backend/tests/api/test_alert_bridge.py` (new)
- `backend/README.md` (modify — document the bridge)

---

## Story monitoring.02: Wire AlertProjectionRepository upserts on AlertsCreatedEvent

**ID:** monitoring.02
**Status:** done
**Prerequisites:** [events.02, api.06, graph.07]
**Unblocks:** [analytics.06, analytics.36, monitoring.09]
**Estimated size:** M
**Done:** 2026-07-23 · alerts.36 (durable alert read model) · `feat/alerts-durable-read-model`

**As a** fraud analyst,
**I need** newly created alerts to appear in `GET /alerts` immediately after the monitoring service emits them,
**so that** the alert feed in the workbench reflects real production state instead of remaining empty until something seeds the projection.

### Current State (shipped)
- **Deviation (chosen fix differs from the original AC shape):** rather than adding a second worker handler that upserts a parallel `AlertProjectionRepository`, alerts.36 retired that projection entirely. The sole `alerts.created` consumer (`handle_alerts_created_for_graph`, `backend/agent/coordinator.py`) already idempotently writes `alert_history` for every real alert; alerts.36 extended that table with the three read-model columns the projection used to carry (`entity_label`, `confidence`, `tags` — migration `0012`), promoted the monitoring-owned store to a full read/mutate protocol (`monitoring.adapters.protocols.AlertFeedStoreProtocol`: list/get/acknowledge/count/`delete_by_kb`, in-memory + Postgres adapters), and DI-switched the API onto it (`api.dependencies.get_alert_feed_store` — Postgres when a connection provider resolves, in-memory otherwise; same pattern as `get_risk_signal_source`/`get_case_repository`).
- `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, SSE `active_alerts`, `GET /analytics/overview`, and `GET /graph/entities/{id}`'s related-alerts now all read the same durable `alert_history` rows — no separate read model to fall out of sync, and nothing left to seed for a fresh deployment: the first real `AlertsCreatedEvent` is visible in `GET /alerts` with no test-fixture dependency. `api/_alert_store.py` (the object-store projection + `AlertProjectionRepository`) was deleted.
- `entity_label`/`confidence`/`tags` are populated by the two producers directly on `AlertCreatedReference` before Flow 4 maps them onto the row: the analytics pipeline's `_run_explainability_stage` sets `confidence` from the risk assessment's `overall_score` and `tags` from the top-3 risk-factor names (kebab-cased); `MonitoringService.evaluate()` sets `confidence` from the alert candidate's threshold-ratio score and `tags` from a kebab-slugged `metric_name`. Both currently fall back `entity_label` to `entity_id` (no cheap display value in scope without an extra graph read — tracked as a follow-up, see `docs/backlog/analytics.md` "true entity_label on Flow B alerts").
- KB deletion purges alerts as one step of the shared cascade (`alert_history` via `AlertHistoryWriter.delete_by_kb`, `knowledgebases.cleanup.kb_deletion_steps`) — both the API and worker retry bundles build their own writer, so there is no separate "API-owned projection" step left to skip.

### Acceptance Criteria
- [x] Alerts appear in `GET /alerts` without any handler-side upsert step: the durable writer Flow 4 already calls (`handle_alerts_created_for_graph` → `alert_history_writer.write_alerts`) is the same store the API reads, so there is nothing further to wire.
- [x] `entity_label` (fallback to `entity_id`), `confidence`, and `tags` are populated on the row by the two producers (see above) instead of defaulting to `""`/`0.0`/`[]` on every alert.
- [x] Idempotent on `alert_id`: `write_alerts` is first-row-wins per `(kb, alert_id)` (proved by `tests/monitoring/test_alert_history_writer.py`'s idempotency test), so re-delivery of the same `AlertsCreatedEvent` cannot regress a row's read-model fields.
- [x] Alert writes stay wrapped in the existing DLQ + retry envelope on `handle_alerts_created_for_graph` — no new handler, no new envelope to add.
- [x] `GET /alerts` returns the row after `MonitoringService.evaluate` (or the analytics pipeline) fires, end-to-end — proved by the API alert-router integration tests below, not a separate projection-specific test.

### Verification
- `backend/.venv/bin/pytest tests/monitoring/test_alert_history_writer.py tests/monitoring/test_postgres_alert_history.py tests/monitoring/test_alerts_service.py tests/agent/test_alerts_created_graph_flow.py -q` — green (writer idempotency, Postgres adapter, list/ack/count service behavior, Flow 4 read-model population).
- `backend/.venv/bin/pytest tests/api/test_read_model_routers.py tests/api/test_phase5_stateful_routes.py tests/api/test_events_router.py tests/api/test_dependencies.py -q` — green (`/alerts`, SSE `active_alerts`, and `get_alert_feed_store` DI-switch behavior over the durable store).
- Full `make test` from repo root green at Task 5 closeout (see this file's provenance commits for the exact run).
- `pyright` (bare) and `ruff check --no-cache .` clean.

### Code touch points
- `backend/database/migrations/versions/0012_alert_history_read_model.py` (new)
- `backend/monitoring/adapters/protocols.py`, `backend/monitoring/adapters/in_memory.py`, `backend/monitoring/adapters/postgres.py` (modify — `AlertFeedStoreProtocol` + list/ack/count/`delete_by_kb`)
- `backend/agent/coordinator.py` (modify — Flow 4 populates `entity_label`/`confidence`/`tags` on `AlertCreatedReference`)
- `backend/api/dependencies.py` (modify — `get_alert_feed_store`, replacing `get_alert_repository`)
- `backend/api/routers/alerts.py`, `backend/api/routers/events.py`, `backend/api/_analytics_overview.py`, `backend/api/_graph_entity_payload.py` (modify — read `AlertFeedStoreProtocol` instead of `AlertProjectionRepository`)
- `backend/api/_alert_store.py` (deleted)
- `backend/knowledgebases/cleanup.py` (modify — `alert_history` step replaces the API-owned `alert_projection` step)

---

## Story monitoring.03: Add asset-criticality and confidence weighting to alert prioritization

**ID:** monitoring.03
**Status:** planned
**Prerequisites:** [shared.04, config.05, graph.04]
**Unblocks:** [monitoring.12]
**Estimated size:** L

**As a** fraud analyst,
**I need** alert priority to combine severity, model confidence, and asset criticality,
**so that** the top of my queue is the alert most worth my next hour — not just whichever alert happened to cross the high-threshold first.

### Current State
- Severity is computed as a flat `"high"`/`"medium"` from observation score against medium/high thresholds (`backend/monitoring/service.py:385-401`).
- `shared.types.Alert.severity` is a bare `str` with a TODO to become a `SeverityLevel` enum (`backend/shared/types.py:117-119`).
- `AlertProjectionRecord.confidence` exists (`backend/api/_alert_store.py:49`) but `MonitoringService` never emits a confidence value, so the projection always stores `0.0`.
- No asset-criticality concept exists on entities or in alert payloads; the alert table cannot sort by anything beyond severity.

### Acceptance Criteria
- [ ] `SeverityLevel` enum introduced in `backend/shared/types.py` (`critical`, `high`, `medium`, `low`, `info`) and `Alert.severity` retyped to it (back-compat shim accepts legacy strings).
- [ ] `AlertCandidate` and `Alert` gain `confidence: float` (0.0–1.0) and `priority: float` (composite of severity tier × confidence × asset criticality).
- [ ] `MonitoringService.evaluate` writes `confidence` derived from the observation rationale/score and `priority` derived from the composite formula; asset criticality sourced from `entity.properties["criticality"]` with KB-scoped fallback weights from `DomainConfig.alerts`.
- [ ] Rate-limit sort in `MonitoringService.evaluate` and the API list sort in `AlertsService.list_alerts` both use `priority` (severity-only sort remains available as an option in `AlertListRequest`).
- [ ] `_to_alert_candidate` updated with unit tests covering boundary scores, missing criticality, and the priority composite formula.
- [ ] Documentation in `backend/monitoring/AGENT.md` describes the formula and tunables.

### Verification
- `pytest backend/tests/monitoring/test_prioritization.py -v` — green; covers enum migration, composite math, sort order, fallbacks.
- `pyright --strict backend/monitoring backend/shared` — clean after the enum migration.
- `pytest --cov=backend/monitoring --cov-report=term-missing` — ≥ 85% on the package.

### Code touch points
- `backend/shared/types.py` (modify — SeverityLevel enum + Alert fields)
- `backend/monitoring/models.py` (modify — AlertCandidate fields)
- `backend/monitoring/service.py` (modify — `_to_alert_candidate`, sort)
- `backend/monitoring/service_models.py` (modify — list request sort option)
- `backend/api/_alert_store.py` (modify — surface priority/confidence in projection list)
- `backend/tests/monitoring/test_prioritization.py` (new)
- `backend/monitoring/AGENT.md` (new or modify)

---

## Story monitoring.04: Add alert disposition workflow — escalate, dismiss, false-positive labels

**ID:** monitoring.04
**Status:** planned
**Prerequisites:** [api.06, _security.06, database.07]
**Unblocks:** [monitoring.09, monitoring.14]
**Estimated size:** L

**As a** fraud analyst,
**I need** to mark alerts as `resolve`, `dismiss`, `escalate`, or `reopen` with a disposition label (`true_positive`, `false_positive`, `benign`, `unknown`),
**so that** downstream metrics (FP rate, MTTR), risk-score replay, and the self-reinforcing loop have ground truth to train against.

### Current State
- Lifecycle state machine supports `open → acknowledged → investigating → resolved/dismissed` plus a "reopen" edge (`backend/monitoring/service.py:49-55`).
- `AlertsService` exposes only `acknowledge_alert` / `resolve_alert` (`backend/monitoring/service.py:327-366`).
- API exposes only `POST /alerts/{id}/acknowledge` (`backend/api/routers/alerts.py:53-73`) — no resolve, dismiss, escalate, or reopen endpoints.
- The projection's `acknowledge` does not route through the lifecycle state machine, allowing inconsistent transitions.
- No `disposition`, no `escalation_target`, and no audit trail beyond the per-row `updated_at`.

### Acceptance Criteria
- [ ] New endpoints `POST /alerts/{id}/{resolve,dismiss,escalate,reopen}` route through `AlertsService` and the projection in lockstep.
- [ ] `Alert` gains `disposition: Literal["true_positive", "false_positive", "benign", "unknown"]` (default `"unknown"`) and `escalation_target: str | None`.
- [ ] `AlertsService` methods `dismiss_alert`, `escalate_alert`, `reopen_alert` implemented and enforce `ALERT_TRANSITIONS`; transitions emit a new `AlertLifecycleEvent` published to the event bus.
- [ ] New `alert_activity_log` table (and `AlertActivityWriter`) records every transition with `(alert_id, actor, from_status, to_status, disposition, reason, occurred_at)` for audit.
- [ ] `acknowledge_alert_projection` routes through the state machine instead of direct field updates.
- [ ] OpenAPI schema regenerated; frontend contract types in `chili_app/src/api/contracts.ts` updated.
- [ ] Integration tests cover every transition path including illegal transitions returning HTTP 409.

### Verification
- `pytest backend/tests/monitoring/test_lifecycle.py backend/tests/api/routers/test_alerts_lifecycle.py -v` — green.
- `pytest --cov=backend/monitoring --cov=backend/api/routers/alerts --cov-report=term-missing` — ≥ 85%.
- Local smoke: `curl -X POST http://localhost:8000/alerts/<id>/escalate -d '{"target":"oncall-l2","disposition":"true_positive","reason":"…"}'` returns 200 and audit row visible in `psql -c "select * from alert_activity_log"`.

### Code touch points
- `backend/monitoring/service.py` (modify — new lifecycle methods, event publication)
- `backend/shared/types.py` (modify — Alert.disposition, escalation_target)
- `backend/monitoring/models.py` (modify — activity record)
- `backend/monitoring/adapters/postgres.py` (modify — AlertActivityWriter)
- `backend/api/routers/alerts.py` (modify — new endpoints)
- `backend/api/_alert_store.py` (modify — route through state machine)
- `backend/events/types.py` (modify — `AlertLifecycleEvent`)
- `backend/database/migrations/*.py` (new — `alert_activity_log`)
- `chili_app/src/api/contracts.ts` (modify)
- `backend/tests/monitoring/test_lifecycle.py` (new)
- `backend/tests/api/routers/test_alerts_lifecycle.py` (new)

---

## Story monitoring.05: Add alert routing — queue alerts to specific roles or analysts

**ID:** monitoring.05
**Status:** planned
**Prerequisites:** [config.07, _security.05, api.06]
**Unblocks:** [monitoring.12, monitoring.13]
**Estimated size:** L

**As a** fraud-operations manager,
**I need** alerts routed to a specific role/team/analyst based on entity type, severity, metric, or knowledge base,
**so that** on-call rotations and specialty queues work and analysts only see the alerts they own.

### Current State
- Every alert lands in one global feed and the same WS broadcast goes to every connected `viewer` (subject only to optional severity filter, `backend/api/routers/ws.py:39-43, 72-75`).
- No `assigned_to` / `assigned_team` / `on_call_rotation` concept anywhere.
- RBAC permissions `alerts:read` and `cases:assign` are declared in `backend/config/defaults/medicare_fraud.yaml:224, 228` but unused by routing logic.

### Acceptance Criteria
- [ ] `Alert.assigned_to: str | None` and `Alert.assigned_team: str | None` fields added.
- [ ] `RoutingRule` Pydantic model (entity_type / severity / metric_name / knowledge_base_id → target role/team/user) loaded from `MonitoringConfig.routing_rules` per `config.07`.
- [ ] `MonitoringService.evaluate` evaluates rules per alert with documented precedence (first-match-wins; documented in AGENT.md).
- [ ] `WebSocketHub.broadcast` and `GET /alerts` filter alerts by the caller's role/team/identity; default-deny when no rule matches and caller lacks `alerts:read_all`.
- [ ] `POST /alerts/{id}/assign` lifecycle action (reassigns to a user or team) — reuses the `monitoring.04` activity log.
- [ ] Hot-reload on routing config change (no worker restart needed).

### Verification
- `pytest backend/tests/monitoring/test_routing.py backend/tests/api/test_ws_routing.py -v` — green.
- Local smoke: configure a rule routing `severity=high` to `team=tier2`, connect two WS clients (one in tier2, one viewer-only), trigger evaluation, only tier2 receives the broadcast.

### Code touch points
- `backend/shared/types.py` (modify — Alert assignment fields)
- `backend/monitoring/models.py` (modify — RoutingRule)
- `backend/monitoring/service.py` (modify — evaluate routing)
- `backend/api/routers/alerts.py` (modify — `/assign`, filtered list)
- `backend/api/routers/ws.py` (modify — connection scoping)
- `backend/api/_alert_bridge.py` (modify — filter callback uses identity)
- `backend/config/schema.py` (modify — routing_rules on MonitoringConfig)
- `backend/tests/monitoring/test_routing.py` (new)
- `backend/tests/api/test_ws_routing.py` (new)

---

## Story monitoring.06: Assemble evidence packs for generated alerts

**ID:** monitoring.06
**Status:** planned
**Prerequisites:** [analytics.12, graph.05, storage.06]
**Unblocks:** [monitoring.13]
**Estimated size:** L

**As a** fraud analyst,
**I need** every generated alert to carry a populated evidence pack (subgraph + risk-factor narrative + policy citations),
**so that** the alert detail panel can render an investigable case the moment I open it instead of showing a stub.

### Current State
- `AlertCandidate.evidence_pack_id` and `Alert.evidence_pack_id` are wired through the model (`backend/monitoring/models.py:43`, `backend/shared/types.py:122`).
- `_to_alert_candidate` copies `evidence_pack_id` straight from the upstream observation without ever calling an evidence-pack builder (`backend/monitoring/service.py:385-401`).
- `EvidencePack` type exists in `backend/shared/types.py:134`; `backend/analytics/explainability/service.py:57` builds packs but the monitoring pipeline never invokes explainability.
- Most observations have `evidence_pack_id=None`, so alert detail in the UI is missing supporting evidence.

### Acceptance Criteria
- [ ] New `EvidencePackBuilder` protocol in `backend/monitoring/protocols.py` (or `backend/analytics/explainability/protocols.py` if explainability owns the contract).
- [ ] Default implementation invokes `analytics.explainability.service` for the subgraph + risk-factor narrative and persists the pack via a new `EvidencePackStore` (object-store backed by `storage.06`).
- [ ] `MonitoringService.evaluate` calls the builder per alert (after dedup/rate-limit) and stamps the returned `evidence_pack_id` on the published `AlertsCreatedEvent`.
- [ ] Pack assembly latency budget: p95 ≤ 250 ms per pack; budget enforced by a metric and a soft-fail (alert publishes with `evidence_pack_id=None` and a `chili_monitoring_pack_build_failures_total` counter) so alert publication is never gated indefinitely.
- [ ] Tests cover successful pack build, builder timeout/failure, and idempotent re-build on retry.

### Verification
- `pytest backend/tests/monitoring/test_evidence_pack.py -v` — green.
- `pytest --cov=backend/monitoring --cov-report=term-missing` — ≥ 85%.
- Local smoke: trigger evaluation; open `GET /alerts/{id}`; response includes `policy_citations` and `related_entity_ids` derived from the pack.

### Code touch points
- `backend/monitoring/protocols.py` (modify — EvidencePackBuilder protocol)
- `backend/monitoring/adapters/evidence.py` (new — default implementation)
- `backend/monitoring/service.py` (modify — call builder in evaluate)
- `backend/analytics/explainability/service.py` (modify — expose monitor-facing API if needed)
- `backend/tests/monitoring/test_evidence_pack.py` (new)
- `backend/monitoring/AGENT.md` (modify — budget + soft-fail semantics)

---

## Story monitoring.07: Build notification dispatcher and in-app channel

**ID:** monitoring.07
**Status:** planned
**Prerequisites:** [config.15, events.16]
**Unblocks:** [monitoring.15]
**Estimated size:** L

### Narrative
As an operator,
I want alerts to flow through a notification dispatcher with an in-app channel,
so that alert delivery has one host-owned path before external integrations are added.

### Current State
Alert data exists, but notification routing and delivery channels are not centralized.

### Acceptance Criteria
- [ ] Notification protocol defines message, severity, recipient, channel, and delivery result models.
- [ ] Dispatcher routes alert notifications to configured channels.
- [ ] In-app channel persists notifications and exposes read/acknowledge APIs.
- [ ] Delivery attempts are correlated with alert IDs and event IDs.

### Verification
- [ ] Unit tests cover dispatcher routing and in-app delivery.
- [ ] API tests cover notification list and acknowledge flows.

### Code touch points
- `backend/app/monitoring/**`
- `backend/app/api/**`
- `backend/tests/**`

---
## Story monitoring.08: Add stream-level backpressure when alert rate spikes

**ID:** monitoring.08
**Status:** planned
**Prerequisites:** [events.07, _observability.08]
**Unblocks:** []
**Estimated size:** L

**As a** platform operator,
**I need** the monitoring pipeline to shed or defer load when alert rates exceed sustainable ceilings,
**so that** a burst of `RiskScoredEvent`s does not crash the WS hub, exhaust notification quotas, or back up the Redis Streams consumer group.

### Current State
- Per-evaluation rate limit exists (`max_alerts_per_evaluation`, default 100, severity-sorted truncation at `backend/monitoring/service.py:188-198`).
- No cross-evaluation backpressure: bursts of `RiskScoredEvent`s trigger one `MonitoringService.evaluate` per assessment in `handle_risk_scored` (`backend/agent/coordinator.py:1429-1475`); failures absorbed and logged but successes continue at full speed.
- No token-bucket per KB, no consumer-group lag observation, no shed-on-overload behavior, no signal back to upstream producers.

### Acceptance Criteria
- [ ] Per-KB token-bucket (or leaky-bucket) limiter applied in `handle_risk_scored` before invoking the monitoring service; defaults sourced from `MonitoringConfig.backpressure`.
- [ ] Soft and hard ceilings: at soft ceiling, log + counter; at hard ceiling, alerts persist to `alert_history` with `status="deferred"` and a `deferred_reason` rather than publishing to WS/notification paths.
- [ ] Redis Streams consumer-group lag exposed as a `chili_events_consumer_lag` gauge (uses the events module's lag helper from `events.07`).
- [ ] Load-shed metrics: `chili_monitoring_deferred_total{kb_id, reason}`, `chili_monitoring_rate_limited_total{kb_id}`.
- [ ] Deferred alerts replayable via `monitoring.11` (replay sees `status="deferred"` rows).
- [ ] Documented runbook in `docs/monitoring_slos.md` (introduced by `monitoring.10`) explains when to widen vs tighten the buckets.

### Verification
- `pytest backend/tests/monitoring/test_backpressure.py -v` — green; covers soft, hard, recovery.
- `pytest --cov=backend/monitoring --cov-report=term-missing` — ≥ 85%.
- Load test (manual): drive 10× nominal alert rate at one KB, assert defer counter rises and WS broadcast count plateaus.

### Code touch points
- `backend/monitoring/backpressure.py` (new)
- `backend/agent/coordinator.py` (modify — apply limiter in `handle_risk_scored`)
- `backend/monitoring/service.py` (modify — accept defer path)
- `backend/monitoring/adapters/postgres.py` (modify — write `status="deferred"`)
- `backend/config/schema.py` (modify — backpressure tunables)
- `backend/tests/monitoring/test_backpressure.py` (new)

---

## Story monitoring.09: Add alert metrics — count, MTTA, MTTR, false-positive rate

**ID:** monitoring.09
**Status:** planned
**Prerequisites:** [monitoring.02, monitoring.04, _observability.03]
**Unblocks:** [monitoring.10]
**Estimated size:** M

**As a** platform operator,
**I need** the monitoring module to export comprehensive Prometheus metrics for created/suppressed/rate-limited counts, MTTA/MTTR histograms, and a false-positive ratio,
**so that** dashboards and SLO burn-rate alerts (`monitoring.10`) have signals to compute against.

### Current State
- Only `active_alerts_total` gauge exists (`backend/monitoring/metrics.py:37-40`) — and it is **never written**: `grep` shows zero `active_alerts_total.set/inc/dec` callers in monitoring code.
- No counters for `alerts_created`, `alerts_suppressed_by_dedup`, `alerts_suppressed_by_rule`, `alerts_rate_limited`, `alerts_escalated`.
- No histograms for MTTA (time-to-acknowledge), MTTR (time-to-resolve), or `evaluation_duration_seconds`.
- No FP ratio (requires disposition labels from `monitoring.04`).
- `MonitoringEvaluationResponse` carries the counts but they are not exported to Prometheus.

### Acceptance Criteria
- [ ] New module-prefixed metrics in `backend/monitoring/metrics.py`:
  - `chili_monitoring_alerts_created_total{severity, kb_id}`
  - `chili_monitoring_alerts_suppressed_total{reason}` (reason ∈ {dedup, rule, rate_limit})
  - `chili_monitoring_eval_duration_seconds{kb_id}` (Histogram)
  - `chili_monitoring_mtta_seconds`, `chili_monitoring_mttr_seconds` (Histograms)
  - `chili_monitoring_false_positive_ratio` (Gauge, computed from `alert_activity_log`)
- [ ] `active_alerts_total` actually updated on every projection upsert and every lifecycle transition.
- [ ] Metrics emitted from `MonitoringService.evaluate` (counts + duration) and `AlertsService` lifecycle methods (MTTA/MTTR observations).
- [ ] FP ratio computed by a periodic worker job (every 5 min) over the last 30 days; cardinality bounded per `_observability.03` guidance.
- [ ] `/metrics` exporter regression test verifies the new metric names exist.

### Verification
- `pytest backend/tests/monitoring/test_metrics.py -v` — green.
- `curl http://localhost:8000/metrics | grep chili_monitoring_` returns the new families.
- `pytest --cov=backend/monitoring/metrics --cov-report=term-missing` — ≥ 85%.

### Code touch points
- `backend/monitoring/metrics.py` (modify)
- `backend/monitoring/service.py` (modify — emit counts + duration)
- `backend/api/_alert_store.py` (modify — emit active gauge on upsert/acknowledge)
- `backend/monitoring/jobs.py` (new — FP ratio scheduler)
- `backend/tests/monitoring/test_metrics.py` (new)

---

## Story monitoring.10: Define and instrument alert SLOs/SLIs

**ID:** monitoring.10
**Status:** planned
**Prerequisites:** [monitoring.09, _observability.04]
**Unblocks:** []
**Estimated size:** M

**As a** platform operator,
**I need** named SLOs/SLIs with targets, recording rules, and burn-rate alerts for the alert pipeline,
**so that** I can tell at a glance whether monitoring is healthy and get paged before users complain.

### Current State
- No SLO/SLI definitions exist (`grep -rn "SLO\|SLI\|burn_rate" backend/monitoring/` returns nothing).
- Architecture §11 lists generic observability but does not name alert pipeline SLIs.
- Without targets (alert-creation-to-WS-broadcast p95, evaluation success rate, notification delivery rate, MTTA, FP ratio) operators cannot tell if the pipeline is healthy.

### Acceptance Criteria
- [ ] New `docs/monitoring_slos.md` publishes targets:
  - `alert_creation_to_broadcast_latency_p95 ≤ 2s`
  - `alert_evaluation_success_rate_30d ≥ 99.5%`
  - `alert_notification_delivery_rate_30d ≥ 99%` (per-channel)
  - `alert_mtta_p50_24h ≤ 15m`
  - `alert_false_positive_ratio_30d ≤ 0.25`
- [ ] Prometheus recording rules in `infra/prometheus/rules/monitoring.yaml` express each SLI; multi-window burn-rate alerts (1h × 14.4, 6h × 6) implemented per Google SRE workbook patterns.
- [ ] `/system/slos` endpoint (or `chili_app` page) renders current SLI value vs target.
- [ ] Each SLI sourced from a `monitoring.09` metric — no new instrumentation in this story.
- [ ] Runbook stubs link from each burn-rate alert to a section in `docs/monitoring_slos.md`.

### Verification
- `promtool check rules infra/prometheus/rules/monitoring.yaml` — passes.
- `curl http://localhost:8000/system/slos` returns JSON containing each SLI with `current`/`target`/`burn_rate_1h`.
- `pytest backend/tests/api/test_system_slos.py -v` — green.

### Code touch points
- `docs/monitoring_slos.md` (new)
- `infra/prometheus/rules/monitoring.yaml` (new)
- `backend/api/routers/system.py` (modify — `/system/slos`)
- `backend/tests/api/test_system_slos.py` (new)

---

## Story monitoring.11: Add alert stream replay — recompute alerts from historical observations

**ID:** monitoring.11
**Status:** planned
**Prerequisites:** [database.06, analytics.18]
**Unblocks:** []
**Estimated size:** L

**As a** fraud-ops engineer,
**I need** to replay historical observations through the current rule set without re-firing alerts,
**so that** I can validate new rule versions, recover deferred alerts (`monitoring.08`), or backfill alerts after fixing a bug — all without polluting the live dedup index.

### Current State
- `MonitoringService.evaluate` is single-shot per `MonitoringEvaluationRequest`; the dedup index is in-process memory (`backend/monitoring/service.py:79`).
- Replaying would re-fire every alert because dedup state is global.
- `PostgresObservationSource.load_batch` loads exactly one historical batch by `batch_id` (`backend/monitoring/adapters/postgres.py:82-109`) — no time-range query.
- No way to materialize "what alerts would have fired" without emitting them.

### Acceptance Criteria
- [ ] New `MonitoringService.replay(kb_id, from, to, *, dry_run, dedup_isolation, replay_run_id)` method:
  - Loads observations via a new `load_range(kb_id, from, to)` on `ObservationSourceProtocol`.
  - Runs the evaluator with an isolated dedup index (`dedup_isolation=True`).
  - `dry_run=True` returns the would-be alerts without publication or persistence.
  - `dry_run=False` persists alerts with `status="replayed"` and a `replay_run_id` and does **not** publish `AlertsCreatedEvent`.
- [ ] New `PostgresObservationSource.load_range` covered by an explicit time-range index.
- [ ] CLI tool `python -m monitoring.replay --kb <id> --from <ts> --to <ts> --dry-run` prints a summary table.
- [ ] Replay run summary persisted to a new `replay_runs` table (id, kb_id, from, to, dry_run, alert_count, created_at, created_by).
- [ ] UI surface explicitly deferred — note in `chili_app` follow-up story.

### Verification
- `pytest backend/tests/monitoring/test_replay.py -v` — green; covers dedup isolation, dry-run, persisted replay, idempotency on replay_run_id.
- `pytest --cov=backend/monitoring --cov-report=term-missing` — ≥ 85%.
- Local smoke: `python -m monitoring.replay --kb demo --from 2026-05-01 --to 2026-05-15 --dry-run` returns a non-empty alert count.

### Code touch points
- `backend/monitoring/service.py` (modify — replay method, isolated dedup)
- `backend/monitoring/adapters/protocols.py` (modify — `load_range`)
- `backend/monitoring/adapters/postgres.py` (modify — implement `load_range`)
- `backend/monitoring/replay.py` (new — CLI entry point)
- `backend/database/migrations/*.py` (new — `replay_runs` table)
- `backend/tests/monitoring/test_replay.py` (new)

---

## Story monitoring.12: Add tenant fields to alert storage

**ID:** monitoring.12
**Status:** planned
**Prerequisites:** [knowledgebases.06, monitoring.03, monitoring.05]
**Unblocks:** [monitoring.17]
**Estimated size:** L

### Narrative
As a tenant administrator,
I want alert records to carry tenant ownership,
so that alert history can be isolated across tenant boundaries.

### Current State
Alerting exists as an operational concept, but tenant scoping is not consistently represented in alert persistence.

### Acceptance Criteria
- [ ] Alert, notification, and delivery records include tenant or knowledge base ownership fields.
- [ ] Database migrations and repository models persist tenant ownership.
- [ ] Existing alert creation paths populate tenant context where available.
- [ ] Backfill or default behavior is documented for existing records.

### Verification
- [ ] Repository tests prove tenant fields are required or defaulted according to the migration plan.
- [ ] Migration tests cover forward and rollback behavior where supported.

### Code touch points
- `backend/app/monitoring/**`
- `backend/app/db/**`
- `backend/tests/**`

---
## Story monitoring.13: Implement core alert rule library

**ID:** monitoring.13
**Status:** planned
**Prerequisites:** [monitoring.05, monitoring.06]
**Unblocks:** [monitoring.19]
**Estimated size:** L

### Narrative
As an operator,
I want reusable alert rule types for common operational signals,
so that alerts can be configured consistently without custom code for every metric.

### Current State
Alert evaluation exists conceptually, but reusable rule definitions are not packaged as a library.

### Acceptance Criteria
- [ ] Rule schema supports metric selector, window, threshold, severity, labels, and notification routing hints.
- [ ] Implement threshold, percentile, and rate-of-change rule evaluators.
- [ ] Rule evaluators emit typed alert decisions with reason metadata.
- [ ] Default core rules are documented for ingestion, API, graph, and event health.

### Verification
- [ ] Unit tests cover each core rule evaluator and edge cases for missing data.
- [ ] Golden tests cover default rule definitions.

### Code touch points
- `backend/app/monitoring/**`
- `backend/tests/monitoring/**`
- `docs/wiki/modules/monitoring.md`

---
## Story monitoring.14: Self-reinforcing loop write-back — annotate graph when alerts close

**ID:** monitoring.14
**Status:** planned
**Prerequisites:** [monitoring.04, graph.07, analytics.22]
**Unblocks:** []
**Estimated size:** L

**As a** GNN/risk-model trainer,
**I need** alert resolution (and disposition labels) to write back to the graph entity as decremented counts and historical summaries,
**so that** the self-reinforcing loop in architecture §6.7 actually closes — letting risk scoring exploit "this entity has a 90% FP rate" or "previous alerts on this entity were benign."

### Current State
- Flow 4 (`handle_alerts_created_for_graph`, `backend/agent/coordinator.py:1535-1594`) snapshots `active_alert_count` / `last_alert_at` / `last_alert_severity` onto entities on **creation only**.
- No `AlertResolvedEvent` or `AlertDispositionEvent`; resolution and false-positive labels never feed back into the graph.
- `active_alert_count` is monotonically biased high vs reality.
- Downstream analytics (GNN features, risk scoring) cannot consume historical alert outcomes.

### Acceptance Criteria
- [ ] `AlertLifecycleEvent` (from `monitoring.04`) consumed by a new worker handler `handle_alert_lifecycle_for_graph`.
- [ ] Handler decrements `active_alert_count` (re-derives via `count_open_alerts`) and writes new entity properties:
  - `last_resolution_disposition`
  - `last_resolved_at`
  - `false_positive_rate_30d` (computed over `alert_activity_log` rolling 30 days)
  - `alert_history_summary` (compact JSON: `{count_30d, fp_count_30d, last_severity, last_disposition}`)
- [ ] Handler idempotent / replay-safe: derived from the audit log, never blind-incremented.
- [ ] `analytics.22` feature builder consumes the new properties (cross-edge contract verified by a fixture test).
- [ ] Wrapped in the DLQ + retry envelope (uses `run_handler_with_retry`).

### Verification
- `pytest backend/tests/agent/test_alert_lifecycle_for_graph.py -v` — green; covers acknowledge/resolve/dismiss/reopen all updating the entity correctly.
- `pytest --cov=backend/agent --cov-report=term-missing` — ≥ 85% maintained on the touched slice.
- Local smoke: trigger an alert, resolve as false-positive, query the entity in `/graph/entities/{id}`, observe `false_positive_rate_30d > 0` and decremented `active_alert_count`.

### Code touch points
- `backend/agent/coordinator.py` (modify — new handler + registration)
- `backend/events/types.py` (modify if not already covered by monitoring.04)
- `backend/analytics/gnn/features.py` (modify — consume new properties)
- `backend/tests/agent/test_alert_lifecycle_for_graph.py` (new)
- `backend/monitoring/AGENT.md` (modify — document the closed loop)

## Story monitoring.15: Add external notification channel adapters

**ID:** monitoring.15
**Status:** planned
**Prerequisites:** [monitoring.07]
**Unblocks:** [monitoring.16]
**Estimated size:** L

### Narrative
As an operator,
I want email, Slack, and webhook notification channels,
so that alerts can reach the systems my team already monitors.

### Acceptance Criteria
- [ ] Email, Slack, and generic webhook adapters implement the notification protocol.
- [ ] Channel configuration supports secrets by reference rather than inline values.
- [ ] Delivery results capture provider status and retryability.

### Verification
- [ ] Adapter tests cover success, retryable failure, permanent failure, and missing configuration.
- [ ] Fake provider fixtures avoid real network calls in unit tests.

### Code touch points
- `backend/app/monitoring/**`
- `backend/app/config/**`
- `backend/tests/monitoring/**`

---

## Story monitoring.16: Add notification retry, DLQ, and metrics coverage

**ID:** monitoring.16
**Status:** planned
**Prerequisites:** [monitoring.15, events.16]
**Unblocks:** [api.04, api.05]
**Estimated size:** M

### Narrative
As an operator,
I want failed notification deliveries to be retried, dead-lettered, and measured,
so that alert delivery failures are visible and recoverable.

### Acceptance Criteria
- [ ] Notification dispatcher applies retry policy with bounded attempts and backoff.
- [ ] Exhausted deliveries are written to the DLQ or equivalent failed-delivery store.
- [ ] Metrics expose attempts, successes, failures, retries, and dead-lettered notifications by channel.

### Verification
- [ ] Tests cover retry success, exhausted retry, DLQ write, and metric increments.
- [ ] Operations docs describe how to inspect failed notification deliveries.

### Code touch points
- `backend/app/monitoring/**`
- `backend/app/events/**`
- `backend/tests/**`

---

## Story monitoring.17: Enforce tenant scope in alert APIs

**ID:** monitoring.17
**Status:** planned
**Prerequisites:** [monitoring.12]
**Unblocks:** [monitoring.18]
**Estimated size:** L

### Narrative
As a tenant administrator,
I want alert APIs to filter by tenant scope,
so that users only see alerts they are allowed to inspect.

### Acceptance Criteria
- [ ] Alert list, detail, notification, and acknowledge APIs require tenant context.
- [ ] Repository queries filter by tenant or knowledge base ownership.
- [ ] Authorization failures do not reveal whether another tenant's alert exists.

### Verification
- [ ] API tests cover same-tenant access, cross-tenant denial, and missing-tenant rejection.
- [ ] Repository tests cover tenant-filtered queries.

### Code touch points
- `backend/app/api/**`
- `backend/app/monitoring/**`
- `backend/tests/**`

---

## Story monitoring.18: Filter websocket alert streams by tenant

**ID:** monitoring.18
**Status:** planned
**Prerequisites:** [monitoring.17]
**Unblocks:** []
**Estimated size:** M

### Narrative
As a tenant administrator,
I want realtime alert streams to respect tenant scope,
so that websocket subscribers cannot receive another tenant's operational events.

### Acceptance Criteria
- [ ] Websocket subscription handshake binds tenant context to the connection.
- [ ] Alert broadcasts are filtered before delivery to each subscriber.
- [ ] Tests cover cross-tenant broadcast isolation and disconnected tenant cleanup.

### Verification
- [ ] Websocket tests prove tenant A does not receive tenant B alert events.
- [ ] Metrics or logs identify filtered delivery counts without leaking payloads.

### Code touch points
- `backend/app/api/**`
- `backend/app/monitoring/**`
- `backend/tests/api/**`

---

## Story monitoring.19: Add pattern and ML-based alert rule adapters

**ID:** monitoring.19
**Status:** planned
**Prerequisites:** [analytics.32, monitoring.13]
**Unblocks:** [monitoring.20]
**Estimated size:** M

### Narrative
As an operator,
I want pattern and ML-backed alert rules,
so that alerting can capture anomalies that simple thresholds miss.

### Acceptance Criteria
- [ ] Pattern rule evaluator supports sequence or co-occurrence matching over metric/event windows.
- [ ] ML-backed rule adapter can consume analytics scores through the analytics service boundary.
- [ ] Rule outputs include explainability metadata suitable for alert detail views.

### Verification
- [ ] Unit tests cover pattern matches, non-matches, and analytics-score decisions.
- [ ] Fake analytics adapter keeps ML rule tests deterministic.

### Code touch points
- `backend/app/monitoring/**`
- `backend/app/analytics/**`
- `backend/tests/monitoring/**`

---

## Story monitoring.20: Add alert rule library hot reload and defaults

**ID:** monitoring.20
**Status:** planned
**Prerequisites:** [monitoring.19]
**Unblocks:** []
**Estimated size:** M

### Narrative
As an operator,
I want alert rule libraries to ship with defaults and reload safely,
so that rule updates do not require a full service redeploy.

### Acceptance Criteria
- [ ] Default rule library is loaded from configuration or packaged files at startup.
- [ ] Rule reload validates the full library before replacing active rules.
- [ ] Reload emits audit/event records with changed rule IDs and validation failures.

### Verification
- [ ] Tests cover successful reload, invalid reload rollback, and default library loading.
- [ ] Operations docs describe rule reload procedure and rollback behavior.

### Code touch points
- `backend/app/monitoring/**`
- `backend/app/config/**`
- `docs/wiki/modules/monitoring.md`

---
