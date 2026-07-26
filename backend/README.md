# chiliAI Backend

Python 3.12 backend for the chiliAI platform — a domain-reconfigurable Graph RAG analytics system.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Backend module details: [`docs/architecture.md` §5](../docs/architecture.md#5-backend-module-decomposition).

## Current State

Working FastAPI gateway and pipeline-worker prototype with domain configuration, event-driven orchestration, ingestion, graph/vector/embedding/LLM/RAG service boundaries, analytics modules, monitoring, storage adapters, config-driven adapter selection, auth/RBAC middleware, route-level policy enforcement, live KB metadata projection, a durable alert feed read model over `alert_history` (alerts.36), service-backed workflow summaries, worker-updated workflow lifecycle tracking, repository-backed SSE KB/active-alert/workflow status, graph namespace cleanup, a durable per-document ingestion status projection with per-document coordinator failure isolation (BL-041), a durable/replayable event dead-letter ledger with an operator API surface (BL-023), and extensive pytest coverage. Initial production-facing adapters now exist for Neo4j, Qdrant, OpenAI, Anthropic, sentence-transformers, S3-compatible storage, and Redis-backed shared workflow state; remaining production work is mainly tenant/resource-level authorization, observability, audit-grade workflow history, production-grade projection metadata persistence, vector/document provenance cleanup, and live adapter deployment profiles.

For the live, dependency-ordered list of production-readiness work per backend module, see [`../docs/backlog/README.md`](../docs/backlog/README.md) and the per-module files (`../docs/backlog/agent.md`, `../docs/backlog/graph.md`, `../docs/backlog/ingestion.md`, etc.).

### What's functional

- **`shared/`** — Generic platform types (`Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`), config-definition types (`EntityDefinition`, `PropertyDefinition`, `PropertyType`, `RelationshipDefinition`), protocols (`Configurable`), and utilities. **No hardcoded domain-specific types** — all domain entities use `Entity(type, properties)` validated against config. `shared/metrics.py` (BL-043) is the contracts-library home for Prometheus counters incremented from more than one module (`ingestion/service.py` + `agent/coordinator.py` + `records/service.py`), alongside the same-pattern `shared/logging.py` and `shared/tracing.py`.
- **`config/`** — Domain configuration schema (`DomainConfig` Pydantic model with cross-field validation), YAML/JSON loader with base + environment overlay layering (`overlay.py`, `CHILI_CONFIG_OVERLAY_PATH`; see "Config overlays" below and [ADR 0001](../docs/architecture/decisions/0001-config-overlay-merge-semantics.md)), the file-backed active-pack pointer store (`store.py`: pointer > `CHILI_CONFIG_PATH` resolution, atomic writes to `data/config/active_pack.json`), default domain packs (`medicare_fraud.yaml`, `medicare_fraud_cms_desynpuf.yaml`, `food_supply_chain.yaml`, `department_air_force_housing.yaml`), and the `overlays/` directory (`medicare_fraud_dev.yaml`). See [`config/README.md`](config/README.md) for the pack-authoring contract and domain-switch ergonomics.
- **`api/app.py`** — FastAPI app factory with `/health`, CORS, metrics instrumentation, and all API routers.
- **`api/routers/config.py`** — Viewer-gated reads (`GET /config/domain|features|domain/schema`) plus admin-gated pack management: `GET /config/packs` (discovery + active-pack state) and `POST /config/validate|apply|switch` (dry-run validation; no-restart domain hot-swap via the swap-once-success pipeline — validate + production auth guardrail → persist pointer → atomic DI cache reset → publish `ConfigUpdatedEvent`). Pack references are confined to allow-listed config directories. See [`docs/architecture.md` §9.3](../docs/architecture.md#93-active-pack-hot-swap-no-restart-domain-switch).
- **`api/dependencies.py`** — Dependency injection wiring. `get_domain_config()` resolves the active pack (pointer > env) and process-caches; `reset_domain_config_caches()` clears it plus every config-keyed factory cache and bumps a monotonic swap-generation token (`get_config_generation`) with generation-guarded memoizers, so hot-swaps are atomic (a request sees a wholly-old or wholly-new dependency graph). `enforce_production_guardrail()` (applied at boot and to every hot-swap candidate) refuses auth-disabled or incomplete-OIDC configs under `CHILI_ENV=staging|production`. `get_api_state()` reads from `request.app.state.api_state`, attached per-app in `create_app()`. Graph, vectorstore, storage, embedding, and LLM adapters are selected from config with lazy optional imports.
- **`api/routers/`** — Knowledge base, alert, investigation, chat (rag), analytics, config, policy, cases, evidence, graph, workflows, events (SSE), auth, WebSocket, and records routers. Every Phase 5+ route carries `Depends(require_role(...))` (reads = viewer, writes = analyst); `policy_registry.assert_complete` runs on app startup when auth is enabled and refuses to boot if any route is unguarded. Records routes: `POST /records/{knowledge_base_id}/files` (CSV/JSONL file upload) and `POST /records/{knowledge_base_id}/push` (JSON api-push).
- **`api/_kb_projection.py`** — API-owned KB/document metadata projection. The in-memory repository remains available for tests and isolated local runs; the object-store repository persists dev KB/document metadata across API reloads through the configured `ObjectStore`. Projection reads merge repository metadata with live graph metrics/object-store build artifacts and persist status/count changes back through the repository.
- **Alert feed** — `/alerts`, acknowledge, SSE `active_alerts`, and the alert-related fields on `/analytics/overview` and `GET /graph/entities/{id}` all read the durable `alert_history` table through `monitoring.adapters.protocols.AlertFeedStoreProtocol` (`api.dependencies.get_alert_feed_store`) — no separate API-owned projection file (`api/_alert_store.py` was deleted, alerts.36). See "Alert Feed Notes (alerts.36)" below.
- **`api/_workflow_projection.py`** — API DTO projection for workflow summaries. The `agent/` module owns workflow state behind `WorkflowRunStoreProtocol`; `/workflows` and SSE `running_workflows` read through `AgentServiceProtocol` instead of legacy seeded `ApiState`. The dev stack uses the Redis workflow store so API and worker share lifecycle updates.
- **`api/routers/events.py`** — SSE workspace heartbeat for alert/workflow/KB status deltas. The heartbeat reads cached API-owned projections only; live graph/object-store reconciliation stays on explicit KB list/detail reads so idle browser tabs do not poll Neo4j every five seconds. Also hosts the `/events/dlq` operator surface (BL-023): `GET /events/dlq` (paginated, filterable by `status`/`event_type`, analyst-gated, returns full `DlqRecord`s including `error_traceback` — no separate summary shape) and `GET /events/dlq/{dlq_id}` (analyst-gated, 404 unknown), plus admin-gated `POST /events/dlq/{dlq_id}/replay` (decodes the stored payload via `events.codec.decode_event`, re-publishes it through `get_event_bus()`, then `mark_replayed`; 404 unknown, 409 non-pending, 422 when the payload no longer decodes — record stays `pending`) and `POST /events/dlq/{dlq_id}/discard` (`mark_discarded`; 404/409). `api.dependencies.get_dlq_record_store()` mirrors `get_document_status_store` — Postgres-backed when a database is configured, else in-memory.
- **`events/`** — In-memory and Redis Streams event bus implementations plus typed event envelopes. `dlq_models.py` defines the durable `DlqRecord`/`DlqRecordListResponse`/`DlqRecordStatus` types; `protocols.DlqRecordStore` plus its `adapters/dlq_in_memory.py` and `adapters/dlq_postgres.py` implementations back both the worker-side persistence (see `agent/README.md` § Durable DLQ record persistence) and the API operator surface above. See [`events/README.md`](events/README.md) for the module design and [`docs/runbooks/event-replay.md`](../docs/runbooks/event-replay.md) for the operator playbook.
- **`ingestion/`** — Parser orchestration, document chunking, extraction, validation, and registration flows.
- **`graph/`, `vectorstore/`, `embeddings/`, `llm/`, `rag/`** — Service/protocol boundaries with in-memory adapters and selected production-facing adapters.
- **`analytics/` and `monitoring/`** — Heuristic timeseries, GNN, risk, explainability, alert, and monitoring services.
- **`analytics/peerstats/`** — Config-driven cross-sectional peer-group z-score analytics. Aggregates `raw_records` JSONB per entity/interval, z-scores each entity against its peer cohort, and upserts `DerivedRiskSignal` rows to the `entity_derived_signals` table. Gated on `capabilities.peer_stats`. `PostgresRiskSignalSource` (in `analytics/risk`) reads those signals so the risk service incorporates them without change to the risk module. See [`analytics/peerstats/README.md`](analytics/peerstats/README.md).
- **`analytics/README.md`** — Contributor guide for turning Postgres-backed scripts and notebook algorithms into typed analytics services, adapters, tests, and API/worker wiring.
- **`analytics/metrics/`** — Entity-metric persistence package (no service layer, no events). `EntityMetricRepository` protocol backed by `InMemoryEntityMetricRepository` (tests/local) or `PostgresEntityMetricRepository` (Postgres). `MetricsRecomputeThrottle` limits per-KB recompute rate. Graph-scope metrics use sentinel `entity_id = "__graph__"`.
- **`storage/`** — In-memory, local filesystem, and S3-compatible object-store adapters.
- **`database/`** — Postgres + TimescaleDB connection provider, `DatabaseConfig`-driven backend selection, and Alembic-managed schema (fifteen persistence tables across migrations `0001`-`0012`, including the durable per-document ingestion status projection `source_document_status`, the durable DLQ ledger `event_dlq` (BL-023), the persisted self-history anomaly ledger `timeseries_anomalies` (migration `0011`, BL-047), and read-model columns `entity_label`/`confidence`/`tags` added to `alert_history` (migration `0012`, alerts.36)). Both alert producers now populate real values on the `AlertCreatedReference` event before Flow 4 maps them onto the row: the analytics pipeline's `_run_explainability_stage` sets `confidence` from the risk assessment's `overall_score` and `tags` from the top risk-factor names (kebab-cased); `entity_label` falls back to `entity_id` (no cheap display value is in scope without an extra graph read). `MonitoringService.evaluate()` sets `confidence` from the alert candidate's threshold-ratio score and `tags` from a kebab-slugged `metric_name`; `entity_label` stays at its `""` default (no display name is available on a monitoring observation). `GET /alerts` and the rest of the alert feed now read `alert_history` directly (alerts.36 — see "Alert Feed Notes" below); the API no longer keeps a separate alert projection. Infrastructure only — no domain logic.
- **`records/`** — structured/tabular ingestion (CSV/JSONL/api-push). Validates rows against config-declared feed schemas, lands canonical rows in `raw_records`, and publishes `RecordsIngestedEvent`. Parallel to `ingestion/` for documents.
- **`cases/`** — durable, KB-scoped investigation case management (BL-010). `Case` model + `CaseRepository` (in-memory + Postgres adapters, `cases` table via migration `0002_cases`) + `CaseService` with `promote_from_alert`. Backs `/cases` CRUD + `POST /cases/promote` (all `?knowledge_base_id=`-scoped). See [`cases/README.md`](cases/README.md).
- **`policy/`** — durable, KB-scoped policy intelligence (BL-011). Rule-pack-driven `PolicyItem` generation + analyst triage (accept/reject/defer/escalate-to-case) with persisted `PolicyDisposition`. `PolicyItemRepository` (in-memory + Postgres adapters, `policy_items` table via migration `0003_policy`). Backs `GET /policy/items`, `GET /policy/items/{id}`, `POST /policy/items/{id}/triage`. Replaces the old seeded policy-gap surface. See [`policy/README.md`](policy/README.md).
- **`conversations/`** — durable RAG chat persistence (BL-012). `Conversation`/`ConversationMessage` models + `ConversationRepository` (in-memory + Postgres adapters, `conversations` table via migration `0005_conversations`) + `ConversationService`. Backs the `/chat/conversations` create/read/append routes; the API layer (`api/_conversation_payloads.py`) adapts these models to the frontend `Chat*` contracts and builds the user/assistant turn from a RAG answer — replacing the in-memory-only seeded `ApiState` conversation store.
- **`scorecards/`** — config-driven statutory scorecard runs (branch `af_housing`). Pure `evaluate_template()` grades `ScorecardTemplateConfig` metrics (bounded operators `ratio`/`sum`/`mean`/`weighted_mean`/`latest`, freshness windows, one-direction thresholds) against `SourceRecord` rows; `ScorecardService.generate()` selects KB records by scope + period, content-hashes the source snapshot, and persists runs through `ScorecardRunRepository` (in-memory + Postgres, `scorecard_runs` table via migration `0008_scorecards`). Feed records reach the module through the `ScorecardSourceRecordLoader` protocol, implemented at the gateway by `RecordFeedSourceLoader` (`api/dependencies.py`) over `RawRecordStore.load_for_kb` — scorecards never imports `records/`. Backs `/scorecards/templates|runs|runs/{id}/export`. Metric provenance for the shipped UH/MFH templates: [`../docs/research/housing-scorecard-mandates.md`](../docs/research/housing-scorecard-mandates.md).
- **`api/_housing_read_model.py` + `api/routers/housing.py`** — `/housing/overview` and `/housing/installations` compute genuine per-installation aggregates from the KB's ingested feed rows (same rows the scorecard evaluator consumes), with statutorily informed `ok`/`watch`/`critical`/`unknown` banding documented on `derive_status`. Installation rows also expose the per-installation aggregate inputs (value/weight pairs, work-order counts, UH/MFH available-vs-authorized units; nullable where unreported) so the frontend can recompute every overview aggregate for any filtered subset — exact-equality router tests pin the formulas. Installations without resolvable coordinates stay in `items` but are excluded from `map_points` (frontend shows a location-pending list). See [`docs/architecture.md` §6.8](../docs/architecture.md#68-housing-scorecards--executive-dashboard-branch-af_housing).
- **`analytics/explainability/`** also owns the **evidence-pack repository** (BL-005): real packs are extracted in the worker (`graph.get_subgraph` + risk factors → `ExplanationContext` → `ExplainabilityService`), persisted to an object-store `EvidencePackRepository`, and served by `GET /evidence-packs/{id}` (KB-scoped) — replacing the seeded `ApiState` evidence read model. `ExplainabilityService` composes two injected, config-selected seams (BL-048, Sprint 2026-28 B3): a `NarrativeGeneratorProtocol` (`DeterministicNarrativeGenerator` default, or `LlmNarrativeGenerator` degrading to it) and a `FeatureAttributorProtocol` (`NoopFeatureAttributor` default, or `ShapRiskAttributor` attributing the linear risk composite) — both never raise, degrading with a WARNING log instead. Persisted packs carry the results as `narrative_sections`/`attribution`, served through `EvidencePackResponse`. See "Analytics Runtime Notes" below and [`analytics/README.md`](analytics/README.md) § Explainability narrative + attribution seams.
- **`api/middleware/`** — Metrics, auth, and RBAC middleware with route-level policy enforcement and auth-enabled startup audit. `GET /metrics` here exposes the API process's own `prometheus_client` registry only — it is a separate registry from the worker's, so a full scrape needs both endpoints. `JwksCache` (`auth.py`) resolves signing keys by `kid`: an unknown `kid` triggers a forced JWKS refetch throttled to once per URI per 30 seconds (BL-022), so an IdP key rotation recovers without a restart or waiting out the TTL. The OIDC login/callback flow (`routers/auth.py` + `routers/_oidc_client.py`) round-trips a `nonce` alongside the PKCE verifier and validates it against the decoded `id_token` (id_token flows only — the access-token fallback path has no nonce claim to check). See [`docs/auth/idp-templates.md`](../docs/auth/idp-templates.md) for worked Keycloak/Okta `AuthConfig` YAML and IdP-side setup steps (desk-checked, not live-verified — see the doc's header).
- **`agent/coordinator.py`** — Worker entry point (`python -m agent.coordinator`) for Redis-stream processing, workflow lifecycle tracking, retry/DLQ routing, graceful shutdown, and a lightweight health endpoint (`agent/health.py`) that also serves `GET /metrics` (port `8001` by default) for the worker's own registry — see `agent/README.md`. Implements persistence-layer worker flows:
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
├── embeddings/      # Embedder protocol + adapters (OpenAI, sentence-transformers), LRU cache, usage metrics
├── rag/             # RAG pipeline — query → embed → search → graph expand → LLM → answer
├── llm/             # Abstract LLM client protocol + adapters (in-memory, OpenAI, Anthropic)
├── analytics/
│   ├── timeseries/  # Time-series anomaly detection
│   ├── gnn/         # GNN link prediction, clustering
│   ├── risk/        # Risk scoring engine
│   ├── explainability/  # Evidence pack generation, subgraph extraction
│   ├── metrics/     # Entity-metric persistence (entity_metric_history / entity_metrics_current)
│   └── peerstats/   # Cross-sectional peer-group z-scores → derived risk signals (entity_derived_signals)
├── agent/           # Workflow coordinator — async state machine for multi-step pipelines
├── monitoring/      # Active monitoring — claim stream consumer, alert generation
├── shared/          # Domain types, protocols, utilities (dependency-light, no business logic)
├── config/          # Domain configuration loader (YAML/JSON)
├── events/          # Event bus abstraction + Redis Streams adapter
├── storage/         # Object/file storage abstraction + adapters (S3, MinIO, local FS)
├── database/        # Postgres + TimescaleDB connection provider, Alembic migrations
├── records/         # structured/tabular ingestion (CSV/JSONL/api-push), raw_records landing
├── knowledgebases/  # KB/document metadata repository adapters (in-memory, object-store)
├── conversations/   # durable RAG chat conversations (in-memory, Postgres)
├── cases/           # durable, KB-scoped investigation cases (promote-from-alert)
├── policy/          # durable, KB-scoped policy intelligence (rule-pack items + triage)
└── scorecards/      # config-driven scorecard evaluation + durable runs (in-memory, Postgres)
```

`backend/tools/` is distinct from the repo-root `tools/` package (host-side demo/data-prep scripts driven over HTTP, see `tools/__init__.py`) — both share the bare name `tools` but are typechecked by *separate* pyright invocations (`backend/pyproject.toml`'s `[tool.pyright]` vs. `tools/pyrightconfig.json`; see either file's comment for why one process can't resolve both).

## Cross-Module Interaction Rules

Modules interact **only** through:

1. **FastAPI gateway orchestration** — API router → service modules (frontend-initiated)
2. **Agent / workflow coordinator** — event-driven pipelines via Redis Streams
3. **Shared contracts library** (`shared/`) — domain types and protocols

Ad hoc cross-module imports, hidden shared state, and direct implementation coupling are forbidden.

## Development Commands

```bash
# Install (uv manages the venv; editable, with dev extras when available)
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"

# API server
CHILI_ENV=local uvicorn api.app:create_app --factory --reload --port 8000

# Pipeline worker
python -m agent.coordinator

# Tests (integration + e2e tests run against the live stack — bring it up first)
make dev          # from repo root: start Postgres/Neo4j/Qdrant/Redis/MinIO
pytest --cov      # @pytest.mark.integration tests target the running stack

# Type checking (currently scoped in pyproject.toml while strict coverage expands)
pyright

# Export backend OpenAPI for frontend contract codegen (from repo root)
cd .. && PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json

# Demo: Tennessee Medicare subset (requires `make dev` stack running first)
make demo-tn-subset                                         # build TN subset + create KB + upload
python -m tools.sample_data.build_tennessee_subset --help  # subset builder options

# Demo: full CMS fraud bring-up (BL-051) — pack switch + subset + ingest + readiness probes
make demo-cms                                               # scripts/demo_cms.sh; requires `make dev` running first

# Demo: Air Force housing dashboard (stack must run the housing pack)
make dev-domain DOMAIN=department_air_force_housing        # start stack with the housing pack
make seed-housing                                          # create KB + upload 6 feed fixtures via real HTTP
make seed-housing SEED_ARGS="--scorecards"                 # ...and generate scorecard runs per template
# then open http://localhost:5173/housing
# Reseeding creates a fresh KB each run; the housing endpoints aggregate the
# newest KB of the active domain. Against a bare uvicorn (no worker) pass
# SEED_ARGS="--no-worker".
# The housing pack pins the dev-stack services like the other shipped packs
# (Postgres records/scorecard runs, object-store KB metadata, Redis events,
# Neo4j/Qdrant), so seeded demo state survives API restarts. Reseed only
# after `make clean` wipes the volumes — and into a fresh KB: the seed
# script refuses a non-empty same-named KB by design.
```

> These commands target the architecture described in `docs/architecture.md`. The codebase is under active hardening; keep Ruff, Pyright, and pytest clean for touched packages.

> **Integration tests against the live stack.** `tests/conftest.py` defaults the
> per-service test URLs (`DATABASE_URL`, `QDRANT_URL`, `CHILI_TEST_REDIS_URL`,
> `NEO4J_TEST_URI`/`NEO4J_TEST_PASSWORD`) to the dev stack (host-published ports;
> compose hostnames inside the API container), so `@pytest.mark.integration`
> tests run against a running stack instead of self-skipping. Apply migrations
> first (`DATABASE_URL=… python -m alembic upgrade head`). Smokes that are not
> compose services stay opt-in and skip unless their env var is set:
> `OPENAI_API_KEY` (paid API), `SENTENCE_TRANSFORMERS_SMOKE_MODEL` (model
> download), and the Ollama e2e (`OLLAMA_MODEL` + a reachable Ollama server).
>
> ⚠️ **Postgres-touching tests default to `chili_test`, never the dev DB.**
> `tests/database/test_migrations.py` runs `alembic downgrade base` →
> `upgrade head` against `DATABASE_URL` — dropping and recreating **every**
> app table empty. Historically the conftest defaulted `DATABASE_URL` to the
> dev stack's `…:5432/chili`, which destroyed seeded demo state twice
> (2026-05, 2026-07-16 — KB shells survive in the object store while their
> rows vanish). Since 2026-07-16 `tests/conftest.py` defaults to
> `…:5432/chili_test` instead; the dev compose stack creates that DB on
> fresh volumes (`infra/postgres/init-test-db.sql`). On a pre-existing
> volume create it once:
> `docker exec chiliai-postgres-1 psql -U chili -c "CREATE DATABASE chili_test"`
> (migration 0001 installs the TimescaleDB extension itself). An explicitly
> exported `DATABASE_URL` still wins — never export the dev `chili` DSN when
> running the suite. A fresh (schema-less) `chili_test` self-provisions: a
> session-scoped conftest fixture applies `alembic upgrade head` before any
> test runs when the database is reachable but has no `alembic_version`
> table (added 2026-07-24 after the first post-`make clean` run failed 17
> Postgres-backed tests with `UndefinedTable`).

## Quality Requirements

- **Type checking**: All code is written `pyright --strict`-clean; the enforced gate is bare `pyright`, scoped by `tool.pyright.include` in `pyproject.toml` (hardened modules are added to `include`). Full annotations, no untyped `Any`, explicit domain types.
- **Test coverage**: ≥ 85% for each backend package (project standard; the CI gate enforces aggregate `--cov-fail-under=85`). Missing tests = incomplete work.
- **Interface-first**: Every external system (graph DB, vector store, LLM, object store) behind an abstract protocol in `<module>/protocols.py` with concrete adapters in `<module>/adapters/`.

## Configuration

The backend reads a domain configuration YAML/JSON file ("domain pack") at startup. The active file is resolved with strict precedence: the persisted active-pack pointer (`data/config/active_pack.json`, written by admin `POST /config/apply|switch` hot-swaps) **overrides** the `CHILI_CONFIG_PATH` environment variable — see the gotcha in [`config/README.md`](config/README.md). The configuration defines entity types, relationships, enabled capabilities, records feeds, policy rules, alert thresholds, UI metadata, and infra backend selection. See [`docs/architecture.md` §9](../docs/architecture.md#9-domain-configuration-model).

### Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `CHILI_CONFIG_PATH` | (required at runtime) | Path to the domain config YAML/JSON used when no active-pack pointer exists. Parameterized in both compose files (medicare exemplar default); overridden by a persisted pointer after any UI/API pack switch. |
| `CHILI_ACTIVE_PACK_STATE_PATH` | `data/config/active_pack.json` | Location of the active-pack pointer state file (shared `chili-object-data` volume in the dev stack; tests point it at a temp dir). Delete the file or call `config.store.clear_active_pack()` to revert to env-based resolution. |
| `CHILI_ENV` | (required) | Runtime mode: `local`, `dev`, `staging`, or `production`. Startup fails on unset/unknown values. `staging` and `production` require `auth.enabled=True` plus a complete `AuthConfig`; `local` and `dev` permit auth-disabled development. |
| `ALLOWED_ORIGINS` | local dev defaults (`http://localhost:5173`, `:80`, `localhost`) | Comma-separated CORS allow-list for the frontend. Required when the SPA is deployed under a different origin. |
| `CHILI_KB_REPOSITORY_BACKEND` | `in_memory` | Knowledge base metadata repository. Use `object_store` in the dev stack to persist KB/document metadata through API reloads via the configured object store. |
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
| `config/defaults/medicare_fraud.yaml` | Medicare fraud detection (4 entities, 4 relationships, all capabilities). Also the base pack for the dev overlay below. |
| `config/defaults/medicare_fraud_cms_desynpuf.yaml` | CMS DE-SynPUF Medicare fraud exemplar with wider records/feed mappings — the **default** pack for `make dev` / `make prod` |
| `config/defaults/food_supply_chain.yaml` | Food supply chain integrity — exemplar-parity peer pack (8 entities, 11 relationships, 4 records feeds, 3 policy rule packs, full `ui` section, dev-stack infra pins) |
| `config/defaults/department_air_force_housing.yaml` | Department of the Air Force housing oversight — 6 records feeds (UMD, BAH, inventory, market, demographics, resident experience) and statutory UH/MFH scorecard templates with per-metric provenance (see [`../docs/research/housing-scorecard-mandates.md`](../docs/research/housing-scorecard-mandates.md)) |

`config/overlays/medicare_fraud_dev.yaml` is **not** in this table — it is a
partial overlay (see "Config overlays" below), not a standalone pack, so it
never appears in the pack catalog / Config Manager pack list.

### Config overlays

`CHILI_CONFIG_OVERLAY_PATH` layers one or more environment overlay files
onto the base pack named by `CHILI_CONFIG_PATH` (or the active-pack pointer)
before schema validation — comma-separated, declared order, last wins.
Worked example (dev-environment knobs on top of the minimal base pack):

```bash
CHILI_CONFIG_PATH=config/defaults/medicare_fraud.yaml \
CHILI_CONFIG_OVERLAY_PATH=config/overlays/medicare_fraud_dev.yaml \
  uvicorn api.app:create_app --factory --reload --port 8000
```

Mappings deep-merge (overlay keys win recursively); lists and scalars
replace wholesale; an explicit `null` sets a field to `None`. Every overlay
declares `overlay_for: <pack filename stem>` — a mismatch against the
resolved base pack's filename stem skips the overlay with a warning (so the
env var survives a hot-swap to a different pack) rather than failing the
boot; a missing `overlay_for` or an unknown top-level key is a hard error.
The guard is pack-scoped (not `domain.name`-scoped) per the 2026-07-15 ADR
0001 amendment — packs sharing a `domain.name` no longer share an overlay.
Full rationale, the associativity boundary, and the list-replace trade-off:
[ADR 0001](../docs/architecture/decisions/0001-config-overlay-merge-semantics.md).
Directory layout and the loader/`overlay.py` contract:
[`config/README.md`](config/README.md).

### Creating a new domain

1. Copy an existing default and modify entity types, relationships, feeds, rules, and thresholds (contract in [`config/README.md`](config/README.md)).
2. Select it at stack start (`make dev-domain DOMAIN=<pack>` or `CHILI_CONFIG_PATH`), **or** hot-swap a running stack via the Configuration page / admin `POST /config/switch` — no restart needed; the worker converges via the `config.updated` event.
3. The frontend picks up the new config via `GET /config/domain`.

## Knowledge Base Projection Notes

- KB and document metadata are owned by the FastAPI gateway behind `KnowledgeBaseRepository`.
- Graph entities, relationships, and graph metrics remain owned by `graph/` behind `GraphServiceProtocol` and `GraphRepository` adapters.
- `GET /knowledgebases`, `GET /knowledgebases/{id}`, `GET /knowledgebases/{id}/documents`, and `GET /events/stream` use the same live projection helpers so visible status/counts stay aligned.
- `DELETE /knowledgebases/{id}` performs a per-KB cascade across every durable store (graph, vector store, raw records, derived signals, timeseries anomalies, risk history, observations, alert history, the API's alert read projection, GNN cluster summaries, entity metrics, conversations, cases, policy items, evidence packs, scorecard runs, the document-status projection, and the object-store prefix — see `knowledgebases.cleanup.kb_deletion_steps` for the authoritative, ordered step list), then KB metadata. The alert-projection step runs only in the API's bundle (the store is API-owned; the worker's retry bundle skips it rather than import across the module boundary). The GNN cluster-summary step (`gnn_clusters`), by contrast, is analytics-owned and required in both bundles — API and worker each build their own `ObjectStoreClusterSummaryStore` from the injected object store. If any step fails the endpoint returns 207 with `pending_cleanup=true`; the KB record is flagged and a `KnowledgeBaseDeletedEvent(cleanup_pending=True)` is published. The worker coordinator picks up that event and retries the full cascade. A subsequent DELETE for a `pending_cleanup` KB also retries the idempotent cascade instead of permanently rejecting the stale metadata row. All cleanup calls are idempotent.
- `DELETE /knowledgebases/{id}/documents/{document_id}` deletes one document's object-store artifacts, its `KnowledgeBaseRepository` record, and its row (if any) in the durable document-status projection (`SourceDocumentStatusStore.delete_by_document`) — this keeps a status-filtered `GET .../documents?status=...` list's `total` from ever counting a document that no longer exists. `POST /knowledgebases/{id}/documents` performs the same status-row purge for the superseded document when a re-upload replaces it (`_cleanup_replaced_document` in `api/routers/knowledgebases.py`), so the replacement path can't reintroduce the same orphaned-row mismatch.
- The `object_store` KB repository is intended for local/dev single-writer durability. Add a dedicated production metadata adapter, optional dependency, and migration story before treating it as a high-concurrency production database.

## Ingestion Registration Notes

- Document registration is idempotent per knowledge base for repeated content bytes and repeated remote URIs. The ingestion service derives deterministic source document IDs from content SHA-256 hashes or URI hashes and does not publish duplicate `documents.uploaded` events when the source has already been registered.
- Content uploads are stored under the deterministic source document ID; remote URI submissions write a small marker object for deduplication while preserving the original URI on the event/receipt.

## Document Status Projection Notes (BL-041)

- A durable per-document ingestion status projection lives behind `ingestion.adapters.protocols.SourceDocumentStatusStore` (in-memory + Postgres adapters, `source_document_status` table via migration `0009_document_status`). See [`ingestion/README.md`](ingestion/README.md) for the monotonic-transition contract, the `IngestionStatus.EXTRACTED_EMPTY` status, and `STATUS_RANK`.
- The worker's `_dispatch_event` (`agent/coordinator.py`) projects every drained `DocumentsUploadedEvent`/`DocumentsParsedEvent`/`DocumentsFailedEvent`/`DocumentsExtractionWarningEvent` onto a status transition via `agent.status_projection.project_document_status`, so the projection stays current without a dedicated consumer process.
- `GET /knowledgebases/{kb_id}/documents` exposes the projection's `current_status`, `last_error`, `dropped_entity_count`/`dropped_relationship_count`, and `drop_sample_reasons` per document, and supports `?status=` filtering.
- Coordinator parse-stage failures (`handle_documents_parsed`/`handle_documents_chunked` missing-key or object-store read failures) are converted to a per-document `DocumentsFailedEvent` rather than raising and poisoning the rest of the batch — one bad document fails on its own.
- KB deletion purges the projection via `SourceDocumentStatusStore.delete_by_kb` (part of the shared `knowledgebases.cleanup.kb_deletion_steps` cascade); single-document delete and changed-content reupload purge the superseded row via `delete_by_document` so a status-filtered document list never counts a document that no longer exists.

## Alert Feed Notes (alerts.36)

- The alert feed is a durable read model, not a separate API-owned projection. `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, SSE `active_alerts`, `GET /analytics/overview`, and `GET /graph/entities/{id}`'s related-alerts all read the same `alert_history` table through `monitoring.adapters.protocols.AlertFeedStoreProtocol` (`api.dependencies.get_alert_feed_store`) — Postgres-backed (`PostgresAlertHistoryStore`) when a connection provider resolves, in-memory (`InMemoryAlertHistoryWriter`) otherwise. There is no `CHILI_ALERT_REPOSITORY_BACKEND` env var and no `_alert_store.py`; the file that used to hold the API-owned projection has been deleted.
- `alert_history` rows carry real read-model columns populated at write time — `entity_label`, `confidence`, `tags` — instead of a client-side reshape of a generic `Alert`. The analytics pipeline's explainability stage sets `confidence` from the risk assessment's overall score and `tags` from the top-3 risk-factor names; `MonitoringService.evaluate()` sets `confidence` from the threshold-ratio score and `tags` from a kebab-slugged metric name. Both currently fall back `entity_label` to `entity_id` (no cheap display value is in scope without an extra graph read — see the follow-up story in `docs/backlog/analytics.md`).
- Acknowledge (`POST /alerts/{id}/acknowledge`) is a durable status write against `alert_history`, not an in-process flag — it survives API restarts.
- `DELETE /knowledgebases/{id}` purges alerts as one step of the shared cascade (`alert_history`, via `AlertHistoryWriter.delete_by_kb`) — see `knowledgebases.cleanup.kb_deletion_steps`. Both the API and the worker's retry bundle build their own `AlertHistoryWriter`, so there is no separate "API bundle only" projection step left to skip.

## De-seeded ApiState Notes (BL-012)

- The seeded, in-memory `ApiState` no longer holds alerts, cases, conversations, workflows, evidence packs, or a demo graph. Every frontend read path resolves through a durable store; `ApiState` now only owns the RAG service handle used by the chat streaming path. `GET /analytics/timeseries/{entity_id}` moved off `ApiState` (B2, analytics.07) — it reads `get_entity_series_source()` (a `RecordAggregateTimeSeriesSource` over record-column aggregates and `DomainConfig.timeseries.metrics`) joined with persisted anomalies from `get_timeseries_anomaly_store()` — and `GET /analytics/risk-scores/{entity_id}` followed in B2: it assesses via the DI `get_risk_service()` (Postgres-backed derived signals when a DB is configured), and `ApiState`'s seeded risk composition was deleted.
- `/chat/conversations` (create/read/append) reads and writes the durable `ConversationRepository` (`conversations/`). The non-streaming append builds the user + assistant turn from the RAG answer in `get_chat_message_payload`; the streaming branch fetches the conversation from the same repository.
- `GET /graph/entities/{id}` is served by `api/_graph_entity_payload.py` from the durable graph service (the same store the worker and the `/admin/dev-seed` endpoint write to), with risk scores from the durable risk service and related alerts from the alert projection repository.
- `GET /analytics/overview` is computed entirely from durable stores (`api/_analytics_overview.py`): active/high-risk alert counts from the alert projection, open-case counts from the durable case repository, and `entities_monitored` from KB metadata — aggregated across every knowledge base.
- A regression guard (`tests/api/test_deseed_regression.py`) asserts no `_seed_*` method/attribute survives on `ApiState` and that no non-test backend module reads a `_seed_*` token.

## Workflow Projection Notes

- Workflow state is owned by `agent/` behind `WorkflowRunStoreProtocol` and surfaced to API routes through `AgentServiceProtocol`.
- `GET /workflows` and SSE `running_workflows` are service-backed and no longer read workflow summaries from legacy seeded `ApiState`. `GET /workflows` accepts `knowledge_base_id`, `status`, `limit`, and `offset` query parameters for scoped timeline views.
- Workflow runs now track `queued`, `running`, `completed`, `failed`, and `cancelled` states with `updated_at` timestamps. The worker coordinator updates stage progress, preserves correlation IDs across document parsing events, marks document parse failures terminal, and tracks structured-record ingestion as a KB-scoped workflow.
- The in-memory workflow store remains available for local/test usage with detached returned models, idempotency-key uniqueness checks, and lock-protected shared indexes.
- The Redis workflow store is intended for shared operational state between API and worker containers. For compliance-grade immutable workflow history, add a Postgres/audit adapter or outbox/event-sourcing layer behind the same protocol.

## Analytics Runtime Notes

- GNN analysis is controlled by the domain `capabilities.gnn` flag. When the capability is disabled, the worker skips GNN Flow B without emitting `analysis.failed`.
- The GNN snapshot source is graph-repository-backed in both the worker (`agent.coordinator.build_graph_snapshot_source`) and the API (`api.dependencies.get_graph_snapshot_source`) — it builds bounded `GraphSnapshot`s from the live graph repository (top-degree nodes kept, capped by `DomainConfig.gnn.snapshot_max_nodes`, default 5000) and serves cluster summaries from an `ObjectStoreClusterSummaryStore` over the configured object store. The worker constructs one cluster-store instance per process and shares it between the snapshot source and any pipeline step that persists cluster summaries.
- Flow B (`handle_graph_updated_for_analytics`) persists each successful GNN stage's community results through that same shared cluster store immediately after `_run_gnn_stage` returns (`_persist_gnn_clusters`), so `/analytics/gnn/clusters` serves real pipeline output rather than stale or empty data. An empty `communities` list still writes — it honestly replaces any stale clusters. Store failures are logged as a warning and never fail the pipeline.
- The KB-delete cascade purges cluster summaries too: `knowledgebases.cleanup.KbDeletionStores.gnn_cluster_store` (step `gnn_clusters`, structurally typed as `GnnClusterPurger`) is a required field on both the API and worker bundles — each builds its own `ObjectStoreClusterSummaryStore` from the already-injected object store rather than sharing the worker's process-local instance (object-store-backed state is shared by construction).
- Fresh knowledge bases may not have a registered graph snapshot yet (no entities upserted), and a snapshot with a single node is too small for scoring/community detection. Both cases (`GnnSnapshotUnavailableError`, `GnnInsufficientGraphError`) are treated as controlled skips, not failed analytics stages, so document/vector Flow A remains quiet and successful while GNN waits for a second entity to arrive.
- GNN analytics currently fire on document-driven `graph.updated` events only (`agent.coordinator.handle_graph_updated_for_analytics`, Flow B) — `graph.service.upsert_records_graph` deliberately publishes no `GraphUpdatedEvent` for structured-records ingestion, so records-only knowledge bases show zero clusters until a document lands or `docs/backlog/analytics.md`'s analytics.34 story ships.
- The GNN pipeline stage is live end to end, not just unit-tested against fixtures: `tests/analytics/gnn/test_gnn_live_integration.py` (`@pytest.mark.integration`) seeds entities/relationships through a real `Neo4jGraphRepository`, builds a `GraphRepositorySnapshotSource` over it, and runs `GnnService.analyze` to assert scored nodes and detected communities come back from actual graph data.
- Peer-group z-score analytics (`analytics/peerstats/`) are controlled by the domain `capabilities.peer_stats` flag. When enabled, the worker runs `run_peerstats_stage` best-effort on every `RecordsIngestedEvent`. Results are written to the `entity_derived_signals` table; `PostgresRiskSignalSource` (in `analytics/risk`) reads them to assemble risk profiles. The medicare default config enables this capability with two provider billing specs (`weekly_provider_billing`, `weekly_provider_claim_count`) that flag outlier billing volume and claim count. A `peer_stats:` top-level YAML section (list of `PeerMetricSpec`) is required when the capability is enabled.
- Self-history timeseries anomaly analytics (`analytics/timeseries/`) are controlled by the domain `capabilities.timeseries` flag. When enabled, the worker runs `run_timeseries_stage` (`agent.coordinator`) best-effort on every `RecordsIngestedEvent`, immediately after — but independently of — the peerstats stage: each self-history `TimeseriesMetricSpec` (a `RecordAggregateTimeSeriesSource`-backed per-entity series, reusing the peerstats `RecordColumnSourceProtocol` aggregate SQL) is analyzed with `TimeseriesService.analyze`; detected anomalies are upserted to `timeseries_anomalies` (`TimeseriesAnomalyStoreProtocol`) and the latest anomaly per entity is also written as a `timeseries_anomaly:<spec name>`-prefixed `DerivedRiskSignal` to `entity_derived_signals`, so the risk service picks it up the same way as peerstats signals. Peerstats-affected and timeseries-affected entity ids are merged before risk assessment runs once per entity. A missing-history entity (`TimeseriesInsufficientHistoryError`) is a per-entity controlled skip; a spec misconfiguration (`TimeseriesConfigurationError`, e.g. an unavailable detection-strategy extra) skips the rest of that spec's entities. Extreme flat-baseline z-scores (`z=inf`) are clamped to `1e6` before being persisted so stored floats stay JSON-safe. A `timeseries:` top-level YAML section (list of `TimeseriesMetricSpec`) is required when the capability is enabled.
- The KB-delete cascade purges persisted timeseries anomalies too: `knowledgebases.cleanup.KbDeletionStores.timeseries_anomaly_store` (step `timeseries_anomalies`, structurally typed as `TimeseriesAnomalyPurger`, positioned directly after `derived_signals`) is a required field on both the API and worker bundles — the worker reuses its already-built `TimeseriesAnomalyStoreProtocol` instance and the API injects one via `api.dependencies.get_timeseries_anomaly_store`.
- Explainability narrative + attribution backends (`analytics/explainability/`) are selected per domain config (BL-048, Sprint 2026-28 B3): `DomainConfig.analytics.narrative_backend: Literal["deterministic","llm"]` (default `"deterministic"`) and `attribution_backend: Literal["none","shap"]` (default `"none"`). The worker builds both via `agent.coordinator.build_narrative_generator`/`build_feature_attributor` and threads them into `create_explainability_service(...)` at the Flow B assembly site; `_run_explainability_stage` is otherwise unchanged. `"llm"` wraps `create_llm_service` in `LlmNarrativeGenerator`, falling back to `DeterministicNarrativeGenerator` on any `LlmError`, unexpected exception (including `GenerateRequest` construction, which sits inside the guard), empty completion, or a malformed completion — no `## ` sections, or an empty opening summary (a completion that starts directly with a heading) — (WARNING log, never raises). `"shap"` builds `ShapRiskAttributor`, which attributes `analytics.risk`'s `LinearScoringStrategy` composite over the entity's `entity_derived_signals` feature vector via `shap.Explainer`; a missing `[analytics]` extra, no risk-factor features, or any explainer exception degrades to an empty attribution list (WARNING log, never raises) rather than failing the pipeline. The CMS medicare and Air Force housing default packs enable both (`narrative_backend: llm`, `attribution_backend: shap`); other packs stay on the deterministic/noop defaults. Persisted `EvidencePack`s carry the results as `narrative_sections`/`attribution` (both default `[]`, so pre-B3 persisted packs deserialize unchanged).
