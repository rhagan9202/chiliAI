# _observability backlog

> **Scope:** Logging, metrics (Prometheus/OTEL), tracing, frontend RUM, dashboards, alerting on platform health.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

## Story _observability.01: Adopt shared structlog across all backend modules

**ID:** _observability.01
**Status:** in-progress
**Prerequisites:** []
**Unblocks:** [_observability.02, _observability.03, _observability.04, _observability.10, _observability.13, _security.07, rag.13, records.06, vectorstore.12]
**Estimated size:** M

**As a** backend developer,
**I need** every module to emit logs through `shared.logging.get_logger` instead of stdlib `logging.getLogger`,
**so that** every log line carries JSON structure, the bound `correlation_id` contextvar, and a uniform field schema across API, worker, ingestion, graph, RAG, and monitoring code paths.

### Current State
- `shared/logging.py` configures structlog process-wide and exposes `configure_logging`, `get_logger`, `bind_correlation_id`, `clear_correlation_id` (backend/shared/logging.py:20-25); the contextvar is defined at backend/shared/logging.py:28-30.
- Only two entry points actually consume the helper: `api/app.py:105` calls `configure_logging()` inside `create_app()`, and `agent/coordinator.py:160` imports `bind_correlation_id, configure_logging, get_logger` from `shared.logging`.
- Several modules still hold stdlib loggers — for example `agent/health.py:19` (`logger = logging.getLogger("chili.worker.health")`), `vectorstore/service.py:30`, `ingestion/extractor.py:38`, and `shared/kb_scope.py:15` — so their lines bypass JSON rendering and the correlation processor.
- Architecture §11.1 mandates structlog as the single logging library with JSON output in production and the INFO/WARNING/ERROR level taxonomy (docs/architecture.md:1234-1239).

### Acceptance Criteria
- [ ] Every `logging.getLogger(` call under `backend/` (excluding `backend/.venv/` and third-party stubs) is replaced with `from shared.logging import get_logger` + `logger = get_logger(__name__)`.
- [ ] A repo-wide grep (`rg "logging\.getLogger\(" backend --glob '!**/.venv/**'`) returns zero hits in first-party code (tests for the logging module itself are allowed and asserted by name).
- [ ] `backend/shared/logging.py` exports a `configure_logging()` call hook that is invoked once at `create_app()` and once at worker `main()` boot — both call sites verified by tests.
- [ ] A new test `backend/tests/shared/test_logging_adoption.py` walks `backend/` and asserts no stdlib `logging.getLogger` survives in first-party modules.
- [ ] `docs/architecture.md` §11.1 is referenced from the modules' READMEs as the contract for log shape.

### Verification
- Run `cd backend && rg "logging\.getLogger\(" --glob '!**/.venv/**' --glob '!**/__pycache__/**'` and confirm only `tests/shared/test_logging.py` and `tests/shared/test_logging_adoption.py` match.
- Run `pytest backend/tests/shared/test_logging_adoption.py -v` — must pass.
- Boot the API (`uvicorn api.app:create_app --factory`) and the worker (`python -m agent.coordinator`), exercise one request and one event, and confirm both stdout streams emit JSON lines with a `correlation_id` field.
- Coverage gate: ≥ 85% on `backend/shared/`.

### Code touch points
- `backend/shared/logging.py` (modify)
- `backend/agent/health.py` (modify)
- `backend/vectorstore/service.py` (modify)
- `backend/ingestion/extractor.py` (modify)
- `backend/shared/kb_scope.py` (modify)
- `backend/tests/shared/test_logging_adoption.py` (new)


## Story _observability.02: HTTP correlation-ID middleware with response-header propagation

**ID:** _observability.02
**Status:** planned
**Prerequisites:** [_observability.01]
**Unblocks:** [_observability.03, _observability.10, _observability.11, agent.17, graph.01, graph.07, graph.10, graph.13, graph.16, llm.09, llm.10, records.06]
**Estimated size:** S

**As an** API operator,
**I need** every inbound HTTP request to seed `shared.logging._CORRELATION_ID_CTX` (from either an inbound `X-Request-Id` / `traceparent` header or a freshly minted ULID) and echo the resolved id back on the response,
**so that** every log line, span, and downstream event produced while handling that request can be cross-correlated end-to-end from the browser to the worker.

### Current State
- The contextvar at `backend/shared/logging.py:28-30` exists and is read by `_correlation_id_processor` (backend/shared/logging.py:49-58), but no FastAPI middleware seeds it on inbound requests.
- `grep -rn "X-Correlation\|X-Request-Id\|traceparent" backend/api/` returns no first-party matches — the gateway never reads or sets these headers.
- `backend/api/app.py:134-135` registers `register_metrics(app)` and `instrument_fastapi_app(app)` but no correlation middleware sits before them.
- `backend/events/types.py:14-20` declares `EventBase.correlation_id` with `default_factory=generate_id`, so every event today generates its own id divorced from the originating request.

### Acceptance Criteria
- [ ] New `backend/api/middleware/correlation.py` exports a `CorrelationIdMiddleware` ASGI class that reads `X-Request-Id` (preferred) or `traceparent` from request headers, falls back to `shared.utils.generate_id()`, binds it via `bind_correlation_id`, and clears it on response.
- [ ] The middleware adds `X-Request-Id: <id>` to every response (including error responses) regardless of inbound presence.
- [ ] `create_app()` (backend/api/app.py:102-164) registers `CorrelationIdMiddleware` ahead of `MetricsMiddleware` so metric labels (when added in _observability.04/12) and logs see the same id.
- [ ] `backend/tests/api/middleware/test_correlation.py` covers: (a) inbound id is honored, (b) absent id triggers generation, (c) header is present on the response, (d) `clear_correlation_id` runs even when the handler raises.
- [ ] `backend/api/README.md` documents the header contract.

### Verification
- `pytest backend/tests/api/middleware/test_correlation.py -v` passes with all four cases green.
- Manual: `curl -i http://localhost:8000/health -H 'X-Request-Id: abc123'` echoes `X-Request-Id: abc123`; same call without the header yields a generated id.
- Run the API with `LOG_FORMAT=json` and confirm the `health` log line carries `correlation_id=abc123`.
- Coverage gate: ≥ 85% on `backend/api/middleware/`.

### Code touch points
- `backend/api/middleware/correlation.py` (new)
- `backend/api/app.py` (modify)
- `backend/api/middleware/__init__.py` (modify)
- `backend/api/README.md` (modify)
- `backend/tests/api/middleware/test_correlation.py` (new)


## Story _observability.03: Propagate correlation-ID and W3C Trace Context across Redis Streams events

**ID:** _observability.03
**Status:** planned
**Prerequisites:** [_observability.01, _observability.02]
**Unblocks:** [_observability.06, _plugins.10, agent.17, api.08, api.20, embeddings.04, events.05, graph.13, ingestion.17, knowledgebases.12, llm.09, monitoring.09]
**Estimated size:** M

**As a** platform operator,
**I need** every `EventBase` published to Redis Streams to carry the originating `correlation_id` and a W3C `traceparent` header so the worker rebinds both when it consumes the event,
**so that** a single trace tree spans the API request, the published event, every worker stage, and the resulting spans inside RAG/graph/LLM calls (architecture §11.3).

### Current State
- `EventBase` at `backend/events/types.py:14-20` already carries `correlation_id` but has no `traceparent` field and no inject/extract helpers on the event bus.
- `shared/tracing.py:103-129` exposes `start_pipeline_span` and sets `correlation_id` as a span attribute (backend/shared/tracing.py:124-125), but never maps it onto the W3C trace context.
- Producers (e.g. `backend/api/routers/knowledgebases.py` publishing `KnowledgeBaseCreatedEvent`) call `bus.publish(...)` with no propagation; consumers (`backend/agent/coordinator.py:160` onward) read `event.correlation_id` only.
- Open question from the auditor (resolved here): unify `correlation_id` and W3C `trace_id` by treating `correlation_id` as the human-readable handle and `traceparent` as the OTel context carrier; both fields ship on every event.

### Acceptance Criteria
- [ ] `EventBase` gains an optional `traceparent: str | None` field (backend/events/types.py).
- [ ] `backend/events/propagation.py` exports `inject_context(event: EventBase) -> EventBase` and `extract_context(event: EventBase) -> contextvars.Context` that round-trip both fields via `opentelemetry.propagate.inject/extract` when the optional `[observability]` extra is installed (and degrade to no-op when not).
- [ ] All event-bus adapters under `backend/events/adapters/` call `inject_context` on publish and `extract_context` on consume; the worker `run_handler_with_retry` path (referenced in commit a0a2a38) rebinds `correlation_id` via `bind_correlation_id` and re-enters the trace.
- [ ] `backend/tests/events/test_propagation.py` asserts: round-trip of `correlation_id`, round-trip of `traceparent`, no-op when OTel is absent, that consumer-side spans are children of the producer-side span when both ends have OTel installed.
- [ ] `docs/architecture.md` §11.3 referenced from `backend/events/README.md` with a worked example.

### Verification
- `pytest backend/tests/events/test_propagation.py -v` passes.
- With the `[observability]` extra installed and `OTEL_EXPORTER_OTLP_ENDPOINT` pointed at a console exporter, publish one event from a unit test and consume it; assert via the captured span exporter that producer and consumer spans share the same `trace_id`.
- Coverage gate: ≥ 85% on `backend/events/`.

### Code touch points
- `backend/events/types.py` (modify)
- `backend/events/propagation.py` (new)
- `backend/events/adapters/in_memory.py` (modify)
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/events/README.md` (modify)
- `backend/tests/events/test_propagation.py` (new)


## Story _observability.04: Implement the architecture-defined Prometheus metric set

**ID:** _observability.04
**Status:** planned
**Prerequisites:** [_observability.01]
**Unblocks:** [_observability.05, _observability.07, _observability.08, _observability.12, _observability.13, agent.14, analytics.04, analytics.26, api.06, api.07, database.10, llm.08, monitoring.10, rag.11, rag.13, storage.09]
**Estimated size:** M

**As an** operator,
**I need** the `/metrics` endpoint to expose every metric named in architecture §11.2 — including the four currently missing ones — with consistent label cardinality,
**so that** dashboards and alert rules in _observability.08 can rely on the full set.

### Current State
- HTTP metrics live at `backend/api/middleware/metrics.py:29-39` (`http_requests_total`, `http_request_duration_seconds`).
- Pipeline metrics live at `backend/monitoring/metrics.py:25-40` (`pipeline_stage_duration_seconds`, `pipeline_errors_total`, `active_alerts_total`).
- The arch §11.2 list also requires `pipeline_events_processed_total` (by event type), `graph_query_duration_seconds`, `alerts_generated_total` (by entity type and severity), and `knowledgebase_documents_total` (docs/architecture.md:1247-1251) — none exist.
- The `/metrics` route at `backend/api/middleware/metrics.py:99` is `require_role("service")`-gated; this story keeps that gating (resolves the auditor's open question by treating "private port" as a future _infra concern, not a metric story).

### Acceptance Criteria
- [ ] `backend/monitoring/metrics.py` declares `pipeline_events_processed_total: Counter` with labels `["event_type"]` and a public helper `record_event_processed(event_type)`.
- [ ] `backend/graph/metrics.py` (new) declares `graph_query_duration_seconds: Histogram` with labels `["operation"]` and exports `observe_graph_query(operation: str)` context manager.
- [ ] `backend/monitoring/metrics.py` declares `alerts_generated_total: Counter` with labels `["entity_type", "severity"]` and `record_alert_generated(entity_type, severity)` helper.
- [ ] `backend/knowledgebases/metrics.py` (new) declares `knowledgebase_documents_total: Gauge` with labels `["kb_id"]` and a refresh hook called from the KB service.
- [ ] All four new metrics show up in `curl http://localhost:8000/metrics` (when authenticated as the `service` role).
- [ ] Unit tests under `backend/tests/{monitoring,graph,knowledgebases}/test_metrics.py` assert the counter/histogram/gauge declarations and helper behavior.

### Verification
- `pytest backend/tests/monitoring/test_metrics.py backend/tests/graph/test_metrics.py backend/tests/knowledgebases/test_metrics.py -v` passes.
- Boot the API, ingest a KB, fire one event, generate one alert, then `curl -s -H 'Authorization: Bearer <service-token>' http://localhost:8000/metrics | grep -E "(pipeline_events_processed|graph_query_duration|alerts_generated|knowledgebase_documents)_total"` returns four families.
- Coverage gate: ≥ 85% on `backend/monitoring/`, `backend/graph/`, `backend/knowledgebases/` metric modules.

### Code touch points
- `backend/monitoring/metrics.py` (modify)
- `backend/graph/metrics.py` (new)
- `backend/knowledgebases/metrics.py` (new)
- `backend/tests/monitoring/test_metrics.py` (modify)
- `backend/tests/graph/test_metrics.py` (new)
- `backend/tests/knowledgebases/test_metrics.py` (new)


## Story _observability.05: Instrument graph, vectorstore, embeddings, and LLM adapters with latency histograms

**ID:** _observability.05
**Status:** planned
**Prerequisites:** [_observability.04]
**Unblocks:** [_cicd.14, _observability.08, _plugins.10, analytics.26, api.17, embeddings.04, graph.14, ingestion.17, vectorstore.13, vectorstore.14]
**Estimated size:** M

**As an** SRE,
**I need** every external-system adapter call (graph query, vector search/upsert, embedding generation, LLM completion) to record a Prometheus histogram tagged with the adapter and operation,
**so that** I can diagnose which provider is slow without re-instrumenting at the service layer.

### Current State
- `grep -rn "prometheus_client" backend/graph/ backend/vectorstore/ backend/embeddings/ backend/llm/` returns no first-party matches — adapters emit no metrics.
- The coordinator wraps stages with `observe_pipeline_stage` (backend/monitoring/metrics.py:43-55), but that is per-stage, not per-adapter-call.
- Architecture §11.2 names `graph_query_duration_seconds` explicitly; the per-stage histogram should also cover embedding and LLM calls per stage label (auditor notes).

### Acceptance Criteria
- [ ] `backend/vectorstore/metrics.py` (new), `backend/embeddings/metrics.py` (new), `backend/llm/metrics.py` (new) each declare a histogram named `<module>_call_duration_seconds` with labels `["adapter", "operation"]` and a context-manager helper `observe_<module>_call(adapter, operation)`.
- [ ] `backend/graph/metrics.py` (from _observability.04) gains `observe_graph_query(operation)` usage inside every public method of the in-memory and Neo4j adapters.
- [ ] Every concrete adapter under `backend/{graph,vectorstore,embeddings,llm}/adapters/` wraps its public method bodies with the helper context manager; private helpers are exempt.
- [ ] Adapter-level error counter `<module>_call_errors_total{adapter,operation,error_class}` records exceptions (including timeouts) without swallowing them.
- [ ] Tests under `backend/tests/{graph,vectorstore,embeddings,llm}/test_metrics_instrumentation.py` assert that a sample call increments the histogram and a raised exception increments the error counter.

### Verification
- `pytest backend/tests/{graph,vectorstore,embeddings,llm}/test_metrics_instrumentation.py -v` passes.
- Run the worker against a seeded KB and confirm `curl /metrics` shows non-zero counts for `graph_query_duration_seconds_count{adapter="neo4j"}` and `llm_call_duration_seconds_count{adapter="openai"}` (or `local`).
- Coverage gate: ≥ 85% on each of `backend/{graph,vectorstore,embeddings,llm}/`.

### Code touch points
- `backend/graph/metrics.py` (modify)
- `backend/vectorstore/metrics.py` (new)
- `backend/embeddings/metrics.py` (new)
- `backend/llm/metrics.py` (new)
- `backend/graph/adapters/*.py` (modify)
- `backend/vectorstore/adapters/*.py` (modify)
- `backend/embeddings/adapters/*.py` (modify)
- `backend/llm/adapters/*.py` (modify)
- `backend/tests/graph/test_metrics_instrumentation.py` (new)
- `backend/tests/vectorstore/test_metrics_instrumentation.py` (new)
- `backend/tests/embeddings/test_metrics_instrumentation.py` (new)
- `backend/tests/llm/test_metrics_instrumentation.py` (new)


## Story _observability.06: Wire OpenTelemetry spans across RAG, graph-expand, and LLM call paths

**ID:** _observability.06
**Status:** planned
**Prerequisites:** [_observability.03]
**Unblocks:** [_observability.12, api.18, embeddings.05]
**Estimated size:** M

**As an** analyst debugging a slow RAG response,
**I need** the OTel trace for the request to include child spans for each retrieval stage, each graph expansion hop, and each LLM call,
**so that** I can see end-to-end where time was spent without correlating timestamps manually.

### Current State
- `setup_tracing` and `instrument_fastapi_app` are called at API boot (`backend/api/app.py:106, 135`) and OTel is set up at worker boot.
- `start_pipeline_span` (backend/shared/tracing.py:103-129) exists, but `rg "get_tracer|start_pipeline_span" backend/rag/ backend/graph/ backend/llm/` returns nothing — none of these modules emit spans.
- The coordinator uses `start_pipeline_span` for its workflow stages, leaving downstream service calls untraced.

### Acceptance Criteria
- [ ] `backend/rag/service.py` wraps the public query entry point and each substage (embed, vector search, graph expand, LLM compose) with `start_pipeline_span("rag.<substage>", attributes={"kb_id": ..., "query_id": ...})`.
- [ ] `backend/graph/service.py` wraps every public method with `start_pipeline_span("graph.<method>", attributes={"adapter": ...})`.
- [ ] Each `backend/llm/adapters/*.py` `complete()` / `stream()` method wraps the call with `start_pipeline_span("llm.<adapter>.complete", attributes={"model": ..., "prompt_tokens": ...})`.
- [ ] When the `[observability]` extra is not installed, spans degrade to no-ops (already the contract of `start_pipeline_span`) and no module raises.
- [ ] Tests under `backend/tests/{rag,graph,llm}/test_tracing.py` use an in-memory span exporter to assert the expected span tree is produced for a sample call.

### Verification
- `pytest backend/tests/{rag,graph,llm}/test_tracing.py -v` passes.
- With the `[observability]` extra installed and an OTLP endpoint pointed at a console exporter, hit `POST /rag/query` and confirm the printed span tree contains the expected substage children.
- Coverage gate: ≥ 85% on `backend/rag/`, `backend/graph/`, `backend/llm/`.

### Code touch points
- `backend/rag/service.py` (modify)
- `backend/graph/service.py` (modify)
- `backend/llm/adapters/openai_adapter.py` (modify)
- `backend/llm/adapters/anthropic_adapter.py` (modify)
- `backend/llm/adapters/ollama_adapter.py` (modify)
- `backend/llm/adapters/local.py` (modify)
- `backend/tests/rag/test_tracing.py` (new)
- `backend/tests/graph/test_tracing.py` (new)
- `backend/tests/llm/test_tracing.py` (new)


## Story _observability.07: Stand up an observability stack in dev compose (Prometheus + Grafana + Jaeger/Tempo)

**ID:** _observability.07
**Status:** planned
**Prerequisites:** [_observability.04, _infra.14]
**Unblocks:** [_observability.08, _plugins.10, analytics.19, api.19, ingestion.17]
**Estimated size:** M

**As a** developer,
**I need** `make dev` to optionally bring up Prometheus, Grafana, and Jaeger (or Tempo) plus an OTLP collector,
**so that** I can validate metrics and traces locally before pushing — and so the production manifests in `_infra.md` mirror the same shape.

### Current State
- `grep -rn "prometheus\|grafana\|jaeger\|tempo\|otlp" docker-compose.dev.yaml infra/` returns nothing — none of these services exist in compose or `infra/k8s/`.
- `/metrics` is live (backend/api/middleware/metrics.py:99-102) but unscraped.
- `setup_tracing` honors `OTEL_EXPORTER_OTLP_ENDPOINT` (backend/shared/tracing.py:57-69); without a collector the exporter falls back to console output.

### Acceptance Criteria
- [ ] `docker-compose.observability.yaml` (new) defines `prometheus`, `grafana`, `otel-collector`, and `jaeger` services on a shared network with `chili-api` and `chili-worker`.
- [ ] `Makefile` adds `make dev-observability` that runs `docker compose -f docker-compose.dev.yaml -f docker-compose.observability.yaml up --build`.
- [ ] `infra/observability/prometheus.yml` (new) scrapes `chili-api:8000/metrics` and `chili-worker:9090/metrics` every 15s.
- [ ] `infra/observability/otel-collector-config.yaml` (new) accepts OTLP gRPC on 4317 and forwards traces to Jaeger.
- [ ] `.env.example` adds `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` (commented out for default dev).
- [ ] `backend/README.md` and root `README.md` document `make dev-observability` and the service URLs (Prometheus :9090, Grafana :3000, Jaeger :16686).

### Verification
- `make dev-observability` boots cleanly; `docker compose ps` shows all four observability services healthy.
- `curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].health'` returns `"up"` for the chili-api and chili-worker targets.
- A sample RAG query triggers a trace visible in Jaeger UI (`http://localhost:16686`).
- Coverage gate: not applicable (compose/config files).

### Code touch points
- `docker-compose.observability.yaml` (new)
- `Makefile` (modify)
- `infra/observability/prometheus.yml` (new)
- `infra/observability/otel-collector-config.yaml` (new)
- `infra/observability/grafana/datasources.yaml` (new)
- `.env.example` (modify)
- `backend/README.md` (modify)
- `README.md` (modify)


## Story _observability.08: Ship default Grafana dashboards and Prometheus alert rules

**ID:** _observability.08
**Status:** planned
**Prerequisites:** [_observability.04, _observability.05, _observability.07, _cicd.06]
**Unblocks:** [api.23, frontend.09, frontend.17, ingestion.19, ingestion.25, monitoring.08, storage.13]
**Estimated size:** L

**As an** SRE,
**I need** version-controlled Grafana dashboards and Prometheus alert rules that visualize and alert on pipeline throughput, DLQ rate, alert generation, graph-query latency, and HTTP error rate,
**so that** operators have a curated default view (not just raw metrics) and CI gates dashboard changes.

### Current State
- `infra/` contains no `*.json` dashboards and no `*.rules.yml` files; nothing exists yet.
- The DLQ-rate alert is the primary integrity signal called out in `docs/security_checklist.md:151` but has no Prometheus rule.
- Commit `a0a2a38` documented the DLQ ACK contract (`run_handler_with_retry`); the alert rule needs to fire when DLQ throughput exceeds threshold.

### Acceptance Criteria
- [ ] `infra/observability/grafana/dashboards/api.json` (new) covers `http_requests_total` rate, `http_request_duration_seconds` p50/p95/p99, and status-code breakdown.
- [ ] `infra/observability/grafana/dashboards/pipeline.json` (new) covers `pipeline_events_processed_total` rate by event type, `pipeline_stage_duration_seconds` p95 per stage, `pipeline_errors_total` rate, and DLQ size from the Redis exporter.
- [ ] `infra/observability/grafana/dashboards/alerts.json` (new) covers `alerts_generated_total` rate by `entity_type` and `severity`, plus `active_alerts_total` gauge.
- [ ] `infra/observability/grafana/dashboards/adapters.json` (new) covers `graph_query_duration_seconds`, `llm_call_duration_seconds`, `vectorstore_call_duration_seconds`, `embeddings_call_duration_seconds` p95 by adapter.
- [ ] `infra/observability/prometheus/rules/chili-alerts.yml` (new) defines at minimum: `HighAPI5xxRate`, `DLQGrowing`, `PipelineStageSlow`, `GraphQueryLatencyHigh`, `WorkerDown`.
- [ ] `scripts/validate_dashboards.py` (new) parses every dashboard JSON and asserts each panel queries only metrics that exist (counter/histogram/gauge name appears in `_observability.04`/`_observability.05` declarations).
- [ ] `.github/workflows/ci.yml` runs `scripts/validate_dashboards.py` and `promtool check rules infra/observability/prometheus/rules/*.yml` on every PR touching `infra/observability/`.

### Verification
- `python scripts/validate_dashboards.py` exits 0.
- `promtool check rules infra/observability/prometheus/rules/chili-alerts.yml` exits 0.
- Load each dashboard JSON into the dev-stack Grafana (from _observability.07) and confirm every panel renders with live data after exercising the system.
- CI: the new workflow steps run green on a sample PR.

### Code touch points
- `infra/observability/grafana/dashboards/api.json` (new)
- `infra/observability/grafana/dashboards/pipeline.json` (new)
- `infra/observability/grafana/dashboards/alerts.json` (new)
- `infra/observability/grafana/dashboards/adapters.json` (new)
- `infra/observability/prometheus/rules/chili-alerts.yml` (new)
- `scripts/validate_dashboards.py` (new)
- `.github/workflows/ci.yml` (modify)


## Story _observability.09: Split `/health` from `/ready` and add deep readiness probes

**ID:** _observability.09
**Status:** planned
**Prerequisites:** [database.02, graph.03, vectorstore.02, events.02]
**Unblocks:** [frontend.17]
**Estimated size:** M

**As a** Kubernetes operator,
**I need** the API's `/health` to remain a cheap liveness signal and a new `/ready` endpoint to probe every required dependency (Postgres, Neo4j, Qdrant, Redis Streams) before reporting Ready,
**so that** a single failed backing store removes the pod from the service endpoints without killing the process.

### Current State
- `backend/api/app.py:137-139` returns a hard-coded `{"status": "ok"}` for `/health` — no dependency checks.
- Worker health server at `backend/agent/health.py:60-70` tracks only the timestamp of the last processed event (`backend/agent/health.py:48-57`); a stuck stream looks healthy until `degraded_after_seconds` elapses.
- `infra/k8s/chili-api-deployment.yaml:45-58` points both `livenessProbe` and `readinessProbe` at `/health`, so a degraded Neo4j/Redis/Qdrant is invisible to the orchestrator (architecture §10.4 mentions K8s HPA requires accurate readiness signals).
- This story consumes the `check_health()` protocols added in the prerequisite stories (`database.02`, `graph.03`, `vectorstore.02`, `events.02`).

### Acceptance Criteria
- [ ] `backend/api/routers/health.py` (new) exposes:
  - `GET /health` → 200 with `{"status": "ok"}` (liveness, no dependency calls).
  - `GET /ready` → 200 when every registered dependency reports healthy; 503 with `{"status": "degraded", "dependencies": {...}}` otherwise.
- [ ] A `HealthRegistry` service in `backend/api/health/registry.py` (new) lets each adapter register a `check_health() -> HealthStatus` coroutine; `create_app()` wires Postgres, Neo4j, Qdrant, and Redis Streams checks.
- [ ] `backend/agent/health.py` adds a parallel `/ready` route that probes Redis Streams consumer-group health and DB connectivity (in addition to the existing event-staleness check at `agent/health.py:48-57`).
- [ ] `infra/k8s/chili-api-deployment.yaml` `readinessProbe.httpGet.path` flips from `/health` to `/ready`; liveness stays on `/health`. Same change in `infra/k8s/chili-worker-deployment.yaml`.
- [ ] `backend/tests/api/routers/test_health.py` covers all-healthy, one-unhealthy, and timeout cases; same for the worker counterpart.

### Verification
- `pytest backend/tests/api/routers/test_health.py backend/tests/agent/test_health_ready.py -v` passes.
- Boot the dev stack, stop Neo4j (`docker compose stop neo4j`), and confirm `curl -i http://localhost:8000/ready` returns 503 with Neo4j flagged while `/health` still returns 200.
- Apply the updated K8s manifests in a kind cluster, kill the Postgres pod, and confirm `kubectl get pods` shows `chili-api` as `0/1 Ready` within one probe period but not restarted.
- Coverage gate: ≥ 85% on `backend/api/health/` and `backend/agent/health.py`.

### Code touch points
- `backend/api/routers/health.py` (new)
- `backend/api/health/registry.py` (new)
- `backend/api/app.py` (modify)
- `backend/agent/health.py` (modify)
- `infra/k8s/chili-api-deployment.yaml` (modify)
- `infra/k8s/chili-worker-deployment.yaml` (modify)
- `backend/tests/api/routers/test_health.py` (new)
- `backend/tests/agent/test_health_ready.py` (new)


## Story _observability.10: Add a structured audit-log subsystem

**ID:** _observability.10
**Status:** planned
**Prerequisites:** [_observability.01, _observability.02, _security.05, database.05]
**Unblocks:** [storage.09]
**Estimated size:** L

**As a** compliance officer,
**I need** every analyst action (graph query, alert acknowledgement, config change, KB delete, RAG query) to write an immutable audit-log row tagged with the authenticated principal, tenant, correlation ID, target resource, and outcome,
**so that** the platform satisfies the architecture §14.2 "Audit log" capability and the outstanding `docs/security_checklist.md` A09 item.

### Current State
- `grep -rn "audit_log\|AuditLog\|audit-log" backend/` returns no first-party matches — nothing exists.
- The architecture lists Audit log as Medium-priority future capability (docs/architecture.md:1359).
- This story resolves the auditor's open question on persistence substrate by choosing **Postgres** (a dedicated `audit_log` table via `database.05`); event-stream and SIEM forwarding are out of scope here (future _security story).
- Identity capture depends on `_security.05` (RBAC user-identity in request context).

### Acceptance Criteria
- [ ] `backend/audit/` (new module) exposes `AuditEvent` Pydantic model with fields `id`, `occurred_at`, `actor_id`, `actor_role`, `tenant_id`, `correlation_id`, `action`, `resource_type`, `resource_id`, `outcome` (`success`|`failure`), `metadata` (jsonb), and `AuditLogServiceProtocol`/`PostgresAuditLogService` implementation.
- [ ] An Alembic migration adds the `audit_log` table with the columns above plus indexes on `(occurred_at)`, `(actor_id)`, `(tenant_id, occurred_at)`.
- [ ] FastAPI dependency `audit(action, resource_type)` records the event after a successful handler; on exception, an error-path hook records `outcome="failure"` with the exception class.
- [ ] Mutating routes write audit entries: graph queries (`/graph/query`), alert acks (`/alerts/{id}/ack`), config changes (`/config/*`), KB create/delete (`/knowledgebases/*`), RAG queries (`/rag/query`).
- [ ] `GET /audit?actor_id=&from=&to=&resource_type=` returns paginated entries (admin-only).
- [ ] `backend/tests/audit/test_service.py` and `backend/tests/api/routers/test_audit.py` cover write, query, RBAC-gating, failure-path recording, and tenant scoping.

### Verification
- `pytest backend/tests/audit/ backend/tests/api/routers/test_audit.py -v` passes.
- Hit a mutating endpoint, then `psql -c "SELECT actor_id, action, outcome FROM audit_log ORDER BY occurred_at DESC LIMIT 5;"` shows the entry.
- Coverage gate: ≥ 85% on `backend/audit/`.

### Code touch points
- `backend/audit/__init__.py` (new)
- `backend/audit/models.py` (new)
- `backend/audit/protocols.py` (new)
- `backend/audit/service.py` (new)
- `backend/audit/adapters/postgres.py` (new)
- `backend/audit/dependency.py` (new)
- `backend/api/routers/audit.py` (new)
- `backend/database/migrations/versions/<rev>_audit_log.py` (new)
- `backend/api/routers/graph.py` (modify)
- `backend/api/routers/alerts.py` (modify)
- `backend/api/routers/config.py` (modify)
- `backend/api/routers/knowledgebases.py` (modify)
- `backend/api/routers/rag.py` (modify)
- `backend/tests/audit/test_service.py` (new)
- `backend/tests/api/routers/test_audit.py` (new)


## Story _observability.11: Integrate frontend error tracking and Web Vitals

**ID:** _observability.11
**Status:** planned
**Prerequisites:** [_observability.02, frontend.26]
**Unblocks:** []
**Estimated size:** M

**As a** frontend on-call,
**I need** unhandled SPA errors, React error boundaries, and Web Vitals (LCP, FID, CLS, INP, TTFB) reported to a hosted error/RUM backend with release tagging and source-map symbolication,
**so that** production user-facing failures surface without depending on user-reported screenshots, and so we satisfy architecture §11.4 and §13.
- This story resolves the auditor's vendor-choice open question by selecting **Sentry** (industry-standard, OTel-compatible, OSS SDK); an `_infra` follow-up may swap to self-hosted GlitchTip without API changes.

### Current State
- `chili_app/` has no Sentry/Datadog dependency — `grep -rn "Sentry\|sentry" chili_app/src/` returns no matches.
- The only failure handler is `chili_app/src/components/common/ErrorBoundary.tsx:24` (`componentDidCatch`), which just calls `console.error('ErrorBoundary caught:', error, info)`.
- Architecture §11.4 calls for Sentry or equivalent (docs/architecture.md:1262); §13 lists it as the production-hardening front-end stack.
- The X-Request-Id from `_observability.02` will be attached to Sentry events as a tag so backend and frontend errors correlate.

### Acceptance Criteria
- [ ] `chili_app/package.json` adds `@sentry/react` and `@sentry/vite-plugin` dependencies.
- [ ] `chili_app/src/observability/sentry.ts` (new) initializes Sentry with `dsn` from `VITE_SENTRY_DSN`, `release` from `VITE_APP_VERSION`, `environment` from `VITE_APP_ENV`, and the Browser Tracing + Web Vitals integrations.
- [ ] `chili_app/src/main.tsx` calls `initSentry()` before `createRoot(...)`.
- [ ] `chili_app/src/components/common/ErrorBoundary.tsx` reports caught errors via `Sentry.captureException` in addition to the existing `console.error`.
- [ ] `chili_app/src/api/client.ts` (or equivalent) attaches the response `X-Request-Id` to Sentry breadcrumbs/tags for cross-correlation.
- [ ] `vite.config.ts` registers `@sentry/vite-plugin` for production builds to upload source maps tagged with the release.
- [ ] When `VITE_SENTRY_DSN` is unset (local dev), `initSentry()` is a no-op and the SPA continues working.
- [ ] `chili_app/src/observability/__tests__/sentry.test.ts` covers the no-op path and the captureException path under Vitest.
- [ ] `chili_app/README.md` documents the env vars and the local "DSN unset = no-op" contract.

### Verification
- `cd chili_app && npm run test:run -- observability/sentry` passes.
- `npm run build` with `VITE_SENTRY_DSN` set produces a build that uploads source maps (verified by plugin output).
- E2E: trigger a deliberate render error via Playwright (e.g. a debug-only `/throw` route) and confirm the captured event appears in Sentry's UI (or the mock transport in tests) with the `X-Request-Id` tag.
- Frontend lint clean: `npm run lint`.

### Code touch points
- `chili_app/package.json` (modify)
- `chili_app/src/observability/sentry.ts` (new)
- `chili_app/src/main.tsx` (modify)
- `chili_app/src/components/common/ErrorBoundary.tsx` (modify)
- `chili_app/src/api/client.ts` (modify)
- `chili_app/vite.config.ts` (modify)
- `chili_app/.env.example` (modify)
- `chili_app/src/observability/__tests__/sentry.test.ts` (new)
- `chili_app/README.md` (modify)


## Story _observability.12: Make tracing and metrics tenant- and KB-aware

**ID:** _observability.12
**Status:** planned
**Prerequisites:** [_observability.04, _observability.06, _multitenancy.03]
**Unblocks:** []
**Estimated size:** M

**As a** multi-tenant operator,
**I need** every metric and span tagged with `tenant_id` and (where meaningful) `kb_id`,
**so that** dashboards, alerts, and traces match the access-control boundary defined by architecture §12.3 and the KB scoping in §7 — without leaking one tenant's data into another's view.

### Current State
- Existing metric labels are `["method", "path", "status"]` (backend/api/middleware/metrics.py:32) and `["stage"]` (backend/monitoring/metrics.py:28) — neither carries tenant or KB attribution.
- `start_pipeline_span` attributes (backend/shared/tracing.py:103-128) include only `correlation_id` and caller-supplied extras.
- This story consumes the `TenantContext` plumbing added by `_multitenancy.03` (tenant id available in request- and event-scoped contextvars).
- KB id is already known at most call sites via `kb_id` parameter or `shared.kb_scope`.

### Acceptance Criteria
- [ ] `backend/api/middleware/metrics.py` adds `tenant_id` to `http_requests_total` and `http_request_duration_seconds` labels; cardinality is bounded by a configurable `metrics.max_tenants` cap (default 1000) with overflow bucketed as `tenant_id="_other_"`.
- [ ] `backend/monitoring/metrics.py` `pipeline_*` metrics gain `tenant_id` and (where applicable) `kb_id` labels.
- [ ] `backend/{graph,vectorstore,embeddings,llm}/metrics.py` (from _observability.05) gain `tenant_id` and `kb_id` labels with the same cardinality cap.
- [ ] `start_pipeline_span` attaches `tenant.id` and `kb.id` span attributes automatically from the active `TenantContext` and `KbContext`.
- [ ] `alerts_generated_total` and `knowledgebase_documents_total` (from _observability.04) gain `tenant_id` labels.
- [ ] Tests under `backend/tests/observability/test_tenant_labels.py` assert the labels are present and the overflow bucket activates above the cap.
- [ ] `docs/architecture.md` §11.2 list updated to note tenant/KB labels (and `_observability.13` conventions doc reflects the cap policy).

### Verification
- `pytest backend/tests/observability/test_tenant_labels.py -v` passes.
- Boot dev stack with two seeded tenants, issue requests under each, then `curl /metrics | grep tenant_id` shows distinct label values.
- Force-create > `metrics.max_tenants` synthetic tenants in a test and assert the `_other_` bucket increments.
- Coverage gate: ≥ 85% on the touched metrics modules.

### Code touch points
- `backend/api/middleware/metrics.py` (modify)
- `backend/monitoring/metrics.py` (modify)
- `backend/graph/metrics.py` (modify)
- `backend/vectorstore/metrics.py` (modify)
- `backend/embeddings/metrics.py` (modify)
- `backend/llm/metrics.py` (modify)
- `backend/shared/tracing.py` (modify)
- `backend/knowledgebases/metrics.py` (modify)
- `docs/architecture.md` (modify)
- `backend/tests/observability/test_tenant_labels.py` (new)


## Story _observability.13: Document and enforce a logging-and-metrics conventions guide

**ID:** _observability.13
**Status:** planned
**Prerequisites:** [_observability.01, _observability.04]
**Unblocks:** []
**Estimated size:** S

**As a** new contributor,
**I need** a single page that codifies log-level usage, structured field names, metric naming, label conventions, and the cardinality cap policy — with a linter that catches drift,
**so that** the cross-module rollout from _observability.01/04 does not erode over time and the architecture §11.1 INFO/WARNING/ERROR rule is actually enforceable.

### Current State
- `docs/onboarding.md` has no log-level or metric-naming guidance.
- The arch §11.1 levels rule (INFO request lifecycle / WARNING degraded / ERROR failures) lives only in `docs/architecture.md:1239`; no developer-facing checklist references it.
- No linter exists that blocks adding stdlib `logging.getLogger` or unbounded metric label cardinality.

### Acceptance Criteria
- [ ] `docs/observability_conventions.md` (new) covers:
  - Mandatory log fields (`correlation_id`, `tenant_id`, `kb_id` where relevant, `event=` snake_case verb).
  - Level usage rules (per arch §11.1) with concrete examples.
  - Metric naming (`<module>_<noun>_<unit>` for histograms, `<module>_<noun>_total` for counters).
  - Required labels and the `_other_` overflow bucket policy from _observability.12.
  - When to add a span attribute vs. a metric label.
- [ ] `scripts/lint_observability.py` (new) enforces:
  - No `logging.getLogger(` in first-party `backend/` code.
  - Every Prometheus metric declaration includes a docstring and uses the naming convention above.
  - Histogram metrics use `*_seconds` suffix and Counter metrics use `*_total` suffix.
- [ ] `.github/workflows/ci.yml` runs `python scripts/lint_observability.py` on every backend PR.
- [ ] `CLAUDE.md` and `.github/copilot-instructions.md` link to `docs/observability_conventions.md` as the single source of truth.
- [ ] `docs/onboarding.md` links to the conventions doc in its "Observability" section.

### Verification
- `python scripts/lint_observability.py` exits 0 on the current tree (after _observability.01 lands) and exits non-zero when a stdlib `getLogger` or a malformed metric name is introduced (verified by a deliberately broken fixture test).
- `pytest backend/tests/scripts/test_lint_observability.py -v` passes.
- A reviewer reading `docs/observability_conventions.md` can derive the same logger and metric shape every other module uses.

### Code touch points
- `docs/observability_conventions.md` (new)
- `scripts/lint_observability.py` (new)
- `.github/workflows/ci.yml` (modify)
- `CLAUDE.md` (modify)
- `.github/copilot-instructions.md` (modify)
- `docs/onboarding.md` (modify)
- `backend/tests/scripts/test_lint_observability.py` (new)
