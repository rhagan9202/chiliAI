# Module: api

**Verified against codebase:** 2026-06-16
**Source:** `backend/api/`

## Purpose

FastAPI gateway layer. Thin HTTP orchestration — no business logic in routers. Routes delegate to service modules via dependency injection. Owns: auth middleware, RBAC enforcement, SSE/WebSocket real-time push, and API-facing projections for alerts, knowledge bases, workflows, graph entities, chat, policy items, and analytics read models.

Does **not** own: any business logic, data persistence, event processing.

---

## Directory Structure

```
api/
  app.py                  # create_app() factory — registers routers, middleware, health
  state.py                # ApiState container assembled at startup
  dependencies.py         # DI wiring for all injected services
  contracts.py            # All API-facing request/response Pydantic models
  _alert_store.py         # In-process alert projection + repository
  _kb_projection.py       # project_knowledge_base() hydration helper
  _rag_bridges.py         # RAG <-> KB document/entity bridge helpers
  _workflow_projection.py # project_workflow_runs() helper
  middleware/
    auth.py               # JWT/cookie/Bearer resolution → User; get_current_user()
    rbac.py               # require_role() dependency factory; ROLE_HIERARCHY
    session_store.py      # SessionStoreProtocol, SessionRecord, chiliai_session cookie
    policy_registry.py    # assert_complete() — default-deny audit on all routes
    metrics.py            # HTTP request metrics middleware
    exceptions.py         # SessionNotFoundError
  routers/
    auth.py               # /auth/login, /auth/callback, /auth/logout, /auth/me
    knowledgebases.py     # /knowledgebases CRUD + document management
    alerts.py             # /alerts feed + acknowledge
    cases.py              # /cases CRUD + feedback
    evidence.py           # /evidence-packs/{id}
    graph.py              # /graph/entities/{id}
    rag.py                # /chat conversations + message streaming
    records.py            # /records file upload + api-push
    workflows.py          # /workflows list/detail/cancel
    analytics.py          # /analytics risk/timeseries/gnn/overview
    config.py             # /config/domain, /config/features, /config/domain/schema
    events.py             # /events/stream SSE
    ws.py                 # /ws/alerts and /ws/pipeline WebSocket hub
    investigation.py      # /investigation queries
    policy.py             # /policy/items list/detail/triage
    dev_seed.py           # /admin/dev-seed non-production fixture seeder
    _oidc_client.py       # OIDC PKCE helpers (internal to auth router)
```

---

## `create_app()` Factory

```python
def create_app() -> FastAPI:
```

1. Calls `configure_logging()`, `setup_tracing()`.
2. Clears `get_domain_config` LRU cache (test isolation).
3. Loads `DomainConfig` from the resolved active pack (active-pack pointer > `CHILI_CONFIG_PATH`).
4. Enforces production guardrail: `CHILI_ENV ∈ {staging, production}` → `AuthConfig.enabled` must be `True` with all required fields.
5. Creates `FastAPI` app with CORS middleware (`ALLOWED_ORIGINS` env var or localhost defaults).
6. Attaches `ApiState` to `app.state.api_state`.
7. Registers HTTP metrics middleware, `GET /metrics`, and OpenTelemetry instrumentation.
8. Mounts all routers.
9. Calls `assert_complete(app)` — policy registry default-deny audit.

`CHILI_ENV` allowed values: `local`, `dev`, `staging`, `production`.

---

## Auth Middleware (`middleware/auth.py`)

### `User` model
```python
class User(BaseModel):
    user_id: str
    roles: list[str] = []
    email: str | None = None
```

### Resolution order
1. `chiliai_session` HttpOnly cookie → `SessionStoreProtocol.get(session_id)` → `SessionRecord`
2. `Authorization: Bearer <jwt>` → JWKS validation against `AuthConfig.jwks_uri`
3. If `AuthConfig.enabled=False` → anonymous `User(user_id="anonymous", roles=["_authdisabled"])`

### Key functions
```python
def get_current_user(request: Request, ...) -> User: ...
def get_current_websocket_user(websocket: WebSocket, ...) -> User: ...
def decode_token(token: str, jwks: dict, audience: str, issuer: str) -> dict[str, object]: ...
```

JWKS document is cached for `jwks_cache_seconds` (default 3600). Fetcher is injectable for tests.

### Session cookie name
```python
SESSION_COOKIE_NAME = "chiliai_session"
```

---

## RBAC (`middleware/rbac.py`)

```python
ROLE_HIERARCHY = {"viewer": 1, "analyst": 2, "service": 2, "admin": 3}

def require_role(role: str) -> Callable[..., User]:
    """FastAPI dependency factory. Bypasses check when AuthConfig.enabled=False."""
```

When auth is disabled, the `_authdisabled` role effectively grants admin-level access (all checks pass).

---

## In-process Read Models

The API maintains lightweight read projections for read-heavy surfaces. Persistence depends on the selected repository/adapter:

| File | What it stores | Populated by |
|------|---------------|-------------|
| `_alert_store.py` | `AlertProjectionRepository` — alert list for `/alerts` | `AlertsCreatedEvent` handlers |
| `knowledgebases/` module | `KnowledgeBaseRepository` — KB list + document records | Direct mutations in KB router; in-memory or object-store-backed via `CHILI_KB_REPOSITORY_BACKEND` |
| `_workflow_projection.py` | Project `WorkflowRun` list for `/workflows` | `AgentServiceProtocol.list_workflows()` |

---

## Route → Service Dispatch

| Router | Dispatches to |
|--------|--------------|
| `knowledgebases` | `IngestionServiceProtocol`, `GraphServiceProtocol`, `KnowledgeBaseRepository`, `ObjectStore`, `EventBus` |
| `alerts` | `AlertProjectionRepository` |
| `cases` | `CaseService`, `CaseRepository` (in-memory or Postgres) |
| `rag` | `RagServiceProtocol`, `ApiState` |
| `records` | `RecordsServiceProtocol` |
| `workflows` | `AgentServiceProtocol` |
| `analytics` | `RiskServiceProtocol`, `TimeseriesServiceProtocol`, `GnnServiceProtocol`, durable overview aggregation, `RecordAggregateTimeSeriesSource` + `TimeseriesAnomalyStoreProtocol` for the entity timeseries route, plus remaining `ApiState` entity risk-score composition |
| `config` | `DomainConfig` (loaded once, LRU cached) |
| `graph` | `GraphServiceProtocol` via dependency |
| `auth` | `SessionStoreProtocol`, OIDC client, `DomainConfig.auth` |
| `events` | `AlertProjectionRepository`, `AgentServiceProtocol`, `KnowledgeBaseRepository` |
| `policy` | `PolicyService`, `PolicyItemRepository` (in-memory or Postgres) |
| `dev_seed` | Writes deterministic non-production fixtures into the real repositories |

---

## Dependencies (`api/dependencies.py`)

Key injected services (all are `lru_cache`-backed or per-request):

```python
get_domain_config() -> DomainConfig           # LRU cached, cleared on create_app()
get_api_state(request) -> ApiState
get_event_bus() -> EventBus
get_ingestion_service() -> IngestionService
get_graph_service() -> GraphServiceProtocol
get_vector_service() -> VectorServiceProtocol
get_embeddings_service() -> EmbeddingsServiceProtocol
get_llm_service() -> LlmServiceProtocol
get_rag_service() -> RagServiceProtocol
get_monitoring_service() -> MonitoringServiceProtocol
get_risk_service() -> RiskServiceProtocol
get_timeseries_service() -> TimeseriesServiceProtocol
get_gnn_service() -> GnnServiceProtocol
get_object_store() -> ObjectStore
get_knowledge_base_repository() -> KnowledgeBaseRepository
get_records_service(...) -> RecordsServiceProtocol
get_agent_service(...) -> AgentServiceProtocol
get_alert_repository(request) -> AlertProjectionRepository
get_case_service(...) -> CaseService
get_conversation_service(...) -> ConversationService
get_policy_service(...) -> PolicyService
get_session_store() -> SessionStoreProtocol
```

---

## Tests

Location: `backend/tests/api/`

Integration tests marked `@pytest.mark.integration`.
