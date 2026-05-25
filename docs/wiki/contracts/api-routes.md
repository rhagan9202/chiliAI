# API Routes Reference

**Verified against codebase:** 2026-05-20
**Source:** `backend/api/routers/`, `backend/api/app.py`, `backend/api/contracts.py`

All routes are registered in `api/app.py::create_app()`. RBAC roles follow the hierarchy: `viewer(1) < analyst(2) = service(2) < admin(3)`. When `AuthConfig.enabled=False` (local/dev), all routes are open.

---

## Health

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/health` | `{"status": "ok"}` | None |

---

## Configuration — `/config`

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/config/domain` | `dict[str, object]` (DomainConfig as JSON) | viewer |
| `GET` | `/config/features` | `dict[str, object]` (feature flags + pages) | viewer |
| `GET` | `/config/domain/schema` | `dict[str, object]` (Pydantic JSON schema) | viewer |

---

## Authentication — `/auth`

| Method | Path | Response | Auth | Notes |
|--------|------|----------|------|-------|
| `GET` | `/auth/login` | `RedirectResponse` | None | Starts OIDC PKCE flow |
| `GET` | `/auth/callback` | `RedirectResponse` | None | OIDC callback, sets cookie |
| `POST` | `/auth/logout` | `Response` | None | Clears `chiliai_session` cookie |
| `GET` | `/auth/me` | `User` | session/bearer | Returns current user |

`User` model: `{user_id: str, roles: list[str], email: str | None}`

---

## Knowledge Bases — `/knowledgebases`

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| `POST` | `/knowledgebases` | `CreateKbRequest` | `KnowledgeBase` 201 | analyst |
| `GET` | `/knowledgebases` | `?limit=50&offset=0` | `KbListResponse` | viewer |
| `GET` | `/knowledgebases/{kb_id}` | — | `KnowledgeBase` | viewer |
| `DELETE` | `/knowledgebases/{kb_id}` | — | 204 | admin |
| `GET` | `/knowledgebases/{kb_id}/documents` | `?limit=50&offset=0` | `DocumentListResponse` | viewer |
| `DELETE` | `/knowledgebases/{kb_id}/documents/{doc_id}` | — | 204 | analyst |
| `POST` | `/knowledgebases/{kb_id}/documents` | `multipart/form-data` files | `DocumentRegistrationResponse` 202 | analyst |

### Request/Response Models

```python
class CreateKbRequest(BaseModel):
    name: str           # [1, 200] chars
    description: str = ""  # [0, 2000] chars

class KbListResponse(BaseModel):
    items: list[KnowledgeBase]
    total: int

class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    total: int

class DocumentSummary(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    content_type: str | None
    size_bytes: int | None
    status: str
    created_at: datetime

class DocumentRegistrationResponse(BaseModel):
    documents: list[DocumentReceipt]   # from ingestion/service_models.py
```

File upload validates: content type in `ValidationConfig.allowed_content_types`, size <= `max_file_size_mb`. After registration, publishes `DocumentsUploadedEvent`.

---

## Alerts — `/alerts`

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/alerts` | `AlertListResponse` | viewer |
| `GET` | `/alerts/{alert_id}` | `AlertDetailResponse` | viewer |
| `POST` | `/alerts/{alert_id}/acknowledge` | `ApiEnvelope` 200 | analyst |

```python
class AlertListResponse(BaseModel):
    items: list[AlertListItem]
    page: PageInfo

class AlertListItem(BaseModel):
    id: str; entity_id: str; entity_type: str; entity_label: str
    severity: Literal["low","medium","high","critical"]
    status: Literal["open","acknowledged","investigating","resolved","dismissed"]
    title: str; reasoning: str
    confidence: float   # [0.0, 1.0]
    evidence_pack_id: str | None; created_at: datetime
    tags: list[str]

class AlertDetailResponse(BaseModel):
    alert: AlertListItem
    related_entity_ids: list[str]
    policy_citations: list[PolicyCitation]

class ApiEnvelope(BaseModel):
    status: Literal["accepted", "ok"]
    message: str
```

---

## Cases — `/cases`

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| `GET` | `/cases` | — | `CaseListResponse` | viewer |
| `GET` | `/cases/{case_id}` | — | `CaseDetailResponse` | viewer |
| `POST` | `/cases` | `CaseCreateRequest` | `CaseDetailResponse` | analyst |
| `PATCH` | `/cases/{case_id}` | `CaseUpdateRequest` | `CaseDetailResponse` | analyst |
| `POST` | `/cases/{case_id}/feedback` | `CaseFeedbackCreateRequest` | `CaseDetailResponse` | analyst |

```python
class CaseCreateRequest(BaseModel):
    title: str
    priority: Literal["low","medium","high","critical"]
    assignee: str | None; alert_ids: list[str]

class CaseUpdateRequest(BaseModel):
    title: str | None; status: Literal["open","in_review","closed"] | None
    priority: Literal["low","medium","high","critical"] | None; assignee: str | None

class CaseFeedbackCreateRequest(BaseModel):
    label: Literal["suspicious","not_suspicious","insufficient_evidence"]
    evidence_adequacy: Literal["low","medium","high"]
    missing_evidence: list[str]; notes: str
```

---

## Evidence Packs — `/evidence-packs`

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/evidence-packs/{evidence_pack_id}` | `EvidencePackResponse` | viewer |

```python
class EvidencePackResponse(BaseModel):
    id: str; alert_id: str; reasoning: str
    confidence: float; scores: dict[str, float]
    subgraph_node_ids: list[str]; subgraph_edge_ids: list[str]
    items: list[EvidenceItemResponse]
    policy_citations: list[PolicyCitation]
```

---

## Graph — `/graph`

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/graph/entities/{entity_id}` | `GraphEntityDetailResponse` | viewer |

```python
class GraphEntityDetailResponse(BaseModel):
    entity: GraphNodeResponse
    neighbors: list[GraphNodeResponse]
    relationships: list[GraphEdgeResponse]
    related_alert_ids: list[str]

class GraphNodeResponse(BaseModel):
    id: str; type: str; label: str; summary: str
    risk_score: float; properties: dict[str, str | int | float | bool]

class GraphEdgeResponse(BaseModel):
    id: str; type: str; source_id: str; target_id: str; summary: str
```

---

## RAG Chat — `/chat`

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| `GET` | `/chat/conversations/{conversation_id}` | — | `ChatConversationResponse` | viewer |
| `POST` | `/chat/conversations` | `ChatConversationCreateRequest` | `ChatConversationResponse` | analyst |
| `POST` | `/chat/conversations/{conversation_id}/messages` | `ChatMessageCreateRequest` | `ChatConversationResponse` or `StreamingResponse` | analyst |

`POST .../messages?stream=true` returns SSE stream. SSE format: `data: {"token": str, "done": bool, ["sources": list[str]]}\n\n`

```python
class ChatConversationCreateRequest(BaseModel):
    knowledge_base_id: str; title: str | None

class ChatMessageCreateRequest(BaseModel):
    content: str
    include_graph_context: bool = True
    filters: dict[str, str | int | float | bool] = {}

class ChatConversationResponse(BaseModel):
    id: str; title: str; knowledge_base_id: str
    messages: list[ChatMessageResponse]
```

---

## Records — `/records`

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| `POST` | `/records/{kb_id}/files` | `multipart/form-data: feed=str, file=.csv/.jsonl` | `RecordIngestReceipt` 202 | analyst |
| `POST` | `/records/{kb_id}/push` | `RecordPushRequest` | `RecordIngestReceipt` 202 | analyst |

```python
class RecordPushRequest(BaseModel):
    feed_name: str    # min_length=1
    rows: list[dict[str, object]]   # min_length=1

class RecordIngestReceipt(BaseModel):
    knowledge_base_id: str; feed_name: str; record_type: str
    correlation_id: str; accepted_count: int; created_at: datetime
```

---

## Workflows — `/workflows`

| Method | Path | Query | Response | Auth |
|--------|------|-------|----------|------|
| `GET` | `/workflows` | `?knowledge_base_id=&status=&limit=50&offset=0` | `WorkflowRunListResponse` | viewer |

```python
class WorkflowRunResponse(BaseModel):
    id: str
    workflow_type: Literal["ingestion","graph_build","analytics","monitoring"]
    status: Literal["queued","running","completed","failed","cancelled"]
    knowledge_base_id: str; started_at: datetime; updated_at: datetime
    current_step: str; last_error: str | None
```

---

## Analytics — `/analytics`

| Method | Path | Query | Response | Auth |
|--------|------|-------|----------|------|
| `GET` | `/analytics/risk-scores` | `?kb_id=&entity_type=&limit=` | `RiskScoreListResponse` | viewer |
| `GET` | `/analytics/timeseries` | `?entity_id=&metric_name=&kb_id=` | `MetricTimeseriesResponse` | viewer |
| `GET` | `/analytics/gnn/clusters` | `?kb_id=` | `GnnClusterResponse` | viewer |
| `GET` | `/analytics/overview` | — | `AnalyticsOverviewResponse` | viewer |
| `GET` | `/analytics/risk-score/{entity_id}` | — | `RiskScoreResponse` | viewer |
| `GET` | `/analytics/timeseries/{entity_id}` | — | `EntityTimeseriesResponse` | viewer |

**Wiring status:** All analytics routes are served by `@lru_cache` in-memory stub services seeded at API startup — not wired to live analytics stores. See [modules/analytics.md — Current Wiring Status](../modules/analytics.md#current-wiring-status) for detail.

### Static payload shapes (api/contracts.py)

The three entity-scoped analytics routes (`/overview`, `/risk-score/{entity_id}`, `/timeseries/{entity_id}`) are backed by `api/dependencies.py` factory functions that return shapes from `api/contracts.py`. These are not returned by the live analytics services (which use `analytics/*/service_models.py`).

```python
class AnalyticsOverviewResponse(BaseModel):
    """High-level analytics summary for dashboard widgets."""
    active_alerts: int = Field(ge=0)
    open_cases: int = Field(ge=0)
    entities_monitored: int = Field(ge=0)
    high_risk_entities: int = Field(ge=0)

class RiskFactorResponse(BaseModel):
    """Frontend risk-factor breakdown."""
    factor_name: str
    contribution: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None

class RiskScoreResponse(BaseModel):
    """Risk summary for one entity."""
    entity_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "critical"]
    factors: list[RiskFactorResponse] = Field(default_factory=list)

class EntityTimeseriesPointResponse(BaseModel):
    """One point in an entity timeseries chart."""
    timestamp: datetime
    value: float
    label: str
    is_anomaly: bool = False

class EntityTimeseriesResponse(BaseModel):
    """Timeseries payload for entity trend charts."""
    entity_id: str
    metric_name: str
    points: list[EntityTimeseriesPointResponse] = Field(default_factory=list)
```

**Note:** `RiskFactorResponse` (from `api/contracts.py`) exposes only `factor_name`, `contribution`, `rationale` — a subset of the internal `RiskFactor` model (`analytics/risk/models.py`) which additionally carries `raw_value` and `weight`. These fields are dropped at the API boundary.

**Dependency chain for entity-scoped routes:**
- `GET /analytics/overview` → `get_analytics_overview_payload(state)` → `state.get_analytics_overview()` → returns `AnalyticsOverviewResponse`
- `GET /analytics/risk-score/{entity_id}` → `get_risk_score_payload(entity_id, state)` → `state.get_risk_score(entity_id)` → returns `RiskScoreResponse`
- `GET /analytics/timeseries/{entity_id}` → `get_timeseries_payload(entity_id, state)` → `state.get_timeseries(entity_id)` → returns `EntityTimeseriesResponse`

All three read from `ApiState` (per-app mutable state seeded at startup), not from live analytics services.

---

## Real-time — `/events`, `/ws`

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/events/workspace` | SSE stream of `RealtimeSnapshotResponse` | viewer |
| `WS` | `/ws` | WebSocket (JSON frames) | viewer |

```python
class RealtimeSnapshotResponse(BaseModel):
    sequence: int; emitted_at: datetime
    active_alerts: int; running_workflows: int
    knowledge_base_statuses: dict[str, str]
```

---

## Investigation — `/investigation`

Last verified: 2026-05-20. Source: `backend/api/routers/investigation.py`.

All routes require `viewer` role. Backed by `GraphServiceProtocol` (injected via `get_graph_service()`).

| Method | Path | Query params | Response | Notes |
|--------|------|-------------|----------|-------|
| `GET` | `/investigation/entities/{entity_id}` | `kb_id=` (required) | `EntityDetailResponse` | 404 if entity absent |
| `GET` | `/investigation/entities/{entity_id}/neighborhood` | `kb_id=`, `depth=2` (1–5) | `NeighborhoodResponse` | 404 if center entity absent |
| `GET` | `/investigation/search` | `kb_id=`, `q=` (min_length=1), `limit=20` (1–500), `offset=0` | `EntitySearchResponse` | Substring property match |

```python
class EntityDetailResponse(BaseModel):
    entity: Entity           # shared/types.py Entity (runtime fields)

class NeighborhoodResponse(BaseModel):
    center_entity_id: str
    entities: list[Entity]
    relationships: list[Relationship]

class EntitySearchResponse(BaseModel):
    items: list[Entity]
    total: int               # NOTE: currently set to len(items), not a DB-level count
```

**Drift note:** `total` in `EntitySearchResponse` is computed as `len(items)` in the router (`search_entities` returns a plain list). This means `total` equals `limit` when the result set is truncated — it does not reflect the true total match count. The service-layer `EntitySearchQuery` accepts `offset` but the router does not paginate the returned `total`.

Cross-linked to: [modules/graph.md](../modules/graph.md), [modules/api.md](../modules/api.md).

---

## Policy — `/policy`

Route policy introspection endpoint (`api/routers/policy.py`) — provides audit of route role annotations. Internal use.

---

## RBAC Role Hierarchy

```python
ROLE_HIERARCHY = {"viewer": 1, "analyst": 2, "service": 2, "admin": 3}
```

- `viewer` — read-only access to all GET endpoints
- `analyst` — read + write (KB creation, document upload, chat, record push, case management)
- `service` — machine-to-machine, same level as analyst
- `admin` — full access including destructive operations (DELETE knowledge base)
- When `AuthConfig.enabled=False`: anonymous user with `_authdisabled` role bypasses all checks
