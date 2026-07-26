# HTTP Route Inventory

**Generated:** 2026-05-22 (merge commit `acae4ac`)
**Reviewed:** 2026-07-26 against `backend/api/app.py::create_app()` — added `/scorecards`, `/housing`, and the conditionally mounted `/admin/dev-seed`.

All routes mounted under the FastAPI app. Role column shows `require_role` argument; routes without a `dependencies=[Depends(require_role(...))]` call are marked `public`.

---

## System / Observability

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/health` | public | Process health check; returns `{status: "ok"}` |
| `GET` | `/metrics` | `service` | Prometheus metrics endpoint |

---

## `/auth` — Authentication

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/auth/login` | public | Redirects to OIDC authorize endpoint |
| `GET` | `/auth/callback` | public | OIDC callback; sets `chiliai_session` cookie |
| `POST` | `/auth/logout` | public | Clears session cookie |
| `GET` | `/auth/me` | public (checked in handler) | Returns current `User` |

---

## `/knowledgebases` — Knowledge Base Management

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `POST` | `/knowledgebases` | `analyst` | Create KB; returns `KnowledgeBase` (201) |
| `GET` | `/knowledgebases` | `viewer` | List KBs; returns `KbListResponse` |
| `GET` | `/knowledgebases/{knowledge_base_id}` | `viewer` | Read KB detail; returns `KnowledgeBase` |
| `DELETE` | `/knowledgebases/{knowledge_base_id}` | `admin` | 5-step cascade (graph → vector → raw_records → object_store → metadata); 204 on clean delete, 207 Multi-Status on partial failure; 409 if workflow busy or `pending_cleanup` |
| `GET` | `/knowledgebases/{knowledge_base_id}/documents` | `viewer` | List KB documents; returns `DocumentListResponse` (paginated) |
| `DELETE` | `/knowledgebases/{knowledge_base_id}/documents/{document_id}` | `analyst` | Delete document metadata + object-store payloads; 204; 409 if workflow busy or `pending_cleanup` |
| `POST` | `/knowledgebases/{knowledge_base_id}/documents` | `analyst` | Upload documents, enqueue ingestion; returns `DocumentRegistrationResponse` (202); content-hash idempotent — `replaced_document_id` set when content changes; 409 if workflow busy or `pending_cleanup` |

---

## `/records` — Structured Record Ingestion

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `POST` | `/records/{knowledge_base_id}/files` | `analyst` | CSV/JSONL file upload into named feed; returns `RecordIngestReceipt` |
| `POST` | `/records/{knowledge_base_id}/push` | `analyst` | JSON array push into named feed; returns `RecordIngestReceipt` |

---

## `/alerts` — Alert Feed

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/alerts` | `viewer` | List alerts; returns `AlertListResponse` |
| `GET` | `/alerts/{alert_id}` | `viewer` | Get alert detail; returns `AlertDetailResponse` |
| `POST` | `/alerts/{alert_id}/acknowledge` | `analyst` | Acknowledge alert; returns `ApiEnvelope` |

---

## `/cases` — Investigation Cases

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/cases` | `viewer` | List cases; returns `CaseListResponse` |
| `GET` | `/cases/{case_id}` | `viewer` | Get case detail; returns `CaseDetailResponse` |
| `POST` | `/cases` | `analyst` | Create case; returns `CaseDetailResponse` |
| `PATCH` | `/cases/{case_id}` | `analyst` | Update case; returns `CaseDetailResponse` |
| `POST` | `/cases/{case_id}/feedback` | `analyst` | Add feedback; returns `CaseDetailResponse` |

---

## `/investigation` — Investigation Queries

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/investigation/entities/{entity_id}` | `viewer` | Entity detail; returns `EntityDetailResponse` |
| `GET` | `/investigation/entities/{entity_id}/neighborhood` | `viewer` | Graph neighborhood; returns `NeighborhoodResponse` |
| `GET` | `/investigation/search` | `viewer` | Entity search (kb_id + query); returns `EntitySearchResponse` |

---

## `/graph` — Graph Queries

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/graph/entities/{entity_id}` | `viewer` | Entity detail with graph context; returns `GraphEntityDetailResponse` |

---

## `/chat` — RAG Chat

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/chat/conversations/{conversation_id}` | `viewer` | Get conversation; returns `ChatConversationResponse` |
| `POST` | `/chat/conversations` | `analyst` | Create conversation; returns `ChatConversationResponse` |
| `POST` | `/chat/conversations/{conversation_id}/messages` | `analyst` | Add message; returns `ChatConversationResponse` by default or an SSE stream when `stream=true` |

---

## `/analytics` — Analytics

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/analytics/risk-scores` | `viewer` | Risk score list; returns `RiskScoreListResponse` |
| `GET` | `/analytics/timeseries` | `viewer` | Metric time-series; returns `MetricTimeseriesResponse` |
| `GET` | `/analytics/gnn/clusters` | `viewer` | GNN cluster results; returns `GnnClusterResponse` |
| `GET` | `/analytics/overview` | `viewer` | Analytics overview; returns `AnalyticsOverviewResponse` |
| `GET` | `/analytics/risk-scores/{entity_id}` | `viewer` | Entity risk score; returns `RiskScoreResponse` |
| `GET` | `/analytics/timeseries/{entity_id}` | `viewer` | Entity time-series; returns `EntityTimeseriesResponse` |

---

## `/scorecards` — Housing Scorecards

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/scorecards/templates` | `viewer` | Configured templates; returns `ScorecardTemplateListResponse` |
| `POST` | `/scorecards/runs` | `analyst` | Generate + persist a run from `ScorecardRunGenerateRequest`; returns `ScorecardRunResponse`; 404 on unknown template |
| `GET` | `/scorecards/runs` | `viewer` | List runs (`?knowledge_base_id=` required; `template_id`/`status`/`limit`/`offset` optional); returns `ScorecardRunListResponse` |
| `GET` | `/scorecards/runs/{run_id}` | `viewer` | Run detail (`?knowledge_base_id=` required); returns `ScorecardRunResponse` |
| `GET` | `/scorecards/runs/{run_id}/export` | `viewer` | Stored JSON/Markdown export (`?knowledge_base_id=` required, `?format=json\|markdown`); returns `ScorecardExportResponse` |

---

## `/housing` — Air Force Housing Dashboard

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/housing/overview` | `viewer` | Executive KPI model computed from ingested feed records; optional `period_start`/`period_end`/`knowledge_base_id` (defaults to newest KB of the active domain); returns `HousingOverviewResponse` |
| `GET` | `/housing/installations` | `viewer` | Installation list + map points (installations without coordinates appear in `items` only); same query params; returns `HousingInstallationsResponse` |

---

## `/evidence-packs` — Evidence Packs

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/evidence-packs/{evidence_pack_id}` | `viewer` | Get evidence pack; returns `EvidencePackResponse` |

---

## `/policy` — Policy Intelligence (BL-011)

All routes require `?knowledge_base_id=` (KB-scoped). Old `/policy/gaps*` and `POST /policy/briefs` routes have been removed.

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/policy/items` | `viewer` | List KB-scoped policy items; returns `PolicyItemListResponse`; optional `?status=` filter; paginated. |
| `GET` | `/policy/items/{item_id}` | `viewer` | Item detail; returns `PolicyItemDetailResponse`. |
| `POST` | `/policy/items/{item_id}/triage` | `analyst` | Triage item (accept/reject/defer/escalate); persists `PolicyDisposition`; escalate action also creates a case via `CaseService`; returns `PolicyItemDetailResponse`. |

---

## `/workflows` — Workflow History

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/workflows` | `viewer` | List workflow runs; returns `WorkflowRunListResponse` |

---

## `/events` — SSE Stream

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/events/stream` | `viewer` | Server-Sent Events workspace snapshot stream |

---

## `/config` — Domain Configuration

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `GET` | `/config/domain` | `viewer` | Active `DomainConfig` (full) |
| `GET` | `/config/features` | `viewer` | Feature flags only |
| `GET` | `/config/domain/schema` | `viewer` | JSON schema of `DomainConfig` |

---

## `/ws` — WebSocket

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `WS` | `/ws/alerts` | `viewer` | Real-time alert push |
| `WS` | `/ws/pipeline` | `viewer` | Real-time pipeline progress push |

---

## `/admin/dev-seed` — Dev/E2E Seed (conditional mount)

Registered in `create_app()` only when `CHILI_ENV != "production"` — never mounted in production.

| Method | Path | Role | Notes |
|--------|------|------|-------|
| `POST` | `/admin/dev-seed` | `analyst` | Seeds a deterministic KB, graph subgraph, alert (durable `alert_history`), evidence pack, case, policy item, and conversation into the real repositories for local/e2e testing; returns `DevSeedResponse` |
