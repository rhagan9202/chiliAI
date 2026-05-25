## File: docs/backlog/monitoring.md

**Scope:** Active monitoring (claim/observation stream evaluation), alert generation rules, dedup/suppression/rate-limit, alert lifecycle and disposition, alert routing, evidence-pack assembly handoff, notification delivery, alert read-projection, stream backpressure, alert metrics/SLOs, replay, tenant-scoped alerts, per-domain alert rule library, and self-reinforcing loop write-back.

Source-of-truth audit of `backend/monitoring/` against `docs/architecture.md` §5.2 (monitoring row), §6.2 (Active Monitoring flow), §6.4 Flow 4 (alert persistence/graph snapshot), §6.7 (self-reinforcing loop), §11 (observability), §14.2 (future capabilities), and the historical Epic 8 stories in `docs/archive/planning/backlog.md` lines 1527–1675. Done items skipped, intent carried forward where still unmet.

Done and intentionally **not** carried forward as epics:
- Threshold evaluation with rolling window + min-observations (`MonitoringService.evaluate`, `backend/monitoring/service.py:140-173`; E8-S01).
- Dedup index with eviction window — recent fix (`service.py:107-112,178-186`; commit 1faf175; E8-S02).
- Time-bounded suppression rules with entity/metric wildcards (`SuppressionRule` at `backend/monitoring/models.py:46`, `service.py:131-138,240-253`; E8-S03).
- Severity-aware rate limiting per evaluation (`service.py:188-198`; E8-S04).
- Alert lifecycle state machine + `transition_alert_status` (`service.py:49-55,281-313`; E8-S05).
- Alert grouping by entity_type within tolerance window (`_build_alert_groups`, `service.py:417-449`; E8-S06).
- Continuous evaluation triggered on `RiskScoredEvent` (`handle_risk_scored_for_monitoring` at `backend/agent/coordinator.py:1430-1475`; E8-S07).
- Plan C Flow 4: alert-history persistence + `active_alert_count` / `last_alert_at` / `last_alert_severity` graph snapshot (`handle_alerts_created_for_graph` at `coordinator.py:1535-1594`, `PostgresAlertHistoryStore` at `backend/monitoring/adapters/postgres.py:124-170`).
- `AlertProjectionRepository` in-memory + object-store implementations powering `GET /alerts*` (`backend/api/_alert_store.py:65-230`).

---

## Epic 1: Bridge AlertsCreatedEvent to the WebSocket hub for real-time push

**Gap:** `MonitoringService.evaluate` publishes `AlertsCreatedEvent` to the event bus (`backend/monitoring/service.py:207-226`) and `WebSocketHub.broadcast` exists on `/ws/alerts` (`backend/api/routers/ws.py:118-134,207-213`), but **no code subscribes the hub to `AlertsCreatedEvent`** — `grep -r "ws_hub\|hub.broadcast"` in non-test code returns only `get_ws_hub` definitions. The hub's own docstring states "the event bus bridge is wired in Epic 8 — for now the hub accepts direct `broadcast` calls" (`ws.py:5-7`). Frontend WS subscribers receive nothing on alert creation; Flow B's terminal `WS: alerts → Analyst` arrow in §6.2 is not implemented.

**Outcome:** an `AlertEventBusBridge` running in the API process subscribes to `alerts.created`, projects to the WS `AlertCreated` payload shape, and broadcasts through `WebSocketHub` with the severity filter applied. The bridge survives Redis reconnects, drops oversized backlog with a counter, and is covered by an integration test that pushes a synthetic event end-to-end.

---

## Epic 2: Wire AlertProjectionRepository upserts on AlertsCreatedEvent

**Gap:** `AlertProjectionRepository.upsert` (`backend/api/_alert_store.py:69,92`) is never called by any production handler. The agent coordinator writes alert history to Postgres and snapshots onto graph entities (`coordinator.py:1535-1594`) but does **not** insert into the API projection, so `GET /alerts` returns an empty feed in any fresh deployment until something seeds it. Cross-edge to `api.md` for the projection contract.

**Outcome:** new `handle_alerts_created_for_projection` consumer (or extension of Flow 4) calls `AlertProjectionRepository.upsert` with the alert plus enrichment context (entity label resolved through `GraphService`, related entity ids from the evidence pack, policy citations if present). Idempotent on alert_id. Same DLQ wrapper as the other Flow C handlers.

---

## Epic 3: Add asset-criticality and confidence weighting to alert prioritization

**Gap:** Severity is a flat tier mapped purely from observation score against medium/high thresholds (`_to_alert_candidate` at `backend/monitoring/service.py:385-401`). The shared `Alert.severity` is a bare `str` with a TODO to become a `SeverityLevel` enum (`backend/shared/types.py:117-119`). `AlertProjectionRecord.confidence` is collected by the projection (`api/_alert_store.py:49`) but `MonitoringService` never emits a confidence value — the projection defaults to `0.0`. There is no concept of asset criticality on entities or in the alert payload, so prioritization in the alert table is severity-only sort.

**Outcome:** introduce `SeverityLevel` enum at the shared boundary; extend `AlertCandidate`/`Alert` with `confidence: float` and `priority: float` (composite of severity tier × confidence × asset criticality from entity properties or KB-scoped weights); `MonitoringService.evaluate` writes confidence from observation rationale/score; rate-limit sort and projection sort both use `priority` instead of severity-only.

---

## Epic 4: Add alert disposition workflow — escalate, dismiss, false-positive labels

**Gap:** The lifecycle state machine supports `open → acknowledged → investigating → resolved/dismissed` plus a "reopen" edge (`ALERT_TRANSITIONS` at `backend/monitoring/service.py:49-55`), and `AlertsService` exposes only `acknowledge_alert` / `resolve_alert` (`service.py:327-366`). There is **no API endpoint for resolve/dismiss/escalate** — `backend/api/routers/alerts.py:53-73` exposes acknowledge only via the projection helper, and the projection's `acknowledge` doesn't route through the lifecycle state machine. There is no `false_positive` label, no escalation target, and no audit trail beyond the per-row `updated_at` field.

**Outcome:** `POST /alerts/{id}/{resolve,dismiss,escalate,reopen}` endpoints flow through `AlertsService` (and projection in lockstep); add `disposition: Literal["true_positive", "false_positive", "benign", "unknown"]` and `escalation_target: str | None` to `Alert`; an `AlertActivityLog` table records every transition with actor, timestamp, and reason for audit. Cross-edge to `_security.md` (audit log) and `api.md`.

---

## Epic 5: Add alert routing — queue alerts to specific roles or analysts

**Gap:** No routing logic anywhere. Every alert lands in one global feed and the same WS broadcast goes to every connected `viewer` (subject only to optional severity filter, `backend/api/routers/ws.py:39-43,72-75`). There is no `assigned_to`, no team queue, no round-robin, no on-call rotation. RBAC permissions like `alerts:read` and `cases:assign` exist in domain config (`backend/config/defaults/medicare_fraud.yaml:224,228`) but are not used to filter routing.

**Outcome:** `Alert.assigned_to: str | None` and `Alert.assigned_team: str | None`; a `RoutingRule` model (entity_type / severity / metric_name / KB → target role/team/user) loaded from `MonitoringConfig.routing_rules`; `MonitoringService.evaluate` evaluates rules per alert; WS broadcast and `GET /alerts` both filter by the caller's role/identity; `POST /alerts/{id}/assign` lifecycle action. Cross-edge to `_security.md` (RBAC), `config.md` (rule schema).

---

## Epic 6: Assemble evidence packs for generated alerts (cross-edge to analytics + graph)

**Gap:** `AlertCandidate.evidence_pack_id` and `Alert.evidence_pack_id` are wired through the model (`backend/monitoring/models.py:43`, `shared/types.py:122`) but `_to_alert_candidate` copies the id straight from the observation without ever calling an evidence-pack builder (`backend/monitoring/service.py:385-401`). The actual `EvidencePack` type lives in `shared/types.py:134` and `analytics/explainability/service.py:57` builds them, but the monitoring pipeline does not invoke explainability when generating an alert — every alert's evidence pack id is whatever the upstream `MonitoringObservation` carried (records pipeline maps it from `MonitoringObservationMappingConfig`, but most observations have it `None`). The UI alert detail (`api/contracts.AlertDetailResponse`) relies on a populated evidence pack for analyst review.

**Outcome:** `MonitoringService.evaluate` invokes an `EvidencePackBuilder` (new protocol) per generated alert; default implementation calls `analytics.explainability.service` for the subgraph + risk-factor narrative and persists the pack via a new `EvidencePackStore`; alert publication waits on the pack id; budget asserts pack assembly stays under N ms p95. Cross-edges to `analytics.md` (explainability invocation) and `graph.md` (Epic 5 filtered subgraph extraction).

---

## Epic 7: Add alert notification delivery — email, webhook, Slack, in-app

**Gap:** Nothing. `grep -rn "Slack\|SmtpNotifier\|WebhookNotifier"` across `backend/` returns nothing (other than the protocols TODO). The only delivery path today is the unwired WS hub (Epic 1) and the polled `GET /alerts` endpoint. Architecture §14.2 lists `Alert notifications: Email, webhook, Slack, in-app` as medium priority.

**Outcome:** `NotificationChannel` protocol with adapters (`EmailNotifier`, `SlackNotifier`, `WebhookNotifier`, `InAppNotifier`); `NotificationDispatcher` consumes `AlertsCreatedEvent`, evaluates per-domain notification rules (channel × severity × routing target), and dispatches asynchronously with retries; per-channel rate limit; failures land in a `notification_dlq` Redis stream. Cross-edges to `config.md` (channel config), `_observability.md` (delivery metrics), and `_security.md` (channel credentials in secrets store).

---

## Epic 8: Add stream-level backpressure when alert rate spikes

**Gap:** Per-evaluation rate limit exists (`MonitoringService.max_alerts_per_evaluation`, default 100, with severity-sorted truncation at `backend/monitoring/service.py:188-198`), but there is **no cross-evaluation backpressure**. A burst of `RiskScoredEvent`s triggers `MonitoringService.evaluate` per-assessment in `handle_risk_scored_for_monitoring` (`backend/agent/coordinator.py:1444-1474`) — failures are absorbed and logged but successes continue at full speed. There is no token-bucket per KB, no consumer-group lag observation, no shed-on-overload behavior, and no signal to upstream producers when the alert pipeline falls behind.

**Outcome:** per-KB token-bucket (or leaky-bucket) limiter at `handle_risk_scored_for_monitoring`; soft and hard ceilings; on hard-ceiling, alerts are persisted to `alert_history` with `status="deferred"` and a `deferred_reason` rather than published to the WS/notification path; Redis Streams consumer-group lag exposed as a gauge to feed autoscaling; load-shed metrics. Cross-edge to `_observability.md`, `events.md`.

---

## Epic 9: Add alert metrics — count, MTTA, MTTR, false-positive rate

**Gap:** Only one alert-specific Prometheus metric exists: `active_alerts_total` gauge (`backend/monitoring/metrics.py:37-40`), and it is **never written from** monitoring code (`grep` shows zero `active_alerts_total.set/inc/dec` callers). No counters for alerts generated, suppressed-by-dedup, suppressed-by-rule, rate-limited, escalated; no histograms for MTTA (time-to-acknowledge), MTTR (time-to-resolve), or evaluation latency; no FP rate computed from disposition labels (Epic 4 prerequisite). The `MonitoringEvaluationResponse` carries the counts but they are not exported. Cross-edge to `_observability.md`.

**Outcome:** module-prefixed metrics (`chili_monitoring_alerts_created_total{severity}`, `chili_monitoring_alerts_suppressed_total{reason}`, `chili_monitoring_eval_duration_seconds`, `chili_monitoring_mtta_seconds`, `chili_monitoring_mttr_seconds`, `chili_monitoring_false_positive_ratio`); `active_alerts_total` updated on every projection upsert/transition; metrics emitted from `MonitoringService.evaluate` and `AlertsService` lifecycle methods.

---

## Epic 10: Define and instrument alert SLOs/SLIs

**Gap:** No SLO/SLI definitions exist anywhere for monitoring (verified via `grep -rn "SLO\|SLI\|burn_rate" backend/monitoring/`). Architecture §11 lists generic observability but does not name alert pipeline SLIs. Without explicit targets (e.g., alert-creation-to-WS-broadcast p95, evaluation success rate, notification delivery rate) operators can't tell if the pipeline is healthy.

**Outcome:** SLOs published in `docs/monitoring_slos.md`: alert-creation-to-broadcast latency, alert-evaluation success rate, alert-notification delivery rate, MTTA target, false-positive ratio ceiling; matching Prometheus recording rules + burn-rate alerts; SLO page in `chili_app` or a `/system/slos` endpoint. Hard requires Epic 9. Cross-edge to `_observability.md`.

---

## Epic 11: Add alert stream replay — recompute alerts from historical observations

**Gap:** No replay path. `MonitoringService.evaluate` is single-shot per `MonitoringEvaluationRequest`; the dedup index is in-process memory (`backend/monitoring/service.py:79`), so replay would re-fire every alert. There is no way to: (a) re-run a rule change against the last N hours of observations, (b) replay a single KB's stream without affecting global state, or (c) materialize "what alerts would have fired" without emitting them. `PostgresObservationSource.load_batch` (`backend/monitoring/adapters/postgres.py:82-109`) can load one historical batch but only by exact `batch_id`.

**Outcome:** `MonitoringService.replay(kb_id, from, to, *, dry_run, dedup_isolation)` that loads historical observations, runs the evaluator with an isolated dedup index, returns the would-be alerts without publication (`dry_run=True`) or persists them with `status="replayed"` and a `replay_run_id`; CLI tool `python -m monitoring.replay` for ad-hoc; UI surface deferred. Cross-edge to `database.md` (`observations` time-range query), `analytics.md` (replay coordinates with risk score replay).

---

## Epic 12: Add tenant-scoped alerts across generation, storage, broadcast, and projection

**Gap:** No `tenant_id` on `Alert`, `AlertCandidate`, `AlertHistoryRecord`, or `MonitoringObservation` (`grep -n "tenant" backend/monitoring/*.py backend/monitoring/adapters/*.py` returns nothing). `MonitoringService` is a process-singleton with one shared dedup index. `PostgresAlertHistoryStore` writes/queries with `knowledge_base_id` and `entity_id` only (`backend/monitoring/adapters/postgres.py:33-44,160-170`). `AlertProjectionRepository.list` has no tenant filter. WS `/ws/alerts` broadcasts to all `viewer`-role connections regardless of tenancy. Architecture §14.2 lists multi-tenancy as medium priority; tenant-scoped alerts is one of its hardest sub-problems.

**Outcome:** `tenant_id` propagated end-to-end (observation → candidate → alert → history → projection → WS); per-tenant dedup index isolation in `MonitoringService`; SQL queries gain `tenant_id` in the unique key; WS hub gains tenant filter; `GET /alerts` and `POST /alerts/*` default-deny across tenants. Hard requires `_multitenancy.md` foundation. Cross-edge to `_multitenancy.md`, `_security.md`.

---

## Epic 13: Build a per-domain alert rule library — config-driven generation rules

**Gap:** `AlertsConfig.thresholds` (`backend/config/schema.py:214-220`) declares only `dict[str, dict[str, float]]` (entity_type → metric_name → threshold), but **no code reads it** — `MonitoringService.evaluate` uses only `default_medium_threshold` / `default_high_threshold` plus per-request overrides (`service.py:80-81,116-125`). The TODO at `schema.py:218-220` explicitly calls out missing dedup window, max-per-entity, suppression rules, escalation policies, and configurable severity tiers. There is **no concept of a named "rule"** at all (e.g., `ratio_outlier(metric=billing_cost, percentile=95, window=24h)` vs the current scalar-threshold-only model). Pattern-based and ML-based alert rules (architecture §6.2 implies risk-scorer integration but there is no pattern matcher in `monitoring/`) do not exist.

**Outcome:** `AlertRule` discriminated union (threshold | percentile | rate-of-change | pattern | ml-classifier) loaded from `DomainConfig.alerts.rules`; per-entity-type and per-metric thresholds actually consumed; `RuleEvaluator` strategy per rule kind; rule library shipped per default domain (`medicare_fraud`, `food_supply_chain`); hot-reload on config change. Cross-edge to `config.md` (rule schema), `analytics.md` (pattern/ML rule signals).

---

## Epic 14: Self-reinforcing loop write-back — annotate graph when alert closes

**Gap:** Flow 4 (`handle_alerts_created_for_graph`, `backend/agent/coordinator.py:1535-1594`) snapshots `active_alert_count` / `last_alert_at` / `last_alert_severity` onto entities on **creation only**. There is no `AlertResolvedEvent` or `AlertDispositionEvent`, so resolution and false-positive labels never feed back into the graph. The self-reinforcing loop in architecture §6.7 requires "Each monitoring cycle produces a progressively richer graph" — today the graph learns about alerts opening but not closing, so `active_alert_count` is monotonically increasing relative to the truth, and downstream analytics (GNN features, risk scoring) cannot exploit "this entity has a 90% false-positive rate" or "previous alerts on this entity were benign."

**Outcome:** new `AlertLifecycleEvent` (or per-disposition events) published by `AlertsService.resolve_alert` / lifecycle methods; matching `handle_alert_lifecycle_for_graph` worker handler decrements `active_alert_count`, writes `last_resolution_disposition`, `false_positive_rate_30d`, and `alert_history_summary` properties onto the entity; subsequent risk scoring and GNN feature builders consume these new properties (cross-edge to `analytics.md`). Idempotent / replay-safe.

---

## Open Questions

1. Evidence-pack assembly latency (Epic 6) — is synchronous build inside `MonitoringService.evaluate` acceptable, or must it be a second-stage async handler so alert publication is not gated on subgraph extraction? Affects Epic 1 (what payload the WS bridge sends — alert with pack id vs full pack) and Epic 6 design.
2. Notification delivery (Epic 7) — is "in-app" notification just the existing WS push (Epic 1), or a separate notification-center concept persisted per-user? If separate, add a `notification_inbox` table here or in `api.md`?
3. Alert rule library (Epic 13) — should ML-based rules invoke a model server (cross-edge to `analytics.md` GNN/risk modules) or stay declarative-only with thresholds against pre-computed risk scores? The latter is the cheapest path and matches the current Plan-C analytics flow.
4. Tenant-scoped dedup (Epic 12) — does the dedup index need a per-tenant TTL knob, or is one global `dedup_window_seconds` acceptable for all tenants? Affects `MonitoringConfig` shape.
5. Backpressure semantics (Epic 8) — on hard-ceiling, do we drop alerts entirely (loss-of-availability), defer them (latency hit but no loss), or sample them (statistical loss)? Operator preference likely "defer."
6. Routing precedence (Epic 5) — when multiple routing rules match an alert (e.g., both an entity-type rule and a severity rule), is first-match-wins or all-targets-fan-out the intended semantic?
7. Disposition labels (Epic 4) — do we need a richer taxonomy (e.g., `policy_violation_confirmed`, `data_quality_artifact`, `benign_pattern`) or is the 4-tier `true_positive | false_positive | benign | unknown` sufficient for the Medicare exemplar?
