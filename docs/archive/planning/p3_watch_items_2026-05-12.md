# P3 Watch Items — Runtime/API Alignment

> Created: 2026-05-12
> Scope: follow-up planning notes from the RBAC/auth and quality-gate cleanup wave.

## Confirmed and closed

- `/auth/me` is wired from the frontend through `chili_app/src/contexts/SessionContext.tsx`; this watch item is verified and does not need new implementation work.
- Knowledge-base DELETE frontend helpers now model backend `204 No Content` responses as `Promise<void>` in `chili_app/src/api/knowledgebases.ts`.

## Still watching

### Analytics dual-path

The analytics router still has two styles of data access:

- collection/service-backed routes such as `GET /analytics/timeseries` and `GET /analytics/risk-scores`;
- entity demo/read-model routes such as `GET /analytics/timeseries/{entity_id}` and `GET /analytics/risk-scores/{entity_id}` that are still served through `ApiState`.

Recommended next wave: move entity analytics routes behind analytics services/projections or explicitly mark them demo-only until the analytics module owns those read models.

### GNN clusters frontend integration

`GET /analytics/gnn/clusters` exists as a backend surface, but no production frontend page currently consumes it. Decide whether to integrate it into the dashboard/investigation route or keep it backend-only until the GNN UX is designed.

### WebSocket frontend integration

Backend WebSocket endpoints `/ws/alerts` and `/ws/pipeline` exist and are RBAC-gated. The frontend has a generic `useWebSocket` hook with tests, but no page-level alert/pipeline client currently wires those endpoints into the analyst workbench.

Recommended next wave: add page-level live clients for alert feed/dashboard/pipeline status, or mark the WebSocket endpoints as pending integration in route docs.

### ApiState partial migration

The API gateway still uses seeded `ApiState` for several read/demo surfaces: cases, RAG chat, evidence packs, graph entity details, entity-level analytics, and policy intelligence. This is acceptable for the current prototype but should not become the production state boundary.

Recommended migration order:

1. Cases, because they already represent mutable analyst workflow state.
2. RAG chat and evidence packs, because they depend on persisted KB/graph artifacts.
3. Graph entity details and entity-level analytics, because they should resolve through graph/analytics services.
4. Policy intelligence, once PKG projection ownership is finalized.
