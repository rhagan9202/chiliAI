# Agent Module

`agent/` is the workflow coordinator for the chiliAI pipeline worker. It consumes events from Redis Streams, runs multi-step pipeline handlers, tracks workflow lifecycle state, and routes failures to a dead-letter queue.

## Worker Entry Point

```bash
python -m agent.coordinator   # starts the Redis Streams consumer loop
```

The coordinator registers one handler per event type and dispatches to it inside a retry/DLQ wrapper. Workflow state is written through `WorkflowRunStoreProtocol` so API and worker containers share lifecycle updates when `CHILI_WORKFLOW_RUN_STORE_BACKEND=redis`.

## Pipeline Handlers

### handle_documents_uploaded

Triggered by `documents.uploaded`. Runs the ingestion pipeline: parse → chunk → extract (LLM or pattern) → upsert graph → embed → index vector store → publish `entities.extracted` / `kb.ready`.

### handle_records_ingested

Triggered by `RecordsIngestedEvent`. Maps raw records to `Entity`/`Relationship` objects and upserts them into the graph via `GraphService.upsert_records_graph`. Also embeds and indexes records-derived entities into the vector store so they are retrievable by RAG queries alongside document-derived content.

### handle_knowledge_base_deleted (retry handler)

Triggered by `kb.delete`. Executes the full KB-delete cascade with retry semantics:

1. Graph namespace cleanup — `GraphService.delete_knowledge_base(kb_id)`
2. Vector namespace cleanup — `VectorService.delete_knowledge_base(kb_id)`
3. Raw-records cleanup — `RawRecordStore.delete_by_kb(kb_id)`
4. Object-store payload cleanup — iterates and deletes all stored artifacts under the KB prefix

Each step is idempotent so the handler is safe to retry on transient failures. If a workflow run is active for the KB at delete time, the API returns a 409 and the handler is not dispatched until the active run completes.

### Plan C Persistence Handlers

- **handle_graph_updated_for_analytics** (Flow 2) — Persists graph-scope metrics to `entity_metric_history` / `entity_metrics_current`, throttled per KB.
- **handle_risk_scored_for_graph** (Flow 3) — Writes risk assessments to `risk_score_history` and snapshots scores onto graph entities.
- **handle_alerts_created_for_graph** (Flow 4) — Writes alerts to `alert_history` and snapshots alert counts onto graph entities.

## WorkflowRunStore

The `WorkflowRunStoreProtocol` is implemented by `InMemoryWorkflowRunStore` (tests/local) and `RedisWorkflowRunStore` (dev/prod stack). Select via `CHILI_WORKFLOW_RUN_STORE_BACKEND=in_memory|redis`.

See [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the end-to-end demo context.
