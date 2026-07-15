# Agent Module

`agent/` is the workflow coordinator for the chiliAI pipeline worker. It consumes events from Redis Streams, runs multi-step pipeline handlers, tracks workflow lifecycle state, and routes failures to a dead-letter queue.

## Worker Entry Point

```bash
python -m agent.coordinator   # starts the Redis Streams consumer loop
```

The coordinator registers one handler per event type and dispatches to it inside a retry/DLQ wrapper. Workflow state is written through `WorkflowRunStoreProtocol` so API and worker containers share lifecycle updates when `CHILI_WORKFLOW_RUN_STORE_BACKEND=redis`.

## Health & metrics endpoint

The worker starts a lightweight async HTTP server (`agent/health.py::start_health_server`) alongside the Redis Streams consumer loop, serving `GET /health` (JSON liveness/progress payload) on port `8001` by default (`agent.models.HealthSettings`). The health server also serves `GET /metrics` (Prometheus text exposition of the default `prometheus_client` registry) on the same port. Worker-side counters — `pipeline_stage_duration_seconds`, `pipeline_errors_total` (`monitoring/metrics.py`), `ingestion_documents_failed_total`, `ingestion_documents_empty_extraction_total` (`shared/metrics.py`) — are scraped here, not from the API gateway's `/metrics`: each process exposes only its own registry (no cross-process aggregation). Like `/health`, the endpoint is unauthenticated; the dev compose publishes it on host port `8001` so operators can scrape it directly (`curl :8001/metrics`).

## Domain hot-swap convergence (`config.updated`)

The worker builds all of its config-derived dependencies into a single
`WorkerDependencies` bundle (`build_worker_dependencies`), resolving the active
domain pack the same way the API does (active-pack pointer > `CHILI_CONFIG_PATH`
— see `backend/config/README.md`). When an admin hot-swaps the domain via
`POST /config/apply|switch`, the API publishes a `ConfigUpdatedEvent`
(`config.updated`); the worker consumes it **between drain iterations**
(`apply_pending_config_updates`), so a rebuild never interleaves with in-flight
event handling. Redelivery is idempotent — `ConfigReloadState` tracks the last
applied delivery so the same event never triggers a second rebuild.

Constraint: the reload signal travels on the pre-swap event transport and the
worker keeps consuming the stream it subscribed to, so a pack must **not**
change the `events` backend/URI across a hot-swap (transport changes require a
restart). See `docs/architecture.md` §9.3.

## Pipeline Handlers

### Document status projection (BL-041)

Every dispatch of `documents.uploaded` / `documents.parsed` / `documents.failed` /
`documents.extraction_warning` also runs `agent.status_projection.project_document_status`
at the top of `_dispatch_event`, inside the same retry/DLQ wrapper as the pipeline
stage itself — so a projection failure is retried/dead-lettered exactly like any
other handler failure. It writes a monotonic `DocumentStatusTransition` (via
`WorkerDependencies.document_status_store: ingestion.adapters.protocols.SourceDocumentStatusStore`)
so replayed/redelivered events are no-ops rather than regressing status.
`documents.extraction_warning` is projection-only (mapped onto `VALIDATED` or
`EXTRACTED_EMPTY`) and short-circuits `_dispatch_event` with no further pipeline
stage. `build_document_status_store` selects `PostgresSourceDocumentStatusStore`
when a database is configured, else `InMemorySourceDocumentStatusStore`
(`ingestion/adapters/`).

### handle_documents_uploaded

Triggered by `documents.uploaded`. Runs the ingestion pipeline: parse → chunk → extract (LLM or pattern) → upsert graph → embed → index vector store → publish `entities.extracted` / `kb.ready`.

### Per-document failure isolation (BL-041, extended BL-017)

Each pipeline stage handler (`handle_documents_parsed`, `handle_documents_chunked`,
`handle_entities_extracted`, `handle_entities_validated`) iterates its batch and
isolates only the **permanent** failure classes for that stage to a single
document — publishing a `DocumentsFailedEvent` for it — instead of raising and
poisoning the whole batch for the retry/DLQ wrapper. Any other exception (a
transient object-store or database error) still propagates so
`run_handler_with_retry`'s retry/DLQ policy applies to the full batch.

`handle_entities_validated` (the graph stage) isolates a `GraphIntegrityError`
chained inside `GraphService.upsert_task`'s `BatchUpsertError` — the
document's relationships reference endpoints absent from the graph
(`graph.01`, `GraphUpsertOptions.integrity_mode="strict"` by default). The
handler introspects `BatchUpsertError.__cause__`: when it is a
`GraphIntegrityError`, the document fails in isolation with
`missing_entity_ids` / `relationship_ids` folded into the
`DocumentFailureReference.error_message`, `ingestion_documents_failed_total{stage="graph",
error_class="GraphIntegrityError"}` increments, and sibling documents in the
same `entities.validated` batch still upsert and advance to `graph.updated`.
Any other `BatchUpsertError` cause (e.g. a transient Neo4j error) re-raises
and the whole batch retries.

### handle_records_ingested

Triggered by `RecordsIngestedEvent`. Maps raw records to `Entity`/`Relationship`
objects and upserts them into the graph via `GraphService.upsert_records_graph`.
Also embeds and indexes records-derived entities into the vector store so they
are retrievable by RAG queries alongside document-derived content. When wired,
the handler then runs best-effort policy-rule evaluation over stored entities
and throttled graph metrics, and a best-effort peerstats stage that can persist
derived risk signals and reassess affected entities.

### handle_knowledge_base_deleted (retry handler)

Triggered by `kb.delete`. Executes the full KB-delete cascade with retry
semantics. The step list is centralized in `knowledgebases.cleanup` and purges
graph, vector, raw records, derived signals, risk history, observations, alert
history, metrics, conversations, cases, policy items, evidence, and object-store
payloads before deleting KB metadata.

Each step is idempotent so the handler is safe to retry on transient failures.
If a workflow run is active for the KB at delete time, the API returns a 409 and
the handler is not dispatched until the active run completes.

### Plan C Persistence Handlers

- **handle_graph_updated_for_analytics** (Flow 2) — Persists graph-scope metrics to `entity_metric_history` / `entity_metrics_current`, throttled per KB.
- **handle_risk_scored_for_graph** (Flow 3) — Writes risk assessments to `risk_score_history` and snapshots scores onto graph entities.
- **handle_alerts_created_for_graph** (Flow 4) — Writes alerts to `alert_history` and snapshots alert counts onto graph entities.

## Workflow submission & lifecycle

Workflow runs are created **intentionally** by `AgentService.start_workflow`, wired into the two pipeline entry points in the API gateway:

- **`POST /knowledgebases/{kb}/documents`** → starts a `documents.uploaded` run (full canonical step plan).
- **`POST /records/{kb}/files` and `/push`** → starts a `records.ingested` run (single `records_ingest` step) when records were actually ingested (duplicate/empty submissions start no run).

The API passes the run's `correlation_id` into the published pipeline event, so the worker's `WorkflowEventTracker` advances *that* run. `start_workflow` is **create-or-get keyed by correlation id**: if the worker won the race and `WorkflowEventTracker` already minted a fallback run, the service adopts it instead of creating a duplicate. The fallback path is retained as a safety net (events with an unknown correlation id still surface). Step plans come from one source of truth: `agent.workflow_tracking.default_steps_for_trigger`.

Because a run is created synchronously at submit, the KB is **busy** (`ensure_kb_idle`) for the duration of the run — one ingestion workflow per KB at a time. A second mutation while a run is non-terminal returns `409`; the duplicate-resubmission no-op (`200`) holds once the KB is idle.

**Cross-cutting prerequisite:** API and worker must share the run store (`CHILI_WORKFLOW_RUN_STORE_BACKEND=redis`) for submission and tracking to converge. With the in-memory backend the two are distinct.

### Cancellation

`POST /workflows/{id}/cancel` (analyst role) marks a non-terminal run `CANCELLED`; `GET /workflows/{id}` returns a single run; `GET /workflows` lists them (viewer role). Cancellation is **cooperative**:

- The tracker honours it at each event boundary (`begin_event` skips a cancelled run's remaining steps). A **`FAILED`** run does *not* gate processing: a per-document `documents.failed` event marks the run failed while sibling documents in the same batch are still in flight, and their successor events keep processing with the run record frozen at `FAILED` (BL-041 failure isolation). Only `CANCELLED` (user intent) and `COMPLETED` (replay safety) skip.
- Long handlers (`handle_graph_updated_for_analytics`, `handle_records_ingested`) re-check `WorkflowEventTracker.is_run_cancelled` at loop/stage boundaries and stop early — a single in-flight synchronous stage still finishes.
- Tracker writes use a status-only compare-and-set (`update_run_if_current` with `expected_statuses={QUEUED, RUNNING}`), so a concurrent cancel is never clobbered back to `RUNNING`/`COMPLETED`.

## WorkflowRunStore

The `WorkflowRunStoreProtocol` is implemented by `InMemoryWorkflowRunStore` (tests/local) and `RedisWorkflowRunStore` (dev/prod stack). Select via `CHILI_WORKFLOW_RUN_STORE_BACKEND=in_memory|redis`. The store maintains a `correlation_id → workflow_id` index (`find_by_correlation_id`) so the tracker and `start_workflow` resolve runs without a full scan.

See [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the end-to-end demo context.
