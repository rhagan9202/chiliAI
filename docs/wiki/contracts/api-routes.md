# API Routes Reference

**Verified against codebase:** 2026-06-16
**Source:** live `api.app:create_app()` route dump with `CHILI_ENV=local`, plus `backend/api/routers/`, `backend/api/app.py`, `backend/api/contracts.py`

All routes are registered in `api/app.py::create_app()`. RBAC roles follow the hierarchy: `viewer(1) < analyst(2) = service(2) < admin(3)`. When `AuthConfig.enabled=False` (local/dev), all routes are open.

---

## Health

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/health` | `{"status": "ok"}` | None |

## Observability

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/metrics` | Prometheus text exposition | service |

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
| `DELETE` | `/knowledgebases/{kb_id}` | — | 204 / 207 / 409 | admin |
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

### `DELETE /knowledgebases/{kb_id}` — cascade delete (updated 2026-05-22)

5-step cascade: graph → vector → raw_records → object_store → kb_repository. Status codes:

| Status | Condition |
|--------|-----------|
| `204 No Content` | All 5 steps succeeded; KB fully deleted. |
| `207 Multi-Status` | One or more steps failed; `KnowledgeBase.pending_cleanup` set to `True`; `KnowledgeBaseDeletedEvent(cleanup_pending=True)` published so the worker can retry. |
| `409 Conflict` | KB has an active workflow (`WorkflowBusyTracker.is_busy()=True`) OR `KnowledgeBase.pending_cleanup=True`. |

207 response body:
```json
{
  "knowledge_base_id": "...",
  "pending_cleanup": true,
  "steps": [
    {"step": "graph", "status": "succeeded"},
    {"step": "vector", "status": "failed", "error": "..."},
    {"step": "raw_records", "status": "succeeded"},
    {"step": "object_store", "status": "succeeded"}
  ]
}
```

### `POST /knowledgebases/{kb_id}/documents` — idempotent re-upload (updated 2026-05-22)

Content-hash deduplication: if a document with the same SHA-256 content hash already exists in the KB, the router cascade-deletes the prior extraction (`graph_service.delete_by_source_document` + `vector_service.delete_by_source_document` + `repository.delete_document` + object_store source-prefix delete) before re-ingesting. The prior document's ID is surfaced in the receipt as `replaced_document_id`.

`DocumentReceipt.replaced_document_id: str | None` — `None` for new uploads; the replaced doc's ID for re-uploads.

### Mutating endpoint busy/pending_cleanup guard (updated 2026-05-22)

All four mutating KB endpoints — `POST /documents`, `POST /records/{kb_id}/files`, `POST /records/{kb_id}/push`, `DELETE /documents/{doc_id}`, `DELETE /{kb_id}` — guard against:
1. Active workflow: `ensure_kb_idle(kb_id, tracker=workflow_tracker)` → 409 if `is_busy=True`.
2. Pending cleanup: explicit `pending_cleanup` check on `KnowledgeBase` → 409 if `True`.

Helper: `api/_kb_busy.py` exports `KbBusyError`, `WorkflowBusyTracker` Protocol, `ensure_kb_idle`.

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
| `POST` | `/cases/promote` | `CasePromoteRequest` + `?knowledge_base_id=` | `CaseDetailResponse` | analyst |
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

class CasePromoteRequest(BaseModel):
    alert_id: str
    notes: str | None

class CaseFeedbackCreateRequest(BaseModel):
    label: Literal["suspicious","not_suspicious","insufficient_evidence"]
    evidence_adequacy: Literal["low","medium","high"]
    missing_evidence: list[str]; notes: str
```

Case routes are KB-scoped through `knowledge_base_id` query parameters in the dependency layer. `/cases/promote` rejects an alert whose stored `knowledge_base_id` does not match the query scope with 404.

---

## Evidence Packs — `/evidence-packs`

| Method | Path | Query | Response | Auth |
|--------|------|-------|----------|------|
| `GET` | `/evidence-packs/{evidence_pack_id}` | `?knowledge_base_id=` | `EvidencePackResponse` | viewer |

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

`POST .../messages?stream=true` returns SSE stream. Non-final events carry `{"token": str, "done": false}`. The final event carries `{"token": "", "done": true, "sources": list[str], "citations": list[ChatStreamCitationResponse]}`.

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
| `POST` | `/records/{kb_id}/files` | `multipart/form-data: feed=str, file=.csv/.jsonl` | `RecordIngestReceipt` - 202 fresh, 200 duplicate | analyst |
| `POST` | `/records/{kb_id}/push` | `RecordPushRequest` | `RecordIngestReceipt` - 202 fresh, 200 duplicate | analyst |

```python
class RecordPushRequest(BaseModel):
    feed_name: str    # min_length=1
    rows: list[dict[str, object]]   # min_length=1

class RecordIngestReceipt(BaseModel):
    knowledge_base_id: str; feed_name: str; record_type: str
    correlation_id: str; accepted_count: int
    duplicate: bool = False
    duplicate_count: int = 0
    rejected_count: int = 0
    rejected: list[RejectedRow] = []
    created_at: datetime
```

Fresh submissions persist accepted rows and publish `RecordsIngestedEvent` only
when `accepted_count > 0`. Byte/row-set duplicate submissions return
`duplicate=True`, `accepted_count=0`, skip persistence and event publication,
and use HTTP 200 so clients can distinguish no-op duplicates from accepted work.

---

## Workflows — `/workflows`

| Method | Path | Query | Response | Auth |
|--------|------|-------|----------|------|
| `GET` | `/workflows` | `?knowledge_base_id=&status=&limit=50&offset=0` | `WorkflowRunListResponse` | viewer |
| `GET` | `/workflows/{workflow_id}` | — | `WorkflowRunResponse` | viewer |
| `POST` | `/workflows/{workflow_id}/cancel` | — | `WorkflowRunResponse` | analyst |

```python
class WorkflowRunResponse(BaseModel):
    id: str
    workflow_type: Literal["ingestion","graph_build","analytics","monitoring"]
    status: Literal["queued","running","completed","failed","cancelled"]
    knowledge_base_id: str; started_at: datetime; updated_at: datetime
    current_step: str; last_error: str | None

class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunResponse]
    has_more: bool
    next_offset: int | None
```

---

## Analytics — `/analytics`

| Method | Path | Query | Response | Auth |
|--------|------|-------|----------|------|
| `GET` | `/analytics/risk-scores` | `?kb_id=&entity_type=&limit=` | `RiskScoreListResponse` | viewer |
| `GET` | `/analytics/timeseries` | `?kb_id=&metric=&start=&end=` | `MetricTimeseriesResponse` | viewer |
| `GET` | `/analytics/gnn/clusters` | `?kb_id=` | `GnnClusterResponse` | viewer |
| `GET` | `/analytics/overview` | — | `AnalyticsOverviewResponse` | viewer |
| `GET` | `/analytics/risk-scores/{entity_id}` | `?kb_id=` | `RiskScoreResponse` | viewer |
| `GET` | `/analytics/timeseries/{entity_id}` | `?kb_id=` | `EntityTimeseriesResponse` | viewer |

**Wiring status:** `/analytics/risk-scores`, `/analytics/timeseries`, and `/analytics/gnn/clusters` are served by analytics services from `api/dependencies.py` using empty in-memory sources by default. `/analytics/overview` is computed from durable alert, case, and KB stores. `/analytics/risk-scores/{entity_id}` and `/analytics/timeseries/{entity_id}` still use the remaining `ApiState` analytics composition, which returns unavailable/empty responses when no generated analytics exists.

### Static payload shapes (api/contracts.py)

The three dashboard/entity-scoped analytics routes (`/overview`, `/risk-scores/{entity_id}`, `/timeseries/{entity_id}`) are backed by `api/dependencies.py` factory functions that return shapes from `api/contracts.py`. These are not returned by the analytics service modules (which use `analytics/*/service_models.py`).

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

**Dependency chain for dashboard/entity-scoped routes:**
- `GET /analytics/overview` -> `get_analytics_overview_payload(alert_repository, case_service, kb_repository)` -> durable store aggregation.
- `GET /analytics/risk-scores/{entity_id}?kb_id=...` -> `get_risk_score_payload(entity_id, kb_id, state)` -> `state.get_risk_score(entity_id, knowledge_base_id=kb_id)` -> returns `RiskScoreResponse`.
- `GET /analytics/timeseries/{entity_id}?kb_id=...` -> `get_timeseries_payload(entity_id, kb_id, source, anomaly_store)` -> iterates `source.metric_names()` (`get_entity_series_source()`, a `RecordAggregateTimeSeriesSource` over `get_record_column_source()` and `DomainConfig.timeseries.metrics`), calling `source.load_series(...)` per spec until one has data, then joins persisted anomalies from `get_timeseries_anomaly_store()` -> returns `EntityTimeseriesResponse` (B2, analytics.07; no longer reads `ApiState`).

Only the risk-scores entity route still reads from `ApiState`; overview and the entity timeseries route no longer do.

---

## Real-time — `/events`, `/ws`

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `GET` | `/events/stream` | SSE stream of `RealtimeSnapshotResponse`; optional `?max_events=` | viewer |
| `WS` | `/ws/alerts` | Alert WebSocket; optional subscribe severity filter | viewer |
| `WS` | `/ws/pipeline` | Pipeline WebSocket; optional subscribe KB filter | viewer |

```python
class RealtimeSnapshotResponse(BaseModel):
    sequence: int; emitted_at: datetime
    active_alerts: int; running_workflows: int
    knowledge_base_statuses: dict[str, str]
```

---

## Investigation — `/investigation`

Last verified: 2026-06-16. Source: `backend/api/routers/investigation.py`.

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

Policy intelligence items and triage live in `api/routers/policy.py`.

| Method | Path | Query/Request | Response | Auth |
|--------|------|---------------|----------|------|
| `GET` | `/policy/items` | `?knowledge_base_id=&status=&limit=50&offset=0` | `PolicyItemListResponse` | viewer |
| `GET` | `/policy/items/{item_id}` | `?knowledge_base_id=` | `PolicyItemDetailResponse` | viewer |
| `POST` | `/policy/items/{item_id}/triage` | `PolicyTriageRequest` + `?knowledge_base_id=` | `PolicyItemDetailResponse` | analyst |

Legacy `/policy/gaps` and `/policy/briefs` routes are not registered.

## Dev/E2E Seed - `/admin/dev-seed`

Registered only when `CHILI_ENV != "production"`.

| Method | Path | Response | Auth |
|--------|------|----------|------|
| `POST` | `/admin/dev-seed` | `DevSeedResponse` | analyst |

The endpoint writes a deterministic KB, graph subgraph, alert projection, evidence pack, case, policy item, and conversation into the real repositories for local/e2e testing.

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
