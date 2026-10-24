# api

The **FastAPI gateway** — the entry point for every frontend-initiated request
and the first of the three permitted cross-module paths (see
[docs/architecture.md](../../docs/architecture.md)). Routers hold no business
logic: they resolve services through dependency injection in
`dependencies.py`, call them, and project results into the response models in
`contracts.py` (or a module's own `service_models.py`). The full route list,
with roles, is in [docs/ledger/http-routes.md](../../docs/ledger/http-routes.md).

Run it with the factory flag: `uvicorn api.app:create_app --factory --reload --port 8000`.

## Layout

| File | Responsibility |
|------|----------------|
| `app.py` | `create_app()` — configures logging/tracing, resets config caches, boot-validates the active pack (`enforce_production_guardrail`, `config.deployment.require_shared_state_stores`), adds CORS, builds `app.state.api_state`, registers `/metrics` and `GET /health`, includes all routers, then runs the default-deny audit. A lifespan hooks SIGTERM/SIGINT so `/events/stream` responses end before uvicorn drains connections. |
| `dependencies.py` | DI providers (`get_*`, mostly `@lru_cache` singletons derived from the active `DomainConfig`), backend selection for every adapter, `load_chili_environment`, `enforce_production_guardrail`, `build_api_state`, and `reset_domain_config_caches` (clears every entry in `CONFIG_CACHE_REGISTRY` on a domain hot-swap). |
| `contracts.py` | Frontend-facing Pydantic response/request models. |
| `config_models.py` | DTOs for the admin pack-management routes in `routers/config.py`. |
| `state.py` | `ApiState` — after the BL-012 de-seed it only carries the RAG service handle. |
| `middleware/auth.py` | `get_current_user`, `User`; resolves the caller from the `chiliai_session` cookie, an `Authorization: Bearer` JWT checked against the OIDC JWKS, or an anonymous user when auth is disabled. |
| `middleware/rbac.py` | `ROLE_HIERARCHY` (`viewer` 1, `analyst` 2, `service` 2, `admin` 3), `require_role`, `is_role_sufficient`. With auth disabled every role check passes. |
| `middleware/policy_registry.py` | `assert_complete(app)` — raises `PolicyMissingError` at startup if any route outside `/auth/`, `/health`, `/docs`, `/openapi.json`, `/redoc` lacks a `require_role` dependency. |
| `middleware/session_store.py` | `SessionStoreProtocol` with in-memory and Redis adapters for the BFF session cookie. |
| `middleware/metrics.py` | `register_metrics` — Prometheus HTTP middleware and `GET /metrics` (role `service`). |
| `_rag_bridges.py` | `ServiceQueryEmbedder`, `ServiceContextRetriever`, `ServiceGraphContextExpander`, `ServiceAnswerGenerator` — adapt the embeddings, vectorstore, graph and LLM services to the [rag/](../rag/README.md) ports. |
| `_analytics_overview.py`, `_graph_entity_payload.py`, `_housing_read_model.py`, `_conversation_payloads.py`, `_workflow_projection.py`, `_kb_projection.py` | Read-model projections composed from several modules' durable stores. |
| `_kb_cleanup.py` | `get_kb_deletion_stores` — assembles the KB-delete cascade store bundle from DI. |
| `_kb_busy.py` | `ensure_kb_idle` / `KbBusyError` — refuse KB mutations while a workflow is in flight. |

## Routers

| Router file | Prefix | Surface |
|-------------|--------|---------|
| `config.py` | `/config` | Domain config, feature gates, config JSON schema; admin pack list / validate / apply / switch. |
| `knowledgebases.py` | `/knowledgebases` | KB CRUD, document upload / list / preview / delete, feature catalog and per-entity features. |
| `records.py` | `/records` | `POST /records/{knowledge_base_id}/files` structured-record upload ([records/](../records/README.md)). |
| `events.py` | `/events` | `GET /events/stream` (SSE workspace snapshots); dead-letter queue list / detail / replay / discard. |
| `alerts.py` | `/alerts` | List, detail, acknowledge, assignment, status, bulk status. |
| `cases.py` | `/cases` | Case CRUD, promote, attach alert, feedback, dossier and dossier export ([cases/](../cases/README.md)). |
| `evidence.py` | `/evidence-packs`, `/knowledgebases/{id}/evidence-packs` | Evidence pack detail, provenance, reviews, export. |
| `graph.py` | `/graph` | `GET /graph/entities/{entity_id}`. |
| `investigation.py` | `/investigation` | Entity detail, locate, neighborhood, search. |
| `rag.py` | `/chat` | Conversations; `POST …/messages` (`?stream=true` for SSE). |
| `analytics.py` | `/analytics` | Risk scores and projections, peer analysis, timeseries, GNN clusters, overview. |
| `identity.py` | `/identity` | Canonical identity, resolve candidates, link decisions. |
| `policy.py` | `/policy` | Policy items and triage ([policy/](../policy/README.md)). |
| `workflows.py` | `/workflows` | Pipeline run list / detail / cancel; step approve / reject. |
| `scorecards.py` | `/scorecards` | Templates, runs, run export. |
| `housing.py` | `/housing` | Housing dashboard overview and installations. |
| `audit.py` | `/audit` | `GET /audit/events`, `GET /audit/status`. |
| `auth.py` | `/auth` | BFF OIDC login / callback / logout / me (uses `_oidc_client.py`). |
| `score_runs.py` | `/knowledgebases/{id}/score-runs` | Create, list, detail, cancel, replay. |
| `capabilities.py` | `/knowledgebases/{id}/capabilities` | Capability registry listing. |
| `workflow_definitions.py` | `/knowledgebases/{id}/workflow-definitions` | Definition CRUD; version approve / retire / run. |
| `playbooks.py` | `/knowledgebases/{id}/playbooks` | List, version detail, publish, export, import. |
| `governance.py` | `/knowledgebases/{id}/governance` | Release report; eval runs create / list / approve / reject. |
| `connectors.py` | `/knowledgebases/{id}/connectors` | Connector list / create; sync runs; quarantine. |
| `readiness.py` | `/knowledgebases/{id}/readiness` | KB readiness report. |
| `dev_seed.py` | `/admin/dev-seed` | Deterministic e2e seed scenario; registered only when `CHILI_ENV` is not `production`. |

## Contracts and invariants

- **Default deny.** Every route declares `Depends(require_role(...))`;
  `assert_complete` fails app startup otherwise.
- **Generated frontend contracts.** The OpenAPI document is the source of truth
  for `chili_app/src/api/contracts.ts`. After changing a frontend-consumed
  model, run `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`
  from the repo root, then `npm run codegen:api` in `chili_app/`.
- **Production guardrail.** Under `CHILI_ENV=staging|production`,
  `enforce_production_guardrail` refuses a pack whose `auth` section is absent,
  disabled, or missing required OIDC fields — at boot and before a hot-swap.
- **Shared state.** With a Redis event bus, `require_shared_state_stores`
  refuses a pack that keeps database, graph or vector state in process memory.
- **Cross-module composition** (bridges, projections) lives here rather than in
  feature modules.

## Environment variables

`CHILI_ENV`, `ALLOWED_ORIGINS` (comma-separated CORS origins; defaults to
localhost dev origins), `REDIS_URL` (required for the session store when auth
is enabled), `CHILI_DEV_ANONYMOUS_ROLE` (elevates the anonymous user outside
production), `CHILI_KB_REPOSITORY_BACKEND`. Config selection (`CHILI_CONFIG_PATH`,
the active-pack pointer) is described in [config/README.md](../config/README.md).

## Persistence

None of its own; every store is reached through DI from its owning module.

## Tests

`tests/api/` — router, DI, middleware and app-factory tests
(e.g. `test_app.py`, `test_dependency_swap.py`, `test_config_routes.py`).
