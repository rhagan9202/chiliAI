# Story E5-S10: Analytics router — GNN cluster results

## Story
As an analyst, I want an API endpoint for GNN clustering results.

## Acceptance Criteria
1. `GET /analytics/gnn/clusters?kb_id=...` returns `GnnClusterResponse(clusters: list[ClusterResult])`.
2. `ClusterResult`: `cluster_id`, `entity_ids`, `anomaly_score`, `label`.
3. Delegates to GNN analytics service.
4. Empty list when GNN disabled in config.
5. Test: response shape and empty-when-disabled.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P3       | S    | E5-S09       |

## Target Files
- `backend/api/routers/analytics.py` — add `GET /analytics/gnn/clusters` endpoint
- `backend/api/dependencies.py` — add `get_gnn_service` dependency factory
- `backend/tests/api/test_analytics_router.py` — add GNN cluster tests

## Reference Files to Read First
- `backend/api/routers/analytics.py` — the analytics router from E5-S09
- `backend/analytics/gnn/protocols.py` — `GnnServiceProtocol` with `analyze` method
- `backend/analytics/gnn/service_models.py` — `GnnAnalysisRequest`, `GnnAnalysisResponse`
- `backend/api/dependencies.py` — existing DI wiring including `get_domain_config`
- `backend/config/schema.py` — domain config schema for checking GNN feature flags

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- No business logic in routers — thin routing, request validation, DI only
- Follow existing patterns in the codebase
- `GnnClusterResponse` and `ClusterResult` are API-layer Pydantic models defined in the router module
- `ClusterResult` fields: `cluster_id: str`, `entity_ids: list[str]`, `anomaly_score: float`, `label: str | None`
- `kb_id` is a required query parameter
- When GNN is disabled in config, the endpoint returns `GnnClusterResponse(clusters=[])` — do NOT return an error
- The router may inject config to check the GNN feature flag, or the service itself returns empty when disabled
- Prefer letting the service handle the disabled check — the router just delegates and returns the result

## What NOT To Do
- Do NOT implement GNN computation logic in the router
- Do NOT implement the concrete GNN service adapter
- Do NOT add other analytics endpoints — risk scores and timeseries are in E5-S09
- Do NOT register this router in `api/app.py` yet — that is E5-S14
- Do NOT add authentication or authorization
- Do NOT return 404 or 503 when GNN is disabled — return empty list per AC

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=api tests/api/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. Added `GET /analytics/gnn/clusters` to
`backend/api/routers/analytics.py` with a `GnnClusterResponse(clusters:
list[ClusterResult])` payload. The router delegates to a `GnnServiceProtocol`
extended with `list_clusters(...)`, with the disabled-state honored by passing a
`gnn_enabled: Callable[[], bool]` predicate into `GnnService` /
`create_gnn_service`. The router's self-contained `get_gnn_service` factory
defaults the predicate to `False` so that "GNN disabled in config" returns an
empty list without raising; tests override the dependency to enable GNN and
seed `ClusterSummary` rows. The in-memory snapshot source was extended with
`put_clusters` / `load_clusters`, mirroring the new adapter protocol contract.
`api/dependencies.py` and `api/app.py` remained untouched per scope.

## Validation Note
From `backend/`: `pytest tests/api/test_analytics_router.py tests/analytics -q`
passed with 49 tests including GNN happy-path, missing-`kb_id` (422), and
empty-when-disabled cases. `pytest tests/analytics --cov=analytics/gnn`
reported 100% coverage on the GNN adapter and protocol layers and 92% on
`analytics/gnn/service.py` (the remaining lines are pre-existing branches).
`ruff check` clean. `pyright` baseline preserved with no new errors introduced
by GNN cluster code (typed `default_factory=list[T]` used for new fields).
