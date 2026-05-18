# chiliAI Backend

Python 3.12 backend for the chiliAI platform — a domain-reconfigurable Graph RAG analytics system.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Backend module details: [`docs/architecture.md` §5](../docs/architecture.md#5-backend-module-decomposition).

## Current State

Working FastAPI gateway and pipeline-worker prototype with domain configuration, event-driven orchestration, ingestion, graph/vector/embedding/LLM/RAG service boundaries, analytics modules, monitoring, storage adapters, config-driven adapter selection, auth/RBAC middleware, route-level policy enforcement, live KB metadata projection, API-owned alert projection, service-backed workflow summaries, worker-updated workflow lifecycle tracking, repository-backed SSE KB/active-alert/workflow status, graph namespace cleanup, and extensive pytest coverage. Initial production-facing adapters now exist for Neo4j, Qdrant, OpenAI, Anthropic, sentence-transformers, S3-compatible storage, and Redis-backed shared workflow state; remaining production work is mainly tenant/resource-level authorization, observability, audit-grade workflow history, production-grade projection metadata persistence, vector/document provenance cleanup, and live adapter deployment profiles.

### What's functional

- **`shared/`** — Generic platform types (`Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`), config-definition types (`EntityDefinition`, `PropertyDefinition`, `PropertyType`, `RelationshipDefinition`), protocols (`Configurable`), and utilities. **No hardcoded domain-specific types** — all domain entities use `Entity(type, properties)` validated against config.
- **`config/`** — Domain configuration schema (`DomainConfig` Pydantic model with cross-field validation), YAML/JSON loader, and two default configs (`medicare_fraud.yaml`, `food_supply_chain.yaml`).
- **`api/app.py`** — FastAPI app factory with `/health`, CORS, metrics instrumentation, and all API routers.
- **`api/routers/config.py`** — `GET /config/domain` returns the active domain configuration as JSON.
- **`api/dependencies.py`** — Dependency injection wiring. `get_domain_config()` loads config once and process-caches (cleared at the top of `create_app()` for test isolation). `get_api_state()` reads from `request.app.state.api_state`, attached per-app in `create_app()`. Graph, vectorstore, storage, embedding, and LLM adapters are selected from config with lazy optional imports.
- **`api/routers/`** — Knowledge base, alert, investigation, chat (rag), analytics, config, policy, cases, evidence, graph, workflows, events (SSE), auth, WebSocket, and records routers. Every Phase 5+ route carries `Depends(require_role(...))` (reads = viewer, writes = analyst); `policy_registry.assert_complete` runs on app startup when auth is enabled and refuses to boot if any route is unguarded. Records routes: `POST /records/{knowledge_base_id}/files` (CSV/JSONL file upload) and `POST /records/{knowledge_base_id}/push` (JSON api-push).
- **`api/_kb_store.py` / `api/_kb_projection.py`** — API-owned KB/document metadata projection. The in-memory repository remains available for tests and isolated local runs; the object-store repository persists dev KB/document metadata across API reloads through the configured `ObjectStore`. Projection reads merge repository metadata with live graph metrics/object-store build artifacts and persist status/count changes back through the repository.
- **`api/_alert_store.py`** — API-owned alert read projection for `/alerts` and SSE `active_alerts`. Monitoring/analytics services still own alert generation; this projection preserves the frontend contract while decoupling alert reads from legacy seeded `ApiState`.
- **`api/_workflow_projection.py`** — API DTO projection for workflow summaries. The `agent/` module owns workflow state behind `WorkflowRunStoreProtocol`; `/workflows` and SSE `running_workflows` read through `AgentServiceProtocol` instead of legacy seeded `ApiState`. The dev stack uses the Redis workflow store so API and worker share lifecycle updates.
- **`api/routers/events.py`** — SSE workspace heartbeat for alert/workflow/KB status deltas. The heartbeat reads cached API-owned projections only; live graph/object-store reconciliation stays on explicit KB list/detail reads so idle browser tabs do not poll Neo4j every five seconds.
- **`events/`** — In-memory and Redis Streams event bus implementations plus typed event envelopes.
- **`ingestion/`** — Parser orchestration, document chunking, extraction, validation, and registration flows.
- **`graph/`, `vectorstore/`, `embeddings/`, `llm/`, `rag/`** — Service/protocol boundaries with in-memory adapters and selected production-facing adapters.
- **`analytics/` and `monitoring/`** — Heuristic timeseries, GNN, risk, explainability, alert, and monitoring services.
- **`analytics/README.md`** — Contributor guide for turning Postgres-backed scripts and notebook algorithms into typed analytics services, adapters, tests, and API/worker wiring.
- **`analytics/metrics/`** — Entity-metric persistence package (no service layer, no events). `EntityMetricRepository` protocol backed by `InMemoryEntityMetricRepository` (tests/local) or `PostgresEntityMetricRepository` (Postgres). `MetricsRecomputeThrottle` limits per-KB recompute rate. Graph-scope metrics use sentinel `entity_id = "__graph__"`.
- **`storage/`** — In-memory, local filesystem, and S3-compatible object-store adapters.
- **`database/`** — Postgres + TimescaleDB connection provider, `DatabaseConfig`-driven backend selection, and Alembic-managed schema (six persistence tables). Infrastructure only — no domain logic.
- **`records/`** — structured/tabular ingestion (CSV/JSONL/api-push). Validates rows against config-declared feed schemas, lands canonical rows in `raw_records`, and publishes `RecordsIngestedEvent`. Parallel to `ingestion/` for documents.
- **`api/middleware/`** — Metrics, auth, and RBAC middleware with route-level policy enforcement and auth-enabled startup audit.
- **`agent/coordinator.py`** — Worker entry point (`python -m agent.coordinator`) for Redis-stream processing, workflow lifecycle tracking, retry/DLQ routing, graceful shutdown, and a lightweight health endpoint. Implements persistence-layer worker flows:
  - **Flow 2** (`handle_graph_updated_for_analytics`) — On `GraphUpdatedEvent`, computes graph metrics (entity count, relationship count, avg degree) and persists them to `entity_metric_history` / `entity_metrics_current`, throttled per knowledge-base by `MetricsRecomputeThrottle`.
  - **Flow 3** (`handle_risk_scored_for_graph`) — On `RiskScoredEvent`, writes risk assessments to `risk_score_history` and snapshots `risk_score` / `risk_level` / `risk_assessed_at` onto graph entities.
  - **Flow 4** (`handle_alerts_created_for_graph`) — On `AlertsCreatedEvent`, writes alerts to `alert_history` and snapshots `active_alert_count` / `last_alert_at` / `last_alert_severity` onto graph entities.
- **`main.py`** — Uvicorn launcher for local development.
- **`Dockerfile`** — Multi-stage build producing a production-ready image.

## Target Module Structure

```
backend/
├── api/             # FastAPI gateway — routing, validation, DI wiring (no business logic)
├── ingestion/       # Document parsing (PDF, DOCX, HTML, JSON, TXT), chunking, entity extraction
├── graph/           # Abstract graph repository protocol + adapters (in-memory, Neo4j)
├── vectorstore/     # Abstract vector store protocol + adapters (in-memory, Qdrant)
├── embeddings/      # Abstract embedder protocol + adapters (OpenAI, sentence-transformers)
├── rag/             # RAG pipeline — query → embed → search → graph expand → LLM → answer
├── llm/             # Abstract LLM client protocol + adapters (in-memory, OpenAI, Anthropic)
├── analytics/
│   ├── timeseries/  # Time-series anomaly detection
│   ├── gnn/         # GNN link prediction, clustering
│   ├── risk/        # Risk scoring engine
│   ├── explainability/  # Evidence pack generation, subgraph extraction
│   └── metrics/     # Entity-metric persistence (entity_metric_history / entity_metrics_current)
├── agent/           # Workflow coordinator — async state machine for multi-step pipelines
├── monitoring/      # Active monitoring — claim stream consumer, alert generation
├── shared/          # Domain types, protocols, utilities (dependency-light, no business logic)
├── config/          # Domain configuration loader (YAML/JSON)
├── events/          # Event bus abstraction + Redis Streams adapter
├── storage/         # Object/file storage abstraction + adapters (S3, MinIO, local FS)
├── database/        # Postgres + TimescaleDB connection provider, Alembic migrations
└── records/         # structured/tabular ingestion (CSV/JSONL/api-push), raw_records landing
```

## Cross-Module Interaction Rules

Modules interact **only** through:

1. **FastAPI gateway orchestration** — API router → service modules (frontend-initiated)
2. **Agent / workflow coordinator** — event-driven pipelines via Redis Streams
3. **Shared contracts library** (`shared/`) — domain types and protocols

Ad hoc cross-module imports, hidden shared state, and direct implementation coupling are forbidden.

## Development Commands

```bash
# Install (editable, with dev extras when available)
pip install -e ".[dev]"

# API server
CHILI_ENV=local uvicorn api.app:create_app --factory --reload --port 8000

# Pipeline worker
python -m agent.coordinator

# Tests
pytest --cov

# Type checking (currently scoped in pyproject.toml while strict coverage expands)
pyright
```

> These commands target the architecture described in `docs/architecture.md`. The codebase is under active hardening; keep Ruff, Pyright, and pytest clean for touched packages.

## Quality Requirements

- **Type checking**: All code must pass `pyright --strict`. Full annotations, no untyped `Any`, explicit domain types.
- **Test coverage**: ≥ 85% for each backend package. Missing tests = incomplete work.
- **Interface-first**: Every external system (graph DB, vector store, LLM, object store) behind an abstract protocol in `<module>/protocols.py` with concrete adapters in `<module>/adapters/`.

## Configuration

The backend reads a domain configuration YAML/JSON file at startup (path set via `CHILI_CONFIG_PATH` environment variable). This configuration defines entity types, relationships, enabled capabilities, and alert thresholds. See [`docs/architecture.md` §9](../docs/architecture.md#9-domain-configuration-model).

### Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `CHILI_CONFIG_PATH` | (required at runtime) | Path to the active domain config YAML/JSON. |
| `CHILI_ENV` | (required) | Runtime mode: `local`, `dev`, `staging`, or `production`. Startup fails on unset/unknown values. `staging` and `production` require `auth.enabled=True` plus a complete `AuthConfig`; `local` and `dev` permit auth-disabled development. |
| `ALLOWED_ORIGINS` | local dev defaults (`http://localhost:5173`, `:80`, `localhost`) | Comma-separated CORS allow-list for the frontend. Required when the SPA is deployed under a different origin. |
| `CHILI_KB_REPOSITORY_BACKEND` | `in_memory` | Knowledge base metadata repository. Use `object_store` in the dev stack to persist KB/document metadata through API reloads via the configured object store. |
| `CHILI_ALERT_REPOSITORY_BACKEND` | `in_memory` | Alert projection repository. Use `object_store` in the dev stack to persist alert read projections and SSE active-alert counts through API reloads via the configured object store. |
| `CHILI_WORKFLOW_RUN_STORE_BACKEND` | `in_memory` | Workflow run store used by `AgentServiceProtocol` for `/workflows` and SSE `running_workflows`. Supported values: `in_memory`, `redis`. Use `redis` in the dev stack so API and worker share workflow lifecycle state. |
| `OIDC_CLIENT_SECRET` | unset | OIDC client secret read by name from `auth.client_secret_env_var`. |
| `REDIS_URL` | unset | Required for the Redis Streams event bus, `CHILI_WORKFLOW_RUN_STORE_BACKEND=redis`, and the production session store when auth is enabled. |
| `CHILI_EVENT_BUS_BACKEND` | `in_memory` | `in_memory` or `redis`. |
| `CHILI_EVENT_BLOCK_MS` | `500` in dev compose | Redis Streams blocking read timeout in milliseconds. Higher local-dev values reduce idle worker wakeups without changing event semantics. |
| `LOG_LEVEL` | `INFO` | Stdlib/structlog log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, or a numeric level). |
| `LOG_FORMAT` | `console` | `console` for local readable logs, `json` for structured aggregation. |
| `DATABASE_URL` | unset | Postgres/TimescaleDB DSN. Required when `DatabaseConfig.backend=postgres` and to run Alembic migrations. |
| `NEO4J_USER` | `neo4j` | Neo4j username used when `GraphDbConfig.backend=neo4j` and `auth_env_var` is not set. Matches the Compose `NEO4J_AUTH=${NEO4J_USER}/${NEO4J_PASSWORD}` setting. |
| `NEO4J_PASSWORD` | unset | Neo4j password used with `NEO4J_USER` when `GraphDbConfig.backend=neo4j` and `auth_env_var` is not set. Leave unset only when the Neo4j service is started with `NEO4J_AUTH=none`. |
| `NEO4J_AUTH` or configured `GraphDbConfig.auth_env_var` | unset | Optional explicit Neo4j credential env. Accepts `username:password`, Docker-style `username/password`, password-only values (defaults username to `neo4j`), or `none` for anonymous local Neo4j. |

### Optional `analytics` config section

The domain configuration YAML/JSON accepts an optional `analytics` section (type `AnalyticsConfig`):

```yaml
analytics:
  metrics_recompute_min_interval_seconds: 300  # default 300 s
```

`metrics_recompute_min_interval_seconds` sets the minimum wall-clock interval between metric recomputes for a given knowledge base (Flow 2). The throttle is applied per-KB in the worker; bursts of `GraphUpdatedEvent`s do not trigger redundant recomputes within the window.

### Setting the config path

```bash
# Environment variable (preferred in containers)
export CHILI_CONFIG_PATH=/app/config/defaults/medicare_fraud.yaml

# Or pass explicitly in code
from config.loader import load_config
cfg = load_config("config/defaults/medicare_fraud.yaml")
```

### Available default configs

| File | Domain |
|------|--------|
| `config/defaults/medicare_fraud.yaml` | Medicare fraud detection (4 entities, 4 relationships, all capabilities) |
| `config/defaults/medicare_fraud_dev.yaml` | Medicare fraud variant wired for the dev Compose stack (Neo4j graph, Redis event bus, object-store KB/alert repos, Redis workflow run store) |
| `config/defaults/food_supply_chain.yaml` | Food supply chain monitoring (4 entities, 3 relationships, partial capabilities) |

### Creating a new domain

1. Copy an existing default and modify entity types, relationships, and thresholds.
2. Set `CHILI_CONFIG_PATH` to the new file.
3. Restart the backend. The frontend picks up the new config via `GET /config/domain`.

## Knowledge Base Projection Notes

- KB and document metadata are owned by the FastAPI gateway behind `KnowledgeBaseRepository`.
- Graph entities, relationships, and graph metrics remain owned by `graph/` behind `GraphServiceProtocol` and `GraphRepository` adapters.
- `GET /knowledgebases`, `GET /knowledgebases/{id}`, `GET /knowledgebases/{id}/documents`, and `GET /events/stream` use the same live projection helpers so visible status/counts stay aligned.
- `DELETE /knowledgebases/{id}` deletes object-store payloads, clears the graph namespace through `GraphServiceProtocol.delete_knowledge_base()`, deletes KB metadata, and publishes `kb.delete`.
- The `object_store` KB repository is intended for local/dev single-writer durability. Add a dedicated production metadata adapter, optional dependency, and migration story before treating it as a high-concurrency production database.

## Ingestion Registration Notes

- Document registration is idempotent per knowledge base for repeated content bytes and repeated remote URIs. The ingestion service derives deterministic source document IDs from content SHA-256 hashes or URI hashes and does not publish duplicate `documents.uploaded` events when the source has already been registered.
- Content uploads are stored under the deterministic source document ID; remote URI submissions write a small marker object for deduplication while preserving the original URI on the event/receipt.

## Alert Projection Notes

- Alert read models are owned by the FastAPI gateway behind `AlertProjectionRepository`; `/alerts` no longer reads from legacy seeded `ApiState`.
- `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, and SSE `active_alerts` use the same projection store so feed state and realtime counts stay aligned.
- The `object_store` alert repository is intended for local/dev single-writer durability. A production alert metadata adapter should implement the same protocol when alert projection writes become concurrent or tenant-scoped.

## Workflow Projection Notes

- Workflow state is owned by `agent/` behind `WorkflowRunStoreProtocol` and surfaced to API routes through `AgentServiceProtocol`.
- `GET /workflows` and SSE `running_workflows` are service-backed and no longer read workflow summaries from legacy seeded `ApiState`. `GET /workflows` accepts `knowledge_base_id`, `status`, `limit`, and `offset` query parameters for scoped timeline views.
- Workflow runs now track `queued`, `running`, `completed`, `failed`, and `cancelled` states with `updated_at` timestamps. The worker coordinator updates stage progress, preserves correlation IDs across document parsing events, marks document parse failures terminal, and tracks structured-record ingestion as a KB-scoped workflow.
- The in-memory workflow store remains available for local/test usage with detached returned models, idempotency-key uniqueness checks, and lock-protected shared indexes.
- The Redis workflow store is intended for shared operational state between API and worker containers. For compliance-grade immutable workflow history, add a Postgres/audit adapter or outbox/event-sourcing layer behind the same protocol.

## Analytics Runtime Notes

- GNN analysis is controlled by the domain `capabilities.gnn` flag. When the capability is disabled, the worker skips GNN Flow B without emitting `analysis.failed`.
- Fresh knowledge bases may not have a registered graph snapshot yet. Missing snapshots are treated as a controlled skip, not a failed analytics stage, so document/vector Flow A remains quiet and successful while GNN waits for a configured snapshot source.
