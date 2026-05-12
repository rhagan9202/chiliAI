# chiliAI Backend

Python 3.12 backend for the chiliAI platform — a domain-reconfigurable Graph RAG analytics system.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Backend module details: [`docs/architecture.md` §5](../docs/architecture.md#5-backend-module-decomposition).

## Current State

Working FastAPI gateway and pipeline-worker prototype with domain configuration, event-driven orchestration, ingestion, graph/vector/embedding/LLM/RAG service boundaries, analytics modules, monitoring, storage adapters, config-driven adapter selection, auth/RBAC middleware, route-level policy enforcement, live KB metadata projection, API-owned alert projection, service-backed workflow summaries, repository-backed SSE KB/active-alert/workflow status, graph namespace cleanup, and extensive pytest coverage. Initial production-facing adapters now exist for Neo4j, Qdrant, OpenAI, Anthropic, sentence-transformers, and S3-compatible storage; remaining production work is mainly tenant/resource-level authorization, observability, durable workflow recovery, production-grade projection metadata persistence, vector/document provenance cleanup, and live adapter deployment profiles.

### What's functional

- **`shared/`** — Generic platform types (`Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`), config-definition types (`EntityDefinition`, `PropertyDefinition`, `PropertyType`, `RelationshipDefinition`), protocols (`Configurable`), and utilities. **No hardcoded domain-specific types** — all domain entities use `Entity(type, properties)` validated against config.
- **`config/`** — Domain configuration schema (`DomainConfig` Pydantic model with cross-field validation), YAML/JSON loader, and two default configs (`medicare_fraud.yaml`, `food_supply_chain.yaml`).
- **`api/app.py`** — FastAPI app factory with `/health`, CORS, metrics instrumentation, and all API routers.
- **`api/routers/config.py`** — `GET /config/domain` returns the active domain configuration as JSON.
- **`api/dependencies.py`** — Dependency injection wiring. `get_domain_config()` loads config once and process-caches (cleared at the top of `create_app()` for test isolation). `get_api_state()` reads from `request.app.state.api_state`, attached per-app in `create_app()`. Graph, vectorstore, storage, embedding, and LLM adapters are selected from config with lazy optional imports.
- **`api/routers/`** — Knowledge base, alert, investigation, chat (rag), analytics, config, policy, cases, evidence, graph, workflows, events (SSE), auth, and WebSocket routers. Every Phase 5+ route carries `Depends(require_role(...))` (reads = viewer, writes = analyst); `policy_registry.assert_complete` runs on app startup when auth is enabled and refuses to boot if any route is unguarded.
- **`api/_kb_store.py` / `api/_kb_projection.py`** — API-owned KB/document metadata projection. The in-memory repository remains available for tests and isolated local runs; the object-store repository persists dev KB/document metadata across API reloads through the configured `ObjectStore`. Projection reads merge repository metadata with live graph metrics/object-store build artifacts and persist status/count changes back through the repository.
- **`api/_alert_store.py`** — API-owned alert read projection for `/alerts` and SSE `active_alerts`. Monitoring/analytics services still own alert generation; this projection preserves the frontend contract while decoupling alert reads from legacy seeded `ApiState`.
- **`api/_workflow_projection.py`** — API DTO projection for workflow summaries. The `agent/` module owns workflow state behind `WorkflowRunStoreProtocol`; `/workflows` and SSE `running_workflows` read through `AgentServiceProtocol` instead of legacy seeded `ApiState`.
- **`events/`** — In-memory and Redis Streams event bus implementations plus typed event envelopes.
- **`ingestion/`** — Parser orchestration, document chunking, extraction, validation, and registration flows.
- **`graph/`, `vectorstore/`, `embeddings/`, `llm/`, `rag/`** — Service/protocol boundaries with in-memory adapters and selected production-facing adapters.
- **`analytics/` and `monitoring/`** — Heuristic timeseries, GNN, risk, explainability, alert, and monitoring services.
- **`storage/`** — In-memory, local filesystem, and S3-compatible object-store adapters.
- **`api/middleware/`** — Metrics, auth, and RBAC middleware with route-level policy enforcement and auth-enabled startup audit.
- **`agent/coordinator.py`** — Worker entry point (`python -m agent.coordinator`) for Redis-stream processing, Flow A/Flow B handlers, retry/DLQ routing, graceful shutdown, and a lightweight health endpoint.
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
│   └── explainability/  # Evidence pack generation, subgraph extraction
├── agent/           # Workflow coordinator — async state machine for multi-step pipelines
├── monitoring/      # Active monitoring — claim stream consumer, alert generation
├── shared/          # Domain types, protocols, utilities (dependency-light, no business logic)
├── config/          # Domain configuration loader (YAML/JSON)
├── events/          # Event bus abstraction + Redis Streams adapter
└── storage/         # Object/file storage abstraction + adapters (S3, MinIO, local FS)
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
uvicorn api.app:create_app --reload --port 8000

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
| `CHILI_ENV` | unset | When set to `production`, `create_app()` enforces `auth.enabled=True` plus a complete `AuthConfig`. |
| `ALLOWED_ORIGINS` | local dev defaults (`http://localhost:5173`, `:80`, `localhost`) | Comma-separated CORS allow-list for the frontend. Required when the SPA is deployed under a different origin. |
| `CHILI_KB_REPOSITORY_BACKEND` | `in_memory` | Knowledge base metadata repository. Use `object_store` in the dev stack to persist KB/document metadata through API reloads via the configured object store. |
| `CHILI_ALERT_REPOSITORY_BACKEND` | `in_memory` | Alert projection repository. Use `object_store` in the dev stack to persist alert read projections and SSE active-alert counts through API reloads via the configured object store. |
| `CHILI_WORKFLOW_RUN_STORE_BACKEND` | `in_memory` | Workflow run store used by `AgentServiceProtocol` for `/workflows` and SSE `running_workflows`. Durable adapters are planned behind `WorkflowRunStoreProtocol`. |
| `OIDC_CLIENT_SECRET` | unset | OIDC client secret read by name from `auth.client_secret_env_var`. |
| `REDIS_URL` | unset | Required for the Redis Streams event bus and the production session store when auth is enabled. |
| `CHILI_EVENT_BUS_BACKEND` | `in_memory` | `in_memory` or `redis`. |

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

## Alert Projection Notes

- Alert read models are owned by the FastAPI gateway behind `AlertProjectionRepository`; `/alerts` no longer reads from legacy seeded `ApiState`.
- `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, and SSE `active_alerts` use the same projection store so feed state and realtime counts stay aligned.
- The `object_store` alert repository is intended for local/dev single-writer durability. A production alert metadata adapter should implement the same protocol when alert projection writes become concurrent or tenant-scoped.

## Workflow Projection Notes

- Workflow state is owned by `agent/` behind `WorkflowRunStoreProtocol` and surfaced to API routes through `AgentServiceProtocol`.
- `GET /workflows` and SSE `running_workflows` are service-backed and no longer read workflow summaries from legacy seeded `ApiState`.
- The current in-memory workflow store is hardened for local/test usage with detached returned models, idempotency-key uniqueness checks, and lock-protected shared indexes. Add a durable Postgres or Redis adapter behind the same protocol before relying on workflow recovery across API/worker restarts.
