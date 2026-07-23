# analytics backlog

> **Scope:** Timeseries anomaly detection, GNN link prediction/clustering, risk scoring, explainability, metrics — plus §14.2 model training pipeline.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

## Story analytics.01: Define analytics inference protocol and baseline adapter

**ID:** analytics.01
**Status:** planned
**Prerequisites:** [graph.04, graph.10, ingestion.11, llm.01]
**Unblocks:** [analytics.31]
**Estimated size:** L

### Narrative
As an analyst,
I want a backend analytics inference interface with a deterministic baseline implementation,
so that graph-derived scores can be consumed before a production GNN runtime is selected.

### Current State
Graph storage and workflows exist, but analytics inference is still represented by planned backlog work rather than an executable service contract.

### Acceptance Criteria
- [ ] Define an analytics inference protocol for node, edge, and subgraph scoring requests.
- [ ] Implement a deterministic baseline adapter that can run without GPU or optional ML libraries.
- [ ] Expose service-layer methods that return typed scores with provenance and model metadata.
- [ ] Document the adapter boundary so a PyG/DGL implementation can replace the baseline.

### Verification
- [ ] Unit tests cover request validation, deterministic scoring, and provenance output.
- [ ] Contract tests prove the baseline adapter satisfies the inference protocol.

### Code touch points
- `backend/app/analytics/**`
- `backend/tests/analytics/**`
- `docs/wiki/modules/analytics.md`

---
## Story analytics.02: GNN: Persist trained model artifacts and serve from durable storage
**ID:** analytics.02
**Status:** planned
**Prerequisites:** [analytics.23, storage.01]
**Unblocks:** []
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** `GnnService` to load trained model artifacts (weights, scaler, label maps) from the model registry instead of recomputing Louvain/spectral embeddings per `analyze()` call,
**so that** inference latency is bounded and the same model version produces reproducible results across worker restarts.

### Current State
- `GnnService.analyze` runs `_detect_communities` (Louvain) and `_compute_embeddings` (spectral) on every call (`backend/analytics/gnn/service.py:63-146`).
- `InMemoryGraphSnapshotSource` (`backend/analytics/gnn/adapters/in_memory.py:11-44`) caches snapshots only; nothing caches model artifacts.
- No `model_artifact_id`/`model_version` field is read from `DomainConfig.analytics` and no artifact loader exists in `backend/analytics/gnn/`.

### Acceptance Criteria
- [ ] New `GnnModelLoader` (or analogous adapter) in `backend/analytics/gnn/adapters/` resolves a `model_artifact_id` from the registry (analytics.23) and pulls weights via the object-store protocol.
- [ ] `GnnService.__init__` accepts an optional `GnnModelLoader`; when provided, `analyze()` reuses the cached inference object instead of recomputing communities/embeddings.
- [ ] Cache invalidation is keyed on `(model_artifact_id, knowledge_base_id, snapshot_revision)` and is exercised by a unit test that toggles versions and asserts a fresh load.
- [ ] `DomainConfig.analytics.gnn_model_artifact_id` is optional; absence falls back to the heuristic path (analytics.01).
- [ ] Coverage ≥ 85% on `backend/analytics/gnn/service.py` and the new loader module.

### Verification
- `pytest backend/tests/analytics/gnn -q` green.
- Unit test mounts a stub `GnnModelLoader`, calls `analyze` twice, and asserts the loader is invoked once.
- `pyright` clean.

### Code touch points
- `backend/analytics/gnn/adapters/model_loader.py` (new)
- `backend/analytics/gnn/service.py` (modify)
- `backend/analytics/gnn/protocols.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/tests/analytics/gnn/test_model_loader.py` (new)

---

## Story analytics.03: GNN: Add Neo4j/graph-backed `GraphSnapshotSourceProtocol` adapter
**ID:** analytics.03
**Status:** done
**Prerequisites:** [graph.06]
**Unblocks:** [analytics.04]
**Estimated size:** L
**Done:** 2026-07-16 · Sprint 2026-28 B1 (GNN live) · `feat/sprint-2026-28-b1-gnn-live`

**As a** fraud-analytics engineer,
**I need** a graph-DB-backed `GraphSnapshotSource` that loads nodes + edges from Neo4j (and the in-memory backend) for a knowledge base,
**so that** `GnnService.analyze` can run against real ingested graphs rather than only what tests put into the in-memory source.

### Current State (shipped)
- `GraphRepositorySnapshotSource` (`backend/analytics/gnn/adapters/graph_repository_source.py`) reads `repository.get_entities`/`get_relationships` for a `knowledge_base_id` and assembles a bounded `GraphSnapshot` — degree-weighted numeric features per node, clamped/weighted edges — against **any** `GraphRepository` implementation (in-memory or Neo4j), so it is not Neo4j-specific.
- Both the worker (`agent.coordinator.build_graph_snapshot_source`) and the API (`api.dependencies.get_graph_snapshot_source`) construct this adapter unconditionally over the already-configured `GraphRepository`, so backend selection continues to flow through the single existing `DomainConfig.graph.backend` setting rather than a second GNN-specific literal.
- `load_clusters` delegates to `ClusterSummaryStoreProtocol` (in-memory or object-store), returning `[]` when nothing has been persisted for the KB yet.
- Live-Neo4j coverage: `backend/tests/analytics/gnn/test_gnn_live_integration.py::test_gnn_snapshot_source_round_trips_live_neo4j` (`@pytest.mark.integration`) seeds a KB through a real `Neo4jGraphRepository`, loads a snapshot, and runs `GnnService.analyze` end to end.

### Acceptance Criteria
- [x] A graph-repository-backed snapshot source assembles `GraphSnapshot` instances bounded by an explicit `max_nodes` parameter. **Deviation:** shipped as `GraphRepositorySnapshotSource` at `backend/analytics/gnn/adapters/graph_repository_source.py` (not `graph_backed.py`) and bounds via client-side top-degree truncation over a full-KB read (`get_entities`/`get_relationships`), not a paginated/iterator push-down at the graph query layer — `graph.06`'s streaming surface was never a hard prerequisite in practice; the `DomainConfig.gnn.snapshot_max_nodes` cap (default 5000, see analytics.04) keeps this bounded for the sprint's KB sizes.
- [x] `load_clusters` reads persisted cluster summaries when present, empty list otherwise. **Deviation:** reads from a dedicated `ClusterSummaryStoreProtocol` (in-memory/object-store adapters in `backend/analytics/gnn/adapters/cluster_store.py`), not from `cluster_id`/`anomaly_score` properties written onto graph entities by an analytics.24-style handler — see analytics.05 for why this path was chosen.
- [x] Backend selection is config-driven. **Deviation:** no `DomainConfig.analytics.gnn_snapshot_backend` literal was added; instead both factories (`build_graph_snapshot_source`, `get_graph_snapshot_source`) always wrap the already-injected `GraphRepository`, so switching `DomainConfig.graph.backend` between `in_memory`/`neo4j` is sufficient — one config surface instead of two that could drift out of sync.
- [x] Coverage ≥ 85% on the new adapter (integration test marked `@pytest.mark.integration` for the Neo4j path). `analytics/gnn/adapters/graph_repository_source.py` is at 97% line coverage; the live-Neo4j round trip is covered by `test_gnn_live_integration.py`.

### Verification
- `pytest -m "not integration" backend/tests/analytics/gnn` green.
- `pytest -m integration backend/tests/analytics/gnn/test_gnn_live_integration.py` green against the dev Neo4j stack (renamed from the originally planned `test_graph_backed_source.py`).
- `pyright` clean.

### Code touch points
- `backend/analytics/gnn/adapters/graph_repository_source.py` (new — planned as `graph_backed.py`)
- `backend/analytics/gnn/adapters/cluster_store.py` (new — in-memory + object-store `ClusterSummaryStoreProtocol` adapters)
- `backend/agent/coordinator.py` (modify — `build_graph_snapshot_source`)
- `backend/api/dependencies.py` (modify — `get_graph_snapshot_source`)
- `backend/config/schema.py` (modify — `DomainConfig.gnn.snapshot_max_nodes`, not a backend literal)
- `backend/tests/analytics/gnn/test_gnn_live_integration.py` (new — planned as `test_graph_backed_source.py`)

---

## Story analytics.04: GNN: Stream and bound large-graph analysis
**ID:** analytics.04
**Status:** planned
**Prerequisites:** [analytics.03, graph.06, _observability.04]
**Unblocks:** [_plugins.09]
**Estimated size:** L
**As a** worker operator,
**I need** GNN analysis to stay within bounded memory on production-sized KBs (no full Laplacian, no O(n²) link prediction),
**so that** worker pods do not OOM when a KB exceeds a few thousand nodes.

> **Delivered slice (Sprint 2026-28 B1, 2026-07-16, `feat/sprint-2026-28-b1-gnn-live`):** the snapshot-loading half of this story shipped: `GraphRepositorySnapshotSource` (`backend/analytics/gnn/adapters/graph_repository_source.py`) bounds the node set it hands to `GnnService` via `DomainConfig.gnn.snapshot_max_nodes` (default 5000) — entities are ranked by degree and only the top-`max_nodes` are kept, with the drop count logged as a warning (`"GNN snapshot truncated for kb=%s..."`). This bounds the *input* to `analyze()`. It does **not** address the two algorithmic complexity items below, which remain open: `_compute_embeddings`'s full `node_count × node_count` Laplacian + dense `np.linalg.eigh` (still O(n³) time / O(n²) memory once inside the 5000-node cap) and `_predict_links`'s O(n²) all-pairs double loop. No per-stage memory/duration counters were added. Story stays `planned` until those are done; do not re-close without addressing them.

### Current State
- `_compute_embeddings` materializes a full `node_count × node_count` Laplacian and calls `np.linalg.eigh` — O(n³) time and O(n²) memory (`backend/analytics/gnn/service.py:287-345`).
- `_predict_links` is O(n²) double-loop over all node pairs (`backend/analytics/gnn/service.py:214-237`).
- `GraphRepositorySnapshotSource` now caps the *node count fed into* the above two functions at `DomainConfig.gnn.snapshot_max_nodes` (default 5000) — see delivered-slice note above — but does not change their per-call complexity.
- No per-stage memory metric is emitted.

### Acceptance Criteria
- [ ] `GnnAnalysisRequest` gains `max_nodes: int = 5000` (or similar) and `analyze()` raises `GnnInsufficientGraphError` (or new `GnnGraphTooLargeError`) when the source returns more nodes. **Partially delivered differently:** the cap lives on `DomainConfig.gnn.snapshot_max_nodes` (source-side truncation with a logged warning), not on `GnnAnalysisRequest` (caller-side rejection) — `analyze()` never sees more than `max_nodes` and never raises for an oversized graph; it silently analyzes the top-degree subset instead. Still open: an explicit reject-vs-truncate policy choice, and a request-level override.
- [ ] `_compute_embeddings` is replaced by a sparse-matrix path (`scipy.sparse.linalg.eigsh` with `k=dimension`) so memory is O(n·k) rather than O(n²). **Not delivered.**
- [ ] `_predict_links` is replaced by approximate nearest-neighbor candidate selection (e.g. FAISS / annoy or a degree-capped neighborhood) and is documented in the README. **Not delivered.**
- [ ] Per-stage memory / duration counters emitted via the observability primitive from `_observability.04`. **Not delivered.**

### Verification
- `pytest backend/tests/analytics/gnn/test_service.py -q` green.
- New benchmark test asserts peak RSS stays below a configurable cap on a 5 000-node synthetic graph.
- `pyright` clean.

### Code touch points
- `backend/analytics/gnn/service.py` (modify)
- `backend/analytics/gnn/service_models.py` (modify)
- `backend/analytics/gnn/exceptions.py` (modify)
- `backend/tests/analytics/gnn/test_large_graph.py` (new)

---

## Story analytics.05: GNN: Surface in-graph `ClusterSummary` persistence
**ID:** analytics.05
**Status:** done
**Prerequisites:** [analytics.24]
**Unblocks:** []
**Estimated size:** M
**Done:** 2026-07-16 · Sprint 2026-28 B1 (GNN live) · `feat/sprint-2026-28-b1-gnn-live`

**As a** fraud analyst,
**I need** `GET /analytics/gnn/clusters` to return clusters derived from the graph (written back by the self-reinforcing loop) rather than only what tests stuff into the in-memory source,
**so that** cluster summaries are durable across worker restarts and reflect the latest analyze run.

### Current State (shipped)
- `GnnService.list_clusters` reads `_snapshot_source.load_clusters` (`backend/analytics/gnn/service.py:149-169`), unchanged.
- Flow B (`agent.coordinator.handle_graph_updated_for_analytics`) persists each successful GNN stage's community results through `_persist_gnn_clusters` immediately after `_run_gnn_stage` returns, writing one `ClusterSummary` per detected community (`cluster_id=community_id`, `entity_ids=member_entity_ids`, `anomaly_score` = the max scored-node score among the community's members) to a `ClusterSummaryStoreProtocol`.
- Both API and worker build an `ObjectStoreClusterSummaryStore` over the configured object store (`system/analytics/gnn_clusters/<kb>.json`), so `/analytics/gnn/clusters` now serves real, durable, worker-restart-surviving pipeline output instead of only whatever a test pushed into an in-memory fixture. An empty `communities` list still writes — it honestly replaces stale clusters rather than leaving them stranded.
- Store failures are logged as a warning and never fail the pipeline (`_persist_gnn_clusters`'s `except Exception` guard).
- Prerequisite analytics.24's write-back (`community_id`/`centrality_score` properties written directly onto graph entities) also exists and predates this story — see analytics.24's delivered-slice note; the two mechanisms are complementary, not the same one: entity properties support per-entity graph queries/exports, while the `ClusterSummary` store is what `/analytics/gnn/clusters` actually reads.

### Acceptance Criteria
- [x] Cluster summaries are durable and reflect the latest `analyze()` run rather than only in-memory-source fixtures. **Deviation:** delivered via a dedicated `ClusterSummaryStoreProtocol` (`backend/analytics/gnn/adapters/cluster_store.py`, in-memory + object-store adapters) populated by Flow B's `_persist_gnn_clusters`, not by `GraphRepositorySnapshotSource.load_clusters` reading `cluster_id`/`anomaly_score` graph-entity properties written by an analytics.24 handler. The object-store path was chosen because "all entities carrying a given `cluster_id`" is not a query the graph protocols expose without a full scan, whereas the analyze-time community list is already grouped and cheap to persist as one small per-KB record.
- [x] When no clusters exist, `list_clusters` returns an empty list (no error). Covered by `test_gnn_service_list_clusters_returns_empty_when_disabled` (capability off) and both cluster-store adapters' "unseeded KB" tests in `backend/tests/analytics/gnn/test_cluster_store.py`.
- [x] Coverage ≥ 85% on the read path — `analytics/gnn/adapters/cluster_store.py` and `analytics/gnn/adapters/graph_repository_source.py` are both ≥ 97% line coverage; `GnnService.list_clusters` is exercised by `backend/tests/analytics/gnn/test_service.py`.

### Verification
- `pytest backend/tests/analytics/gnn -q` green (28 tests, includes `test_cluster_store.py`, `test_graph_repository_source.py::test_load_clusters_delegates_to_store`, and the live-Neo4j round trip). **Deviation:** no test named exactly `test_list_clusters_from_graph` — coverage is spread across the files above instead of one named test.
- Manual/live integration: `backend/tests/analytics/gnn/test_gnn_live_integration.py` runs a real GNN `analyze()` against a live-Neo4j-seeded KB and asserts `>=1` community is produced; the full manual "ingest → cluster persists → `GET /analytics/gnn/clusters` returns it" loop is exercised by the controller's Step 5 live demo pass (Sprint 2026-28 B1 task 6).

### Code touch points
- `backend/analytics/gnn/adapters/cluster_store.py` (new)
- `backend/agent/coordinator.py` (modify — `_persist_gnn_clusters`, Flow B wiring)
- `backend/api/dependencies.py` (modify — `get_graph_snapshot_source` cluster-store wiring)
- `backend/tests/analytics/gnn/test_cluster_store.py`, `test_graph_repository_source.py`, `test_gnn_live_integration.py` (new/modified)

---

> **Delivered pipeline slice (Sprint 2026-28 B2, BL-047, 2026-07-18,
> `feat/sprint-2026-28-b2-timeseries-anomalies`):** ingest-triggered
> self-history timeseries anomaly detection shipped end to end, superseding
> analytics.06's original approach (below) and closing analytics.07. The
> slice spans: `TimeseriesMetricSpec` + `TimeseriesAnalyticsConfig` on
> `DomainConfig.timeseries` with cross-reference validation against records
> feeds (`backend/config/schema.py`); the anomaly store
> (`TimeseriesAnomalyRecord` + `TimeseriesAnomalyStoreProtocol`, in-memory +
> Postgres adapters, migration `0011_timeseries_anomalies.py`); the
> record-aggregate per-entity series source
> (`backend/analytics/timeseries/adapters/record_aggregates.py`,
> `RecordAggregateTimeSeriesSource`); the worker stage `run_timeseries_stage`
> (`backend/agent/coordinator.py`), gated on `capabilities.timeseries`,
> running best-effort immediately after — but independently of — the
> peerstats stage on every `RecordsIngestedEvent`, with controlled skips for
> per-entity insufficient history (`TimeseriesInsufficientHistoryError`) and
> per-spec configuration errors (`TimeseriesConfigurationError`, e.g. a
> missing detection-strategy extra), z-score clamping at `1.0e6`, and
> `timeseries_anomaly:<spec.name>`-prefixed `DerivedRiskSignal` writes with
> peer group key `__self_history__`; the KB-delete cascade step
> `timeseries_anomalies` (structural `TimeseriesAnomalyPurger` protocol,
> positioned directly after `derived_signals`, required in both the API and
> worker `KbDeletionStores` bundles); the API route rewrite covered by
> analytics.07 below; and config-only pack additions (`peer_stats` +
> `timeseries` blocks on `medicare_fraud_cms_desynpuf.yaml`, a `timeseries`
> block on `department_air_force_housing.yaml`). Full design rationale:
> `docs/superpowers/specs/2026-07-17-sprint28-b2-timeseries-anomalies-design.md`.
> Full task-by-task implementation record:
> `docs/superpowers/plans/2026-07-17-sprint28-b2-timeseries-anomalies.md`.
> Gates at closeout: 2612 backend tests passed (5 skipped, 97% coverage),
> `pyright` 0 errors, `ruff check` clean.

## Story analytics.06: Timeseries: Add Postgres `load_series` for per-entity metrics
**ID:** analytics.06
**Status:** dropped
**Prerequisites:** [monitoring.02, records.07]
**Unblocks:** []
**Estimated size:** M
**As a** fraud-analytics engineer,
**I need** `TimeSeriesHistorySource.load_series` to return per-entity series populated by the monitoring/records `observations` write path, not only graph-scope metrics keyed on the `__graph__` sentinel,
**so that** per-entity anomaly detection runs against real observation streams.

### Current State
**Superseded 2026-07-18 (Sprint 2026-28 B2, BL-047) — dropped, not implemented
as specced.** Per-entity anomaly detection did ship (B2), but on a different
series source than this story's AC assumed. Plan-time evidence (design
amendment, `docs/superpowers/specs/2026-07-17-sprint28-b2-timeseries-anomalies-design.md`
§2) rejected the `observations`-backed path this story specified:
`MonitoringObservation.score` is hard-bounded `[0,1]` with load-time
provability (raw payment fields have no `max_value` to bound against),
`observed_at` is pinned to `ingested_at` (a bulk demo ingest collapses the
time axis to one point per feed run), and the `(kb, entity, metric,
observed_at)` primary key + `ON CONFLICT DO NOTHING` silently drops
same-day duplicate claims. Instead, `RecordAggregateTimeSeriesSource`
(`backend/analytics/timeseries/adapters/record_aggregates.py`) reads
per-entity, per-interval aggregates directly from `raw_records` via the
existing peerstats `RecordColumnSourceProtocol.load_interval_aggregates`
SQL — a real claim-date axis, unbounded values, no lossy collisions.
`observations` remains monitoring-only (`monitoring/adapters/postgres.py::PostgresObservationStore`
+ monitoring's own threshold evaluation); the timeseries module never reads
it. The cross-edge contract (per-entity ← `raw_records` aggregates,
graph-scope ← `entity_metric_history`, `observations` ← monitoring-only) is
documented in `backend/analytics/README.md` § Timeseries series-source
contract. See analytics.07 for the API-facing half of the delivered slice
and `docs/backlog/README.md`'s regenerated rollup for this story's `dropped`
accounting.

Pre-supersession state (accurate as of 2026-07-17, retained for history):
- `PostgresTimeSeriesHistorySource._SERIES_SQL` selects from `entity_metric_history` (`backend/analytics/timeseries/adapters/postgres.py:17-30`).
- `entity_metric_history` is only written by Flow 2 with `entity_id="__graph__"` (`backend/analytics/metrics/models.py:11-16`, `backend/agent/coordinator.py:1096-1300`).
- Per-entity observations land in `observations` via `monitoring/adapters/postgres.py::PostgresObservationStore`, but the timeseries adapter does not read them.

### Acceptance Criteria
- [ ] `PostgresTimeSeriesHistorySource` gains an `observations`-backed path (separate adapter or branch) keyed on `(knowledge_base_id, entity_id, metric_name)` and selected via `DomainConfig.analytics.timeseries_source: Literal["entity_metric_history","observations"]`. **Superseded** — see Current State; no `timeseries_source` literal was added, and `PostgresTimeSeriesHistorySource` still reads only `entity_metric_history` (graph-scope). Per-entity reads go through `RecordAggregateTimeSeriesSource` instead.
- [ ] Cross-edge contract is documented in `backend/analytics/README.md` (per-entity timeseries reads `observations`, graph-scope reads `entity_metric_history`). **Delivered with a different contract:** per-entity timeseries reads `raw_records` aggregates, not `observations`; `backend/analytics/README.md` § Timeseries series-source contract documents the shipped contract.
- [ ] Coverage ≥ 85% on the new branch; integration test runs against a Postgres fixture with seeded observation rows. **N/A** — no `observations`-backed branch was built; coverage for the shipped `record_aggregates.py` path is tracked under analytics.07 instead.

### Verification
- `pytest -m integration backend/tests/analytics/timeseries/test_postgres_source.py -q` green.
- Manual: insert a sample observation, call `/analytics/timeseries?...` against a Postgres-backed deployment, observe the row.
- `pyright` clean.

### Code touch points
- `backend/analytics/timeseries/adapters/postgres.py` (modify)
- `backend/analytics/timeseries/adapters/observations.py` (new) *or* branch in postgres.py
- `backend/config/schema.py` (modify)
- `backend/analytics/README.md` (modify)
- `backend/tests/analytics/timeseries/test_postgres_source.py` (modify)

---

## Story analytics.07: Timeseries: Wire production `PostgresTimeSeriesHistorySource` through API DI
**ID:** analytics.07
**Status:** done
**Prerequisites:** [database.05]
**Unblocks:** [analytics.08, analytics.35]
**Estimated size:** S
**Done:** 2026-07-18 · Sprint 2026-28 B2 (timeseries anomalies) · `feat/sprint-2026-28-b2-timeseries-anomalies`
**As a** API developer,
**I need** `get_timeseries_history_source()` to select the Postgres adapter when `DomainConfig.database.backend == "postgres"`,
**so that** `/analytics/timeseries` reads from the same hypertable that Flow 2 writes to, instead of always returning empty in-memory data.

### Current State (shipped)
- `get_timeseries_history_source` (`backend/api/dependencies.py`) now mirrors `get_risk_signal_source`'s DI-switch pattern: `PostgresTimeSeriesHistorySource(provider)` when `get_connection_provider()` is non-None, else `InMemoryTimeSeriesHistorySource()`.
- **Deviation (scope grew with B2):** the same task also rewrote the entity-scoped `GET /analytics/timeseries/{entity_id}` route (previously `ApiState.get_timeseries`, the seeded-data shortcut tracked separately under analytics.28) to read from `get_entity_series_source()` — a `RecordAggregateTimeSeriesSource` over `get_record_column_source()` (new DI-switched accessor, same pattern) and `DomainConfig.timeseries.metrics` — joined with persisted anomalies from `get_timeseries_anomaly_store()` (shipped by the same sprint's earlier task). This closed the timeseries half of analytics.28; the risk-score half closed later in the same sprint (Task 9 defect #5 fix, commit `42ef186`) — analytics.28 is now done. `api/state.py`'s seeded `_timeseries_source`/`_timeseries_service`/`get_timeseries` were deleted (dead code once the route stopped calling them).

### Acceptance Criteria
- [x] `get_timeseries_history_source` returns `PostgresTimeSeriesHistorySource(provider)` when the connection provider is non-None.
- [x] An override hook (DI dependency override) lets tests inject the in-memory adapter without env shenanigans — `app.dependency_overrides[get_timeseries_history_source]`/`get_entity_series_source`/`get_timeseries_anomaly_store`, plus direct `lru_cache`-clear + `monkeypatch.setattr(dependencies, "get_connection_provider", ...)` for unit-level backend-selection tests (see `tests/api/test_risk_signal_source_wiring.py` for the established pattern; not duplicated for these new accessors since the Postgres branch is otherwise consistent with every other DI-switch factory in the module — exercised via `-m integration`, not unit tests).
- [x] A request-level integration test demonstrates `/analytics/timeseries?kb_id=…` returning seeded Postgres rows. **Closed at Task 8 closeout (2026-07-18):** `test_query_timeseries_returns_seeded_postgres_rows` (`backend/tests/api/test_analytics_router.py`, `@pytest.mark.integration`) seeds `entity_metric_history` via `PostgresEntityMetricRepository`, builds a real `PostgresTimeSeriesHistorySource` + `TimeseriesService` over it, and asserts `GET /analytics/timeseries?kb_id=…&metric=…` returns the seeded rows through a `TestClient` request — the AC's original gap (adapter-level coverage only, no request-level proof) is closed.

### Verification
- `pytest backend/tests/api/test_analytics_router.py -q` green (23 passed — the original 21, plus the entity route's record-aggregate + anomaly join, its unavailable-when-no-data path, and the Task 8 closeout's request-level Postgres integration test).
- `pytest backend/tests/api -q` green (612 passed at Task 6/7; re-verified green in the full `make test` run at Task 8 closeout — 2612 passed, 5 skipped, 97% coverage).
- `pyright` clean, `ruff check` clean.

### Code touch points
- `backend/api/dependencies.py` (modify)
- `backend/api/state.py` (modify — deleted seeded timeseries composition)
- `backend/tests/api/test_analytics_router.py` (modify)
- `backend/tests/api/test_phase5_stateful_routes.py`, `backend/tests/api/test_read_model_routers.py` (modify — updated tests that asserted the removed seeded timeseries content)

---

## Story analytics.08: Timeseries: Add forecasting/probabilistic models alongside detection
**ID:** analytics.08
**Status:** planned
**Prerequisites:** [analytics.07, config.01]
**Unblocks:** []
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** a forecasting strategy (Prophet/ARIMA or equivalent) that returns expected vs observed deltas usable by risk scoring,
**so that** risk signals can incorporate predicted-vs-actual deviations instead of relying only on z-score / STL / isolation-forest anomaly tagging.

### Current State
- `DetectionStrategy` is `Literal["z_score","stl_decomposition","isolation_forest"]` (`backend/analytics/timeseries/service_models.py:11`).
- `TimeseriesService._dispatch_detection` (`backend/analytics/timeseries/service.py:168-195`) dispatches only those three.
- No forecasting helper or `predict_next` surface exists; risk signals therefore cannot consume predicted vs observed deltas.

### Acceptance Criteria
- [ ] `DetectionStrategy` gains a `forecast` value (or a parallel `ForecastingStrategy` literal) backed by Prophet or statsmodels ARIMA via a lazy optional import.
- [ ] New `TimeseriesService.forecast(request) -> TimeseriesForecastResponse` returning `expected_value`/`upper_bound`/`lower_bound` per observation.
- [ ] `DomainConfig.analytics.forecasting_backend` config field selects the strategy and is validated cross-field.
- [ ] `RiskSignal` examples in `backend/tests/analytics/risk/test_service.py` add at least one forecasting-derived signal to exercise the integration path.

### Verification
- `pytest backend/tests/analytics/timeseries -q` green.
- Integration test marked `@pytest.mark.integration` exercises the Prophet/ARIMA dependency when installed.
- `pyright` clean.

### Code touch points
- `backend/analytics/timeseries/service.py` (modify)
- `backend/analytics/timeseries/service_models.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/analytics/timeseries/` (modify)

---

## Story analytics.09: Risk: Replace linear weighted-sum strategy with ML-backed scorers
**ID:** analytics.09
**Status:** planned
**Prerequisites:** [analytics.23, config.01]
**Unblocks:** []
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** a learned scoring strategy (e.g. gradient-boosted classifier) selectable behind `RiskScoringStrategyProtocol`,
**so that** risk scores reflect calibrated weights derived from labeled training data instead of a flat normalized linear combination.

### Current State
- `LinearScoringStrategy.score` does `min(1.0, (signal.value * signal.weight) / total_weight)` (`backend/analytics/risk/adapters/linear_strategy.py:8-22`).
- `RiskScoringStrategyProtocol` (`backend/analytics/risk/protocols.py:25-29`) is pluggable but no ML adapter exists.
- `RiskService` always constructs `LinearScoringStrategy()` when none is injected (`backend/analytics/risk/service.py:42-50`).

### Acceptance Criteria
- [ ] `BoostedRiskScoringStrategy` (or named alternative) lives under `backend/analytics/risk/adapters/` with lazy XGBoost/lightgbm import behind an optional extra.
- [ ] Strategy loads its model via the model registry (analytics.23); missing artifact raises `RiskConfigurationError`.
- [ ] `DomainConfig.analytics.risk_strategy: Literal["linear","boosted"]` selects the active strategy.
- [ ] Coverage ≥ 85% on the new strategy adapter.

### Verification
- `pytest backend/tests/analytics/risk -q` green.
- Integration test loads a tiny pretrained model fixture and asserts contributions differ from the linear baseline.
- `pyright` clean.

### Code touch points
- `backend/analytics/risk/adapters/boosted_strategy.py` (new)
- `backend/analytics/risk/protocols.py` (modify)
- `backend/analytics/risk/service.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/tests/analytics/risk/test_boosted_strategy.py` (new)

---

## Story analytics.10: Risk: Add graph-derived and vectorstore-derived `RiskSignalSource` adapters
**ID:** analytics.10
**Status:** planned
**Prerequisites:** [graph.05, vectorstore.07]
**Unblocks:** [analytics.11, analytics.12]
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** production `RiskSignalSource` adapters that derive signals from the graph (degree, centrality, neighborhood risk) and the vectorstore (similarity to known-bad clusters),
**so that** assessments reflect real entity context instead of in-memory seeded signals.

### Current State
- `RiskSignalSourceProtocol` carries a `TODO(production)` for graph + vectorstore signal computation (`backend/analytics/risk/adapters/protocols.py:14-17`).
- `InMemoryRiskSignalSource` and `PostgresRiskSignalSource` exist. The Postgres source reads `entity_derived_signals` for profiles and `risk_score_history` for ranked lists/history (`backend/analytics/risk/adapters/postgres.py`).
- `get_risk_signal_source` selects `PostgresRiskSignalSource(provider)` when a connection provider exists, otherwise `InMemoryRiskSignalSource()` (`backend/api/dependencies.py`).
- Graph-derived and vectorstore-derived signal adapters are still not implemented.

### Acceptance Criteria
- [ ] `GraphRiskSignalSource` adapter at `backend/analytics/risk/adapters/graph_backed.py` consumes `GraphServiceProtocol.get_subgraph` (graph.05) to compute degree / neighborhood-risk signals.
- [ ] `VectorRiskSignalSource` adapter consumes `VectorServiceProtocol` filtered search (vectorstore.07) to derive similarity-to-known-bad signals.
- [ ] `CompositeRiskSignalSource` fuses multiple sources behind one `RiskSignalSourceProtocol`.
- [ ] `get_risk_signal_source` selects the composite when `DomainConfig.database.backend == "postgres"` (production) and the in-memory adapter otherwise (or per `DomainConfig.analytics.risk_signal_backend`).

### Verification
- `pytest backend/tests/analytics/risk/test_composite_source.py -q` green.
- Integration test exercises graph + vector signals end-to-end with a seeded Neo4j + Qdrant fixture.
- `pyright` clean.

### Code touch points
- `backend/analytics/risk/adapters/graph_backed.py` (new)
- `backend/analytics/risk/adapters/vector_backed.py` (new)
- `backend/analytics/risk/adapters/composite.py` (new)
- `backend/api/dependencies.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/analytics/risk/` (add)

---

## Story analytics.11: Risk: Back `RiskSignalSource` reads with Postgres history
**ID:** analytics.11
**Status:** planned
**Prerequisites:** [analytics.10, database.05]
**Unblocks:** [analytics.16]
**Estimated size:** M
**As a** fraud-analytics engineer,
**I need** `RiskSignalSourceProtocol.load_historical_score` to read the Postgres `risk_score_history` table via the existing `PostgresRiskHistoryStore` instead of an in-memory dict,
**so that** trend computation survives restarts and is sourced from the durable Plan C log.

### Current State
- `PostgresRiskSignalSource.load_historical_score(...)` reads the latest score from `risk_score_history`.
- `PostgresRiskSignalSource.list_ranked_entries(...)` also ranks entities from `risk_score_history`.
- `get_risk_signal_source` returns `PostgresRiskSignalSource(provider)` when a DB connection provider exists.
- **PM status note (2026-06-23):** the implementation is **substantially shipped** (3 of 4 AC checked; `PostgresRiskSignalSource` verified at `backend/analytics/risk/adapters/postgres.py`, wired in `api/dependencies.py`). Only the live-DB round-trip test remains. Kept `planned` (not `in-progress`) because the validator requires prerequisites `done` for `in-progress` and `analytics.10`/`database.05` are not yet done.

### Acceptance Criteria
- [x] `PostgresRiskSignalSource` routes `load_historical_score` through `risk_score_history`.
- [x] Unit coverage asserts `load_historical_score` returns the latest score and wraps DB errors.
- [ ] A live-DB round-trip test inserts an assessment via the writer and reads it back through `PostgresRiskSignalSource`.
- [x] `backend/analytics/peerstats/README.md` and analytics wiring docs reflect the Postgres-derived signal/history path.

### Verification
- Covered by `backend/tests/analytics/risk/test_postgres_signal_source.py`.

### Code touch points
- `backend/analytics/risk/adapters/composite.py` (modify) *or* `backend/analytics/risk/adapters/postgres_signal.py` (new)
- `backend/api/dependencies.py` (modify)
- `backend/analytics/README.md` (modify)
- `backend/tests/analytics/risk/test_postgres_history.py` (new)

---

## Story analytics.12: Risk: Promote graph-native history nodes alongside the entity-property snapshot
**ID:** analytics.12
**Status:** planned
**Prerequisites:** [analytics.10, graph.02, agent.13]
**Unblocks:** [monitoring.06]
**Estimated size:** L
**As a** investigator,
**I need** historical risk assessments to appear as graph-native nodes (linked to entities by a typed relationship) in addition to the flat `risk_score`/`risk_level`/`risk_assessed_at` properties,
**so that** investigation queries can traverse history without leaving the graph.

### Current State
- `handle_risk_scored_for_graph` (`backend/agent/coordinator.py:1478-1530`) only sets flat properties via `GraphService.update_entity_properties`.
- Graph-native history nodes are explicitly deferred per Plan C deviations (`docs/architecture.md:716`).

### Acceptance Criteria
- [ ] New `RiskAssessmentNode` entity type (or shared-types extension) carries `score`, `level`, `assessed_at`, `request_id`.
- [ ] `handle_risk_scored_for_graph` upserts the node and a `HAS_ASSESSMENT` relationship while keeping the flat properties for current-state reads.
- [ ] Idempotency: re-deliveries do not create duplicate nodes (keyed on `request_id`).
- [ ] Documentation in `backend/agent/AGENT.md` updated to describe the dual write path.

### Verification
- `pytest backend/tests/agent/test_handle_risk_scored.py -q` green.
- Integration test exercises the dual write against a seeded Neo4j fixture and asserts a single node per request_id after redelivery.

### Code touch points
- `backend/agent/coordinator.py` (modify)
- `backend/shared/types.py` (modify, if a new typed entity is preferred over a free-form `Entity(type=...)`)
- `backend/tests/agent/test_handle_risk_scored.py` (modify)
- `backend/agent/AGENT.md` (modify)

---

## Story analytics.13: Explainability: Generate LLM narrative reasoning beyond join-of-rationales
**ID:** analytics.13
**Status:** done
**Prerequisites:** [llm.06, analytics.16]
**Unblocks:** []
**Estimated size:** M
**Done:** 2026-07-23 · Sprint 2026-28 B3 (explainability engine, BL-048) · `feat/sprint-2026-28-b3-explainability`
**As a** investigator,
**I need** evidence-pack narratives composed by an LLM (with structured headings, claims, and citations to evidence items), not a space-joined string of rationales,
**so that** packs read as analyst-ready prose rather than a debug dump.

### Current State (shipped)
- `NarrativeGeneratorProtocol.summarize(*, context, items) -> ExplanationNarrative` (`backend/analytics/explainability/protocols.py`) is the new seam. `DeterministicNarrativeGenerator` (`adapters/deterministic.py`) is a behavior-preserving extraction of the old `_build_narrative`/`_build_reasoning`/`_format_heading` (group by `source_type` in first-seen order, space-joined bodies) — the pre-existing `test_service.py` suite passes unmodified against it, proving no output changed for the deterministic path.
- `LlmNarrativeGenerator` (`adapters/llm_narrative.py`) wraps `llm.protocols.LlmServiceProtocol`: builds a `GenerateRequest`/`PromptTemplate` from the selected `ExplanationItem`s (source id, quote, rationale, score) plus the alert title and score snapshot, instructs markdown `## `-headed sections grounded in the listed evidence, and parses the completion into `NarrativeSection`s (`evidence_refs` = item ids whose text appears in the section, else all selected ids). Degrades to an injected `DeterministicNarrativeGenerator` fallback — logging WARNING, never raising — on any `LlmError`; any unexpected exception, including `GenerateRequest` construction itself (moved inside the never-raise guard by `e8f1b30`); an empty completion; or a malformed completion — no `## ` sections at all (`9e68277`), or an empty opening summary from a completion that opens directly with a heading (`e8f1b30`). Heading-less output is **not** accepted as a summary-only narrative — both malformed shapes degrade.
- `ExplainabilityService.__init__`/`create_explainability_service` gain a keyword-only `narrative_generator: NarrativeGeneratorProtocol | None = None` (defaults to `DeterministicNarrativeGenerator()`); `generate_from_context` dispatches through it and sets `EvidencePack.reasoning = narrative.summary` plus the new `EvidencePack.narrative_sections`.
- `DomainConfig.analytics.narrative_backend: Literal["deterministic","llm"]` (default `"deterministic"`) selects the backend; `agent.coordinator.build_narrative_generator` constructs it from `DomainConfig.llm` at the worker's Flow B assembly site. CMS medicare and Air Force housing default packs set `narrative_backend: llm`.
- **Deviation:** delivered without its originally-listed `analytics.16` (composite graph+RAG+risk context assembler) prerequisite — the worker's Flow B context (`graph.get_subgraph()` + risk factors → `ExplanationContext`, `agent/coordinator.py`) was already real cross-module context by the time this story shipped, so the composite-assembler prerequisite was never load-bearing for this slice. `analytics.16` remains `planned` on its own merits (a reusable assembler for the API-driven `analytics.15` path, not built this sprint).

### Acceptance Criteria
- [x] `NarrativeGeneratorProtocol` introduced under `backend/analytics/explainability/protocols.py` with a `summarize(items, context) -> ExplanationNarrative` method. **Deviation:** keyword-only `summarize(*, context, items)`.
- [x] `LlmNarrativeGenerator` adapter consumes an `LlmServiceProtocol` (cross-edge to llm.md) and emits multi-section prose grounded in `ExplanationItem.source_id` references.
- [x] `DeterministicNarrativeGenerator` retains the legacy join-of-rationales behaviour for tests and offline mode.
- [x] `ExplainabilityService.generate` dispatches via the protocol; `DomainConfig.analytics.narrative_backend` selects. **Deviation:** dispatch lives in `generate_from_context` (the shared path both `generate` and the worker call), not duplicated in `generate` itself.

### Verification
- `pytest backend/tests/analytics/explainability -q` green (includes `test_deterministic_generator.py`, `test_llm_narrative_generator.py`; `test_service.py` unmodified and passing — behavior-preservation gate).
- `pytest --cov` (full suite): 2650 passed, 5 skipped, 97% coverage; `pyright` 0 errors; `ruff check --no-cache .` clean (Sprint 2026-28 B3 Task 8 closeout gates, 2026-07-23).
- **Live-verified 2026-07-23** (Task 9, `feat/sprint-2026-28-b3-explainability`): worker logs confirmed the LLM narrative path via the local echo provider and a clean WARNING-logged degrade to the deterministic fallback; `GET /evidence-packs/{id}` returned non-empty `narrative_sections`; the workbench evidence viewer rendered them with zero console errors. The pass fixed `9e68277` (degrade section-less completions instead of accepting them as summary-only — the echo provider never emits `## ` headings, which had been leaving every LLM-backed pack with empty `narrative_sections`). Post-merge final review found and fixed one further gap, `e8f1b30` (blank-summary completions — a completion opening directly with a heading — also degrade; `GenerateRequest` construction moved inside the never-raise guard). See `docs/project/planning/sprints/2026-28.md` 2026-07-23 "B3 live verification" entry and `docs/project/planning/backlog.md` BL-048 row.

### Code touch points
- `backend/analytics/explainability/protocols.py` (modify)
- `backend/analytics/explainability/service.py` (modify)
- `backend/analytics/explainability/adapters/llm_narrative.py` (new)
- `backend/analytics/explainability/adapters/deterministic.py` (new)
- `backend/config/schema.py` (modify)
- `backend/agent/coordinator.py` (modify — `build_narrative_generator`, not `api/dependencies.py`; this seam is worker-only this sprint)
- `backend/tests/analytics/explainability/` (modify)

---

## Story analytics.14: Explainability: Wire SHAP adapter and add LIME/saliency alternatives
**ID:** analytics.14
**Status:** planned
**Prerequisites:** [config.01]
**Unblocks:** [analytics.15, analytics.30]
**Estimated size:** M
**As a** fraud-analytics engineer,
**I need** `ExplainabilityContextSourceProtocol` to be selectable between in-memory, SHAP, and LIME/permutation-importance adapters via DI and `DomainConfig`,
**so that** investigators see model-agnostic feature attributions instead of fixture data.

**PM status note (2026-07-23):** the implementation is **substantially shipped
in a different shape than this story's AC assumed** — see the delivered-slice
note below. Kept `planned` (not `in-progress`) because the backlog-consistency
validator requires prerequisites `done` for `in-progress` and `config.01` is
still `planned`; this mirrors the precedent set by analytics.11 above.

### Current State
**Delivered slice (Sprint 2026-28 B3, BL-048, 2026-07-23, `feat/sprint-2026-28-b3-explainability`):** a
*different, narrower* SHAP seam than this story's original AC shipped — a **pipeline feature-attributor**,
not the context-source DI literal this story specified. `FeatureAttributorProtocol.attribute(*, context) ->
list[FeatureAttribution]` (`backend/analytics/explainability/protocols.py`) is the new seam;
`ShapRiskAttributor` (`adapters/shap_attribution.py`) attributes `analytics.risk`'s `LinearScoringStrategy`
composite (`predict(X) = min(1.0, Σx_i)`) over the per-feature contributions already snapshotted in
`context.scores`, via `shap.Explainer` against a zero-baseline background — real SHAP end-to-end over a
linear model today, the same seam attributing a trained model later unchanged. `NoopFeatureAttributor`
(same file) is the `"none"` default. `DomainConfig.analytics.attribution_backend: Literal["none","shap"]`
selects; `agent.coordinator.build_feature_attributor` constructs it at the worker's Flow B assembly site;
`ExplainabilityService` composes the result into `EvidencePack.attribution`. Missing `shap`/no risk-factor
features/any explainer exception degrades to `[]` + WARNING, never raises. CMS medicare and Air Force
housing default packs set `attribution_backend: shap`.

**Still open (this story's original scope, unaddressed by the B3 slice):**
- The `get_explainability_context_source` DI factory and `DomainConfig.analytics.explainability_backend:
  Literal["in_memory","shap","lime"]` context-source literal were **not** built — `ShapExplainabilityContextSource`
  (`adapters/shap_adapter.py`) remains unregistered in DI, exactly as before B3.
- No LIME/permutation-importance adapter exists — no dependency, no sprint AC for it.
- **Corrected stale claim:** the "(new) test_shap_adapter.py" acceptance criterion below is stale —
  `backend/tests/analytics/explainability/test_shap_adapter.py` already existed pre-B3 with 12 passing tests
  covering `ShapExplainabilityContextSource`; it was not new when this story was last touched and B3 did not
  modify it. The B3 slice's own tests live in the separate, newly-created
  `backend/tests/analytics/explainability/test_shap_attribution.py` (8 tests, covering `ShapRiskAttributor` +
  `NoopFeatureAttributor`, unit + `@pytest.mark.integration`).
- `ShapRiskAttributor` and `ShapExplainabilityContextSource` are two distinct adapters solving two different
  problems (pipeline attribution vs. context-source loading) that happen to share the `shap` dependency — see
  `backend/analytics/README.md` § Explainability narrative + attribution seams for the disambiguation.

### Acceptance Criteria
- [ ] `get_explainability_context_source` factory added to `backend/api/dependencies.py` keyed by `DomainConfig.analytics.explainability_backend: Literal["in_memory","shap","lime"]`. **Not delivered by B3** — out of scope per the B3 design's ruling (`docs/superpowers/specs/2026-07-23-sprint28-b3-explainability-design.md` §2.4/§5); remains open.
- [ ] `LimeExplainabilityContextSource` (or `PermutationImportanceContextSource`) added under `backend/analytics/explainability/adapters/` with lazy import. **Not delivered** — no dependency, no sprint AC.
- [x] Coverage ≥ 85% on each new adapter (integration test marked `@pytest.mark.integration` for the SHAP and LIME paths). **Delivered for the B3 pipeline-attributor slice only:** `ShapRiskAttributor`/`NoopFeatureAttributor` unit-covered with a monkeypatched loader hook plus a real `@pytest.mark.integration`/`pytest.importorskip("shap")` test asserting SHAP values sum to `predict(x) - predict(0)` within `1e-3`. No LIME adapter exists to cover.
- [x] SHAP unit/integration test exists where there was none. **Corrected:** true for the new `test_shap_attribution.py` file; `test_shap_adapter.py` already had SHAP tests pre-B3 (see stale-claim note above).

### Verification
- `pytest -m integration backend/tests/analytics/explainability/test_shap_attribution.py -q` green (new, B3). `test_shap_adapter.py`'s pre-existing SHAP coverage is unaffected — this story left it unmodified.
- `pytest --cov` (full suite): 2650 passed, 5 skipped, 97% coverage; `pyright` 0 errors; `ruff check --no-cache .` clean (Sprint 2026-28 B3 Task 8 closeout gates, 2026-07-23).
- **Live-verified 2026-07-23** (Task 9, `feat/sprint-2026-28-b3-explainability`): worker logs confirmed `ShapRiskAttributor` rows on new packs matching the entity's risk-factor contributions; `GET /evidence-packs/{id}` returned non-empty `attribution`. See `docs/project/planning/sprints/2026-28.md` 2026-07-23 "B3 live verification" entry and `docs/project/planning/backlog.md` BL-048 row.

### Code touch points
- `backend/analytics/explainability/protocols.py` (modify — `FeatureAttributorProtocol`, B3)
- `backend/analytics/explainability/adapters/shap_attribution.py` (new, B3 — `NoopFeatureAttributor` + `ShapRiskAttributor`)
- `backend/analytics/explainability/service.py` (modify, B3 — composition)
- `backend/config/schema.py` (modify, B3 — `attribution_backend`)
- `backend/agent/coordinator.py` (modify, B3 — `build_feature_attributor`)
- `backend/tests/analytics/explainability/test_shap_attribution.py` (new, B3)
- Still open (original scope): `backend/api/dependencies.py` (`get_explainability_context_source`), `backend/analytics/explainability/adapters/lime_adapter.py` (new), `backend/analytics/explainability/adapters/shap_adapter.py` (modify to register in DI), `backend/tests/analytics/explainability/test_lime_adapter.py` (new)

---

## Story analytics.15: Explainability: Expose `/explainability/{alert_id}` API + DI
**ID:** analytics.15
**Status:** planned
**Prerequisites:** [analytics.14, api.10]
**Unblocks:** [api.04]
**Estimated size:** M
**As a** investigator,
**I need** a `GET /analytics/explainability/{alert_id}` endpoint that returns the evidence pack assembled by `ExplainabilityService`,
**so that** the workbench can render LLM-grounded narratives + feature attributions on demand.

### Current State
- `backend/api/routers/analytics.py` exposes zero explainability endpoints (only risk-scores, timeseries, gnn/clusters, overview).
- `ExplainabilityService` is invoked indirectly via the SSE/state path; `backend/api/dependencies.py:617-682` has no `get_explainability_service` factory.

### Acceptance Criteria
- [ ] `get_explainability_service` DI factory composes a context source (analytics.14), a narrative generator (analytics.13), and the event bus.
- [ ] `GET /analytics/explainability/{alert_id}?kb_id=…` returns `ExplainabilityResponse` with `require_role("viewer")` enforcement.
- [ ] Errors map to the API standard envelope (api.08).
- [ ] OpenAPI schema includes the route with full response model.

### Verification
- `pytest backend/tests/api/test_analytics_router.py::test_explainability_endpoint -q` green.
- Manual: hit the endpoint against the dev stack with a seeded alert id, observe an evidence pack.
- `pyright` clean.

### Code touch points
- `backend/api/routers/analytics.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/tests/api/test_analytics_router.py` (modify)

---

## Story analytics.16: Explainability: Add graph + RAG + risk subgraph assembler
**ID:** analytics.16
**Status:** planned
**Prerequisites:** [graph.05, rag.01, analytics.11]
**Unblocks:** [analytics.13]
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** a production `ExplainabilityContextSource` that assembles an alert's neighborhood (graph), top-k vector hits (RAG retrieval), and top risk factors into one `ExplanationContext`,
**so that** evidence packs reflect real cross-module context instead of hand-fed test fixtures.

### Current State
- `ExplanationContext.subgraph` is constructed by test fixtures (`backend/analytics/explainability/models.py:33-47`).
- `InMemoryExplainabilityContextSource` only echoes what it was seeded with (`backend/analytics/explainability/adapters/in_memory.py:10-26`).
- No production adapter aggregates graph / RAG / risk inputs.

### Acceptance Criteria
- [ ] `CompositeExplainabilityContextSource` (or `AssemblyExplainabilityContextSource`) under `backend/analytics/explainability/adapters/composite.py` consumes graph subgraph extraction (graph.05), RAG retrieval (rag.01), and the risk signal source (analytics.11).
- [ ] DI factory (analytics.14/15) selects this composite when `DomainConfig.analytics.explainability_backend == "composite"`.
- [ ] Coverage ≥ 85% on the new module; integration test exercises the full assembly path end-to-end.

### Verification
- `pytest -m integration backend/tests/analytics/explainability/test_composite.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/analytics/explainability/adapters/composite.py` (new)
- `backend/api/dependencies.py` (modify)
- `backend/tests/analytics/explainability/test_composite.py` (new)

---

## Story analytics.17: Explainability: Persist generated evidence packs durably
**ID:** analytics.17
**Status:** planned
**Prerequisites:** [database.03, api.10]
**Unblocks:** []
**Estimated size:** M
**As a** investigator,
**I need** evidence packs persisted to a durable store (with audit history) so they survive worker restarts and are queryable by id later,
**so that** investigations can reread past packs without recomputing them.

### Current State
- `ExplainabilityService.generate` (`backend/analytics/explainability/service.py:56-98`) builds an `EvidencePack` and publishes `ExplainabilityGeneratedEvent` but nothing writes the pack to a store.
- No `evidence_pack_history` table; no `PostgresEvidencePackRepository`.
- **Stale example noted at Sprint 2026-28 B3 closeout (2026-07-23):** the `0002_evidence_pack_history.py` filename in the Code touch points below is stale against the current migration sequence — the Alembic head is `0011` (`timeseries_anomalies`, Sprint 2026-28 B2) and `0002` is already taken by `cases`. B3 added no migration (attribution + narrative sections embed in the existing object-store-persisted pack). Any future implementer of this story should name the new migration `0012_evidence_pack_history.py` (or whatever the head is at implementation time), not `0002`.

### Acceptance Criteria
- [ ] New Alembic migration creates `evidence_pack_history` table (`evidence_pack_id`, `alert_id`, `knowledge_base_id`, `reasoning`, `subgraph_nodes`, `subgraph_edges`, `confidence`, `scores`, `created_at`).
- [ ] New `EvidencePackRepositoryProtocol` with `PostgresEvidencePackRepository` and `InMemoryEvidencePackRepository` under `backend/analytics/explainability/adapters/`.
- [ ] New worker handler `handle_explainability_generated_for_storage` in `backend/agent/coordinator.py` performs the write (mirrors Plan C Flow 3/4 pattern).
- [ ] Coverage ≥ 85% on the new adapter; handler covered by a coordinator test.

### Verification
- `pytest backend/tests/analytics/explainability/test_postgres_repository.py -q` green.
- `pytest backend/tests/agent/test_handle_explainability_generated.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/database/migrations/versions/0002_evidence_pack_history.py` (new)
- `backend/analytics/explainability/adapters/postgres.py` (new)
- `backend/analytics/explainability/adapters/in_memory_repo.py` (new)
- `backend/agent/coordinator.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/tests/analytics/explainability/` (add)

---

## Story analytics.18: Metrics: Expand graph-scope metrics beyond entity/relationship/avg-degree
**ID:** analytics.18
**Status:** planned
**Prerequisites:** [graph.16]
**Unblocks:** [analytics.20, embeddings.11, monitoring.11]
**Estimated size:** M
**As a** investigator,
**I need** richer graph-scope metrics (betweenness, PageRank, community quality, per-entity-type breakdowns) collected by Flow 2,
**so that** the dashboard surfaces structural-quality signals without re-querying the graph.

### Current State
- `metrics/models.py` (`backend/analytics/metrics/models.py:11-16`) defines only `METRIC_ENTITY_COUNT`, `METRIC_RELATIONSHIP_COUNT`, `METRIC_AVG_DEGREE`.
- `handle_graph_updated_for_analytics` (`backend/agent/coordinator.py:1096-1300`) writes only those three metrics plus `__graph__` scope.
- Per-entity-type breakdowns are not collected.

### Acceptance Criteria
- [ ] `METRIC_BETWEENNESS_CENTRALITY`, `METRIC_PAGERANK`, `METRIC_COMMUNITY_MODULARITY`, and per-entity-type variants added to `models.py`.
- [ ] Flow 2 computes them via the new graph-native metrics from graph.16 and writes them per `(kb_id, entity_id, metric_name)`.
- [ ] Throttle (`MetricsRecomputeThrottle`) covers the expanded computation set.
- [ ] Coverage ≥ 85% on the metrics computation path.

### Verification
- `pytest backend/tests/agent/test_handle_graph_updated_for_analytics.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/analytics/metrics/models.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/tests/agent/test_handle_graph_updated_for_analytics.py` (modify)

---

## Story analytics.19: Metrics: Add a Prometheus/OpenMetrics exposition surface
**ID:** analytics.19
**Status:** planned
**Prerequisites:** [_observability.07]
**Unblocks:** [analytics.26]
**Estimated size:** M
**As a** ops engineer,
**I need** analytics throughput/latency/error counters exposed via the platform's `/metrics` endpoint (location and label conventions owned by the observability epic),
**so that** Prometheus scraping covers the analytics module the same way it covers HTTP.

### Current State
- `backend/analytics/metrics/` is persistence-only (history + current tables); no Prometheus instrumentation (`backend/analytics/metrics/__init__.py`).
- No counters / histograms exist for analytics analyze duration, anomaly counts, or per-service contention.
- Adapter protocols (`backend/analytics/metrics/adapters/protocols.py:11-27`) cover persistence only.

### Acceptance Criteria
- [ ] New `backend/analytics/metrics/prometheus.py` module declares `analytics_analyze_duration_seconds{service,strategy}`, `analytics_anomaly_count_total`, `analytics_errors_total{service,error_class}` via `prometheus_client`.
- [ ] `RiskService`, `TimeseriesService`, `GnnService`, `ExplainabilityService` instrument their service methods with the new counters/histograms.
- [ ] `/metrics` endpoint location and registration follow the platform convention from `_observability.07`; analytics counters appear in a scrape.
- [ ] Documented label conventions in `backend/analytics/README.md`.

### Verification
- `pytest backend/tests/analytics/test_prometheus_instrumentation.py -q` green.
- Manual: scrape `/metrics` in the dev stack and assert the new metric families appear.
- `pyright` clean.

### Code touch points
- `backend/analytics/metrics/prometheus.py` (new)
- `backend/analytics/timeseries/service.py` (modify)
- `backend/analytics/gnn/service.py` (modify)
- `backend/analytics/risk/service.py` (modify)
- `backend/analytics/explainability/service.py` (modify)
- `backend/analytics/README.md` (modify)
- `backend/tests/analytics/test_prometheus_instrumentation.py` (new)

---

## Story analytics.20: Metrics: Add per-entity-type rollups and metric provenance
**ID:** analytics.20
**Status:** planned
**Prerequisites:** [analytics.18, database.04]
**Unblocks:** []
**Estimated size:** M
**As a** investigator,
**I need** per-entity-type rollup queries (avg/p50/p95 of a metric across all entities of a type) and metric provenance via `correlation_id`,
**so that** dashboard summaries can compare entity types and trace metric values back to the producing pipeline run.

### Current State
- `EntityMetricSample.correlation_id` is captured but never exposed via a rollup query (`backend/analytics/metrics/adapters/postgres.py:32-37,80-90`).
- Adapter SELECTs are keyed only by `(kb_id, entity_id)`; no `(kb_id, entity_type)` rollup.

### Acceptance Criteria
- [ ] New `PostgresEntityMetricRepository.aggregate_by_entity_type(kb_id, metric_name) -> list[MetricRollup]` returning avg/p50/p95.
- [ ] New `load_by_correlation_id(correlation_id)` for provenance lookups.
- [ ] `GET /analytics/metrics/rollups?kb_id=…&metric=…` exposes the rollup behind `require_role("viewer")`.
- [ ] Coverage ≥ 85%.

### Verification
- `pytest backend/tests/analytics/metrics/test_postgres_repository.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/analytics/metrics/adapters/postgres.py` (modify)
- `backend/analytics/metrics/adapters/protocols.py` (modify)
- `backend/analytics/metrics/models.py` (modify)
- `backend/api/routers/analytics.py` (modify)
- `backend/tests/analytics/metrics/` (modify)

---

## Story analytics.21: Model training pipeline (§14.2): Scheduled/triggered GNN training event flow
**ID:** analytics.21
**Status:** planned
**Prerequisites:** [agent.13, agent.14, events.04, analytics.23]
**Unblocks:** []
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** a `GnnTrainEvent` + worker handler that trains GNN weights on a schedule or trigger and writes the artifact through the model registry,
**so that** inference (analytics.01/02) can serve a recent model without on-the-fly fitting.

### Current State
- No `GnnTrainEvent` in `backend/events/types.py`; no `handle_gnn_train` in `backend/agent/coordinator.py`.
- `GnnService` is inference-only (`backend/analytics/gnn/service.py:43-146`) with no `train`/`infer` split.
- §14.2 lists "model training pipeline" as a Medium-priority capability (`docs/architecture.md:1358`).

### Acceptance Criteria
- [ ] New `GnnTrainEvent` defined in `backend/events/types.py`, registered in `EVENT_TYPE_REGISTRY`, and documented in the event catalog (events.04).
- [ ] New worker handler `handle_gnn_train` orchestrates: load snapshot → train → register artifact → publish `GnnModelRegisteredEvent`.
- [ ] Scheduling triggered via agent.14 (scheduled job runner); manual trigger via `POST /analytics/gnn/train` (covered separately in analytics.27).
- [ ] Train/infer split exposed in `GnnService` (`train(snapshot) -> ModelArtifact` distinct from `analyze(request) -> response`).

### Verification
- `pytest backend/tests/agent/test_handle_gnn_train.py -q` green.
- Manual end-to-end: schedule a train, observe artifact persisted, run analyze, observe artifact used.
- `pyright` clean.

### Code touch points
- `backend/events/types.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/analytics/gnn/service.py` (modify)
- `backend/tests/agent/test_handle_gnn_train.py` (new)
- `docs/ledger/event-catalog.md` (modify)

---

## Story analytics.22: Model training pipeline (§14.2): Embedding fine-tuning workflow
**ID:** analytics.22
**Status:** planned
**Prerequisites:** [embeddings.10, analytics.23, agent.14]
**Unblocks:** [monitoring.14]
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** an analytics-owned `embedding_finetune` job that exports labeled pairs (from explainability + risk feedback) and triggers embedding fine-tuning (embeddings.10),
**so that** embeddings adapt to domain-specific similarity signals.

### Current State
- `embeddings/` produces embeddings on the fly; no analytics-owned `embedding_finetune` job.
- No labeled-pair adapter and no training-data export surface from `analytics/explainability` or `analytics/risk`.
- §14.2 lists "embedding fine-tuning" as a Medium-priority capability (`docs/architecture.md:1358`).

### Acceptance Criteria
- [ ] New `LabeledPairExporterProtocol` under `backend/analytics/explainability/protocols.py` (or new `analytics/training/`) returning `(anchor_text, positive_text, negative_text)` triples derived from cases / feedback / risk co-occurrence.
- [ ] New worker handler `handle_embedding_finetune` packages the export and calls the embeddings fine-tuning hook (embeddings.10), then registers the artifact via the model registry (analytics.23).
- [ ] Scheduled trigger via agent.14.
- [ ] Coverage ≥ 85% on the new module; integration test asserts a full export→train→register round-trip with stubbed embedding training.

### Verification
- `pytest backend/tests/analytics/training/ -q` green.
- `pyright` clean.

### Code touch points
- `backend/analytics/training/__init__.py` (new) *or* extension to `analytics/explainability/`
- `backend/analytics/training/exporter.py` (new)
- `backend/agent/coordinator.py` (modify)
- `backend/events/types.py` (modify)
- `backend/tests/analytics/training/` (new)

---

## Story analytics.23: Model training pipeline (§14.2): Model registry, versioning, artifact storage
**ID:** analytics.23
**Status:** planned
**Prerequisites:** [database.03, storage.01, config.01]
**Unblocks:** [analytics.02, analytics.09, analytics.21, analytics.22]
**Estimated size:** L
**As a** platform engineer,
**I need** a `ModelRegistryProtocol` backed by Postgres metadata + object-store blobs that tracks trained model artifacts (SHAP background, GNN weights, scoring strategy parameters, fine-tuned embeddings) with semantic versioning,
**so that** every inference path (analytics.01, 02, 09, 21, 22) can pin a specific model version and roll back safely.

### Current State
- No `analytics/models/` (or `analytics/registry/`) directory; no `model_registry` table; no `ModelRegistryProtocol`.
- Trained artifacts have nowhere durable to live; everything is on-the-fly today.

### Acceptance Criteria
- [ ] New module `backend/analytics/registry/` containing `protocols.py`, `models.py`, `service.py`, and adapters (`postgres.py`, `in_memory.py`).
- [ ] New Alembic migration `model_registry` table: `model_id, kind, version, status, artifact_uri, metadata jsonb, created_at, registered_by`.
- [ ] `register_model(artifact_bytes, metadata) -> ModelRecord` writes blob to object store (storage.01) and metadata to Postgres atomically.
- [ ] `get_active_model(kind)` returns the active version per kind (e.g. `gnn`, `risk_boosted`, `embedding_finetune`, `shap_background`).
- [ ] `DomainConfig.analytics.models[*].active_version` lets ops pin a version without code change.
- [ ] Coverage ≥ 85% on the new module.

### Verification
- `pytest backend/tests/analytics/registry/ -q` green.
- Integration test registers a fake artifact, retrieves it, asserts metadata round-trip.
- `pyright` clean.

### Code touch points
- `backend/analytics/registry/__init__.py` (new)
- `backend/analytics/registry/protocols.py` (new)
- `backend/analytics/registry/models.py` (new)
- `backend/analytics/registry/service.py` (new)
- `backend/analytics/registry/adapters/postgres.py` (new)
- `backend/analytics/registry/adapters/in_memory.py` (new)
- `backend/database/migrations/versions/0003_model_registry.py` (new)
- `backend/config/schema.py` (modify)
- `backend/tests/analytics/registry/` (new)

---

## Story analytics.24: Self-reinforcing loop (§6.7): Write GNN cluster_id / link predictions back to the graph
**ID:** analytics.24
**Status:** planned
**Prerequisites:** [agent.12, events.04, graph.02]
**Unblocks:** [analytics.05, frontend.29]
**Estimated size:** M
**As a** fraud-analytics engineer,
**I need** a worker handler that consumes `GnnAnalyzedEvent` and writes `cluster_id`, `predicted_neighbor_ids`, and `anomaly_score` back onto graph entities,
**so that** subsequent risk and timeseries analyses can use GNN-derived structural features.

> **Delivered slice (verified during Sprint 2026-28 B1 planning/close, 2026-07-16, `feat/sprint-2026-28-b1-gnn-live`; not new work from B1 itself):** `agent.coordinator._write_analytics_properties_to_graph` (called from `handle_graph_updated_for_analytics` right after the risk stage) already writes `community_id` (from the scored node's `cluster_id`, falling back to the containing community's `community_id`) and `centrality_score` (the scored node's normalized `score`) onto each upserted entity via `GraphService.update_entity_properties`, best-effort (logs a warning, never fails the pipeline). This covers the `cluster_id`/`anomaly_score`-shaped half of the ask. **Not delivered:** `predicted_neighbor_ids` is never written back — `GnnAnalysisResponse.predicted_links` is computed and returned to callers but nothing persists it onto entities. Architecturally this also isn't the `GnnAnalyzedEvent`-consuming handler the story specifies: it's an inline call within the same synchronous Flow B pass that ran the GNN stage (using the in-memory `gnn_response`), not a separate `handle_gnn_analyzed_for_graph` triggered by re-consuming the event — so it can't independently redeliver/retry the graph write from the event log the way the story's design implies. The property contract is undocumented: `backend/agent/AGENT.md` does not exist and `backend/agent/README.md` does not mention `community_id`/`centrality_score`. Story stays `planned`; the remaining gap is the `predicted_neighbor_ids` write-back, an explicit event-consuming handler (or a documented rationale for the inline approach), and the property-contract doc.

### Current State
- `GnnAnalyzedEvent` carries reference counts only (`backend/events/types.py:258-269`); it does not carry per-entity `cluster_id`/`score` fields.
- No `handle_gnn_analyzed_for_graph` event-consuming handler exists in `backend/agent/coordinator.py` — see the delivered-slice note above for the inline mechanism that partially substitutes for it.
- Architecture §6.7 (`docs/architecture.md:757-764`) calls for this feedback loop.

### Acceptance Criteria
- [ ] `GnnAnalyzedEvent` (or a new `GnnAnalyzedDetailEvent`) gains optional per-entity reference fields (`cluster_id`, `score`) sufficient for the handler to update entities without re-fetching the full analysis (cross-edge to events.04 for catalog drift). **Not delivered** — the existing write-back reads straight from the in-process `GnnAnalysisResponse`, not from event fields.
- [ ] New `handle_gnn_analyzed_for_graph` handler in `backend/agent/coordinator.py` calls `GraphService.update_entity_properties` for each scored node, idempotent on redelivery. **Partially delivered differently:** `_write_analytics_properties_to_graph` does call `update_entity_properties` per entity (property-merge semantics make it idempotent on redelivery) with `community_id`/`centrality_score`, but as an inline step of Flow B, not a standalone event-consuming handler; `predicted_neighbor_ids` is not written.
- [ ] Property contract (`cluster_id`, `predicted_neighbor_ids`, `anomaly_score`, `gnn_analyzed_at`) documented in `backend/agent/AGENT.md`. **Not delivered** — `AGENT.md` doesn't exist; the shipped property names (`community_id`, `centrality_score`) also differ from the ones specified here (`cluster_id`, `anomaly_score`, `gnn_analyzed_at`) and are undocumented in `backend/agent/README.md`.
- [ ] Coverage ≥ 85% on the handler. The existing inline write-back is covered by `backend/tests/agent/` coordinator tests (not a dedicated `test_handle_gnn_analyzed.py`).

### Verification
- `pytest backend/tests/agent/test_handle_gnn_analyzed.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/events/types.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/agent/AGENT.md` (modify)
- `backend/tests/agent/test_handle_gnn_analyzed.py` (new)

---

## Story analytics.25: Self-reinforcing loop (§6.7): Write timeseries anomaly flags back to the graph
**ID:** analytics.25
**Status:** planned
**Prerequisites:** [agent.12, events.04, graph.02]
**Unblocks:** []
**Estimated size:** M
**As a** fraud-analytics engineer,
**I need** a worker handler that consumes `TimeseriesAnalyzedEvent` and writes `last_anomaly_at`, `anomaly_count`, `anomaly_z_max` onto graph entities,
**so that** investigators see entity-level anomaly history without leaving the graph.

### Current State
- `TimeseriesAnalyzedEvent` is published with reference data only (`backend/events/types.py:244-256`).
- No graph-write handler enriches entities with anomaly stats.

### Acceptance Criteria
- [ ] `TimeseriesAnalyzedEvent` (or a new sibling) gains the per-entity fields needed for the handler to write (catalog update via events.04).
- [ ] New `handle_timeseries_analyzed_for_graph` handler in `backend/agent/coordinator.py` updates entity properties idempotently.
- [ ] Property contract documented in `backend/agent/AGENT.md`.
- [ ] Coverage ≥ 85% on the handler.

### Verification
- `pytest backend/tests/agent/test_handle_timeseries_analyzed.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/events/types.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/agent/AGENT.md` (modify)
- `backend/tests/agent/test_handle_timeseries_analyzed.py` (new)

---

## Story analytics.26: Observability: Per-stage analytics metrics, traces, structured logs
**ID:** analytics.26
**Status:** planned
**Prerequisites:** [_observability.04, _observability.05, analytics.19]
**Unblocks:** []
**Estimated size:** M
**As a** ops engineer,
**I need** every analytics service to emit per-stage timing/throughput counters, OTel spans, and structured log lines (correlation_id, kb_id, entity_id),
**so that** dashboards show p50/p95 per stage and traces correlate analytics work with upstream/downstream events.

### Current State
- `TimeseriesService` (`backend/analytics/timeseries/service.py:64-140`), `GnnService` (`backend/analytics/gnn/service.py:63-146`), and `RiskService` (`backend/analytics/risk/service.py:52-156`) emit no service-level metrics, traces, or structured logs.
- Only `agent/coordinator.py` wraps them with `observe_pipeline_stage` at the workflow boundary.

### Acceptance Criteria
- [ ] Each service method opens an OTel span using the helper from `_observability.04`.
- [ ] Structured logs carry `request_id`, `knowledge_base_id`, `entity_id` (where applicable), and `duration_ms`.
- [ ] Service-level histograms (`analytics_*_duration_seconds`) from analytics.19 are recorded per call.
- [ ] Coverage ≥ 85% on the instrumentation paths.

### Verification
- `pytest backend/tests/analytics/test_observability.py -q` green.
- Manual: trigger an analyze call against the dev stack and observe spans in the trace exporter.
- `pyright` clean.

### Code touch points
- `backend/analytics/timeseries/service.py` (modify)
- `backend/analytics/gnn/service.py` (modify)
- `backend/analytics/risk/service.py` (modify)
- `backend/analytics/explainability/service.py` (modify)
- `backend/tests/analytics/test_observability.py` (new)

---

## Story analytics.27: Analytics API: Add `POST` compute endpoints
**ID:** analytics.27
**Status:** planned
**Prerequisites:** [api.17, _security.06]
**Unblocks:** []
**Estimated size:** M
**As a** investigator,
**I need** `POST /analytics/risk/assess`, `POST /analytics/timeseries/analyze`, `POST /analytics/gnn/analyze`, and `POST /analytics/gnn/train` endpoints that trigger compute on demand,
**so that** investigators can re-run analytics from the workbench without going through the event bus directly.

### Current State
- `backend/api/routers/analytics.py:39-132` exposes only read endpoints (`/risk-scores`, `/timeseries`, `/gnn/clusters`, `/overview`, `/risk-scores/{entity_id}`, `/timeseries/{entity_id}`).
- Service protocols already expose the compute methods; no HTTP route invokes them.

### Acceptance Criteria
- [ ] Four new POST routes registered in `backend/api/routers/analytics.py`, each guarded by the route policy registry (api.17) with `investigator` or `admin` scope per `_security.06`.
- [ ] Request models reuse existing `RiskAssessmentRequest`/`TimeseriesAnalysisRequest`/`GnnAnalysisRequest`; train route accepts a new `GnnTrainRequest` (analytics.21).
- [ ] Errors mapped to the API standard envelope (api.08).
- [ ] OpenAPI schema covers all four routes with response models and example payloads.

### Verification
- `pytest backend/tests/api/test_analytics_router.py -q` green.
- Manual: hit each POST from the dev stack and observe the corresponding service call.
- `pyright` clean.

### Code touch points
- `backend/api/routers/analytics.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/api/middleware/policy_registry.py` (modify)
- `backend/tests/api/test_analytics_router.py` (modify)

---

## Story analytics.28: Analytics API: Remove remaining deterministic-payload shortcut endpoints
**ID:** analytics.28
**Status:** done
**Prerequisites:** [api.29, frontend.04]
**Unblocks:** []
**Estimated size:** M
**Done:** 2026-07-19 · Sprint 2026-28 B2, Task 9 live-pass defect #5 fix (`42ef186`) · `feat/sprint-2026-28-b2-timeseries-anomalies`
**As a** API maintainer,
**I need** `/analytics/risk-scores/{entity_id}` and `/analytics/timeseries/{entity_id}` to read from the live service + persistence layer rather than the seeded in-memory payloads in `ApiState`,
**so that** the dashboard and entity-detail views reflect real data and the seeded fallback can be removed.

### Current State (shipped)
- `/analytics/overview` now uses `get_analytics_overview_payload` and `build_analytics_overview(...)` to aggregate durable alert projections, durable cases, and KB metadata (`backend/api/dependencies.py`, `backend/api/_analytics_overview.py`).
- **`/analytics/timeseries/{entity_id}` is done** (shipped under analytics.07, Sprint 2026-28 B2): it now reads `get_entity_series_source()` (`RecordAggregateTimeSeriesSource` over record-column aggregates + `DomainConfig.timeseries.metrics`) joined with `get_timeseries_anomaly_store()`; `ApiState.get_timeseries`/`_timeseries_source`/`_timeseries_service`/`_build_timeseries_series` were deleted as dead code.
- **`/analytics/risk-scores/{entity_id}` is done too** (Task 9 live-pass defect #5, commit `42ef186`): `get_risk_score_payload` (`backend/api/dependencies.py`) now assesses via `get_risk_service()` (`PostgresRiskSignalSource` when a DB is configured), mapping `RiskConfigurationError`/`RiskInsufficientSignalsError`/`ValueError` to an `unavailable` payload while letting infra errors propagate; `ApiState`'s entire seeded risk stack — `get_risk_score`, `_risk_service`, `_build_risk_profiles`, `_normalize_risk_level` — was deleted (`_normalize_risk_level` moved to `dependencies.py` next to `get_risk_score_payload`).
- `backend/api/state.py`'s module docstring now documents both migrations (timeseries under analytics.07, then risk detail); the only thing `ApiState` still owns is the RAG service handle for chat streaming.
- Live-verified 2026-07-19 (Task 9 checklist items 5–6, TN 1% demo KB `82db11c3`): `provider:1003195173`'s risk profile carries both signal families (`timeseries_anomaly:weekly_carrier_billing_self` + peerstats `weekly_carrier_billing`) via the API, and the workbench entity-detail view renders both risk-factor families with zero console errors (screenshot `b2-task9-workbench-anomaly-chip.png`) — closing the frontend.04 render-confirmation this story's AC called for.

### Acceptance Criteria
- [x] `/analytics/timeseries/{entity_id}` switches to DI factories that compose live persistence (`get_entity_series_source`, `get_timeseries_anomaly_store`) — analytics.07.
- [x] `/analytics/risk-scores/{entity_id}` switches to DI factories that compose the live risk service and persistence (`get_risk_service` over `PostgresRiskSignalSource`) — Task 9 defect #5 fix, commit `42ef186`.
- [x] Deprecation note in `backend/api/AGENT.md` (if present) or `backend/api/state.py` docstring — no `AGENT.md` exists under `backend/api/`; `state.py`'s module docstring documents the risk-detail migration alongside the earlier timeseries one.
- [x] `ApiState` seeded risk-score payload removed once api.01 ships (or moved to a `tools/seed_demo_state.py`) — api.01 is done; `42ef186` deleted the seeded risk stack outright (no `tools/seed_demo_state.py` needed).
- [x] Frontend Dashboard/EntityDetail (frontend.04) confirmed to render correctly on live data — Task 9 live pass confirmed the workbench entity-detail view renders both risk-factor families on real Postgres-derived signals.

### Verification
- `pytest backend/tests/api/test_analytics_router.py -q` green.
- Manual e2e: load Dashboard against a freshly-ingested KB, observe live metrics.
- `pyright` clean.
- Live pass 2026-07-19 (Task 9, TN 1% demo KB `82db11c3`): `/analytics/risk-scores/{entity_id}` serves live Postgres-derived signals for `provider:1003195173`; workbench entity-detail renders both timeseries-anomaly and peerstats risk factors with zero console errors.

### Code touch points
- `backend/api/routers/analytics.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/api/state.py` (modify)
- `backend/tests/api/test_analytics_router.py` (modify)
- `backend/tests/api/test_phase5_stateful_routes.py`, `backend/tests/api/test_read_model_routers.py` (modify — Task 9 defect #5 test migration)

---

## Story analytics.29: Production guardrails: Reject in-memory adapters in production mode
**ID:** analytics.29
**Status:** planned
**Prerequisites:** [config.05, _security.10]
**Unblocks:** []
**Estimated size:** S
**As a** platform operator,
**I need** `get_risk_signal_source`, `get_timeseries_history_source`, `get_graph_snapshot_source`, and `get_explainability_context_source` to refuse to return an in-memory adapter when `CHILI_ENV=production`,
**so that** misconfigured prod deployments fail loudly at startup instead of silently serving empty data.

### Current State
- `get_risk_signal_source` selects `PostgresRiskSignalSource` when a DB connection provider exists; it falls back to `InMemoryRiskSignalSource` otherwise.
- `get_timeseries_history_source` and `get_graph_snapshot_source` still return in-memory adapters unconditionally.
- No production guardrail in `backend/api/dependencies.py`; explainability has no DI helper at all today.

### Acceptance Criteria
- [ ] Shared helper (e.g. `assert_production_safe(adapter, name)`) defined alongside the existing dependency factories that raises `ConfigurationError` when `CHILI_ENV in {"staging","production"}` and the resolved adapter is an in-memory variant.
- [ ] Every analytics DI factory calls the helper before returning.
- [ ] Unit tests cover both branches (prod env + in-memory adapter -> raise; prod env + production adapter -> ok).

### Verification
- `pytest backend/tests/api/test_dependencies.py::test_analytics_prod_guardrail -q` green.
- `pyright` clean.

### Code touch points
- `backend/api/dependencies.py` (modify)
- `backend/tests/api/test_dependencies.py` (modify)

---

## Story analytics.30: Coverage gate parity across all five subpackages
**ID:** analytics.30
**Status:** planned
**Prerequisites:** [analytics.14]
**Unblocks:** []
**Estimated size:** M
**As a** quality owner,
**I need** every analytics subpackage's `service.py` and `adapters/postgres.py` to hit ≥ 85 % coverage and the SHAP, STL, and isolation-forest paths to have non-integration tests,
**so that** the CLAUDE.md coverage gate holds uniformly across `timeseries`, `gnn`, `risk`, `explainability`, and `metrics`.

### Current State
- `backend/analytics/README.md:42-43` explicitly carves `analytics/metrics` out of the service+events shape.
- STL and isolation-forest paths (`backend/analytics/timeseries/service.py:168-195`) and the SHAP adapter (`backend/analytics/explainability/adapters/shap_adapter.py`) are integration-marked today — they do not contribute to the standard non-integration coverage gate.
- Repo policy in `CLAUDE.md` requires ≥ 85 % coverage per package; some analytics packages are below that on the non-integration profile.

### Acceptance Criteria
- [ ] Coverage report run via `pytest --cov=analytics.timeseries --cov=analytics.gnn --cov=analytics.risk --cov=analytics.explainability --cov=analytics.metrics --cov-fail-under=85` passes.
- [ ] Non-integration unit tests cover the STL and isolation-forest dispatch paths via lightweight stub estimators.
- [ ] Non-integration unit tests cover the SHAP adapter happy path via a stub `ShapExplainer`.
- [ ] `backend/analytics/README.md` coverage statement updated to reflect parity across all five subpackages.

### Verification
- `cd backend && pytest --cov=analytics --cov-fail-under=85 -q` green.
- `pyright` clean.

### Code touch points
- `backend/tests/analytics/timeseries/test_strategies.py` (modify or new)
- `backend/tests/analytics/explainability/test_shap_adapter.py` (modify)
- `backend/analytics/README.md` (modify)

## Story analytics.31: Add configurable GNN inference adapter

**ID:** analytics.31
**Status:** planned
**Prerequisites:** [analytics.01]
**Unblocks:** [analytics.32]
**Estimated size:** L

### Narrative
As a data scientist,
I want a configurable PyG/DGL-backed inference adapter,
so that trained graph models can score graph entities through the analytics protocol.

### Acceptance Criteria
- [ ] Optional GNN adapter loads configured model artifacts and feature mappings.
- [ ] Adapter implements the analytics inference protocol without changing callers.
- [ ] Configuration supports CPU execution and explicit rejection when required optional dependencies are missing.

### Verification
- [ ] Unit tests cover model configuration validation and missing-dependency behavior.
- [ ] Adapter contract tests run with lightweight fixtures or fakes.

### Code touch points
- `backend/app/analytics/**`
- `backend/app/config/**`
- `backend/tests/analytics/**`

---

## Story analytics.32: Wire analytics inference into API and graph workflows

**ID:** analytics.32
**Status:** planned
**Prerequisites:** [analytics.31]
**Unblocks:** [_plugins.01, graph.16, monitoring.19]
**Estimated size:** M

### Narrative
As an analyst,
I want analytics inference results available through API and graph workflows,
so that downstream features can consume scored entities consistently.

### Acceptance Criteria
- [ ] API exposes inference endpoints or service methods used by planned consumers.
- [ ] Graph workflow integration can request scores for persisted nodes and edges.
- [ ] Tests verify baseline and configured adapters are selected through configuration.

### Verification
- [ ] API/integration tests cover scoring persisted graph fixtures.
- [ ] Configuration tests prove adapter selection is deterministic.

### Code touch points
- `backend/app/api/**`
- `backend/app/analytics/**`
- `backend/tests/**`

---

## Story analytics.33: Extraction-quality metric — `compute_extraction_quality(predicted, gold)`

**ID:** analytics.33
**Status:** planned
**Prerequisites:** []
**Unblocks:** [ingestion.19]
**Estimated size:** M

**As an** extraction-quality steward,
**I need** a pure `compute_extraction_quality(predicted, gold) -> QualityReport` function under `backend/analytics/metrics/` that returns per-entity-type precision/recall/F1 and an overall macro-F1,
**so that** the ingestion golden-test gate (`ingestion.19`) and any future extractor regression suite have a single, tested scoring primitive rather than ad-hoc inline math.

### Current State
- No extraction-quality computation exists anywhere in the codebase: `grep -r "compute_extraction_quality\|extraction_quality" backend/` returns nothing, and `backend/analytics/metrics/extraction_quality.py` does not exist.
- `ingestion.19` (golden tests) originally cited `analytics.07` as the owner of this capability, but `analytics.07` is "Timeseries: Wire production `PostgresTimeSeriesHistorySource` through API DI" — unrelated. This story is created (PM run 2026-06-23) to give the extraction-quality metric a real home in its owning module.
- `backend/analytics/metrics/` currently holds graph/risk metric helpers but no entity-extraction scoring.

### Acceptance Criteria
- [ ] `compute_extraction_quality(predicted: ExtractionResult, gold: GoldExtraction) -> QualityReport` lands in `backend/analytics/metrics/extraction_quality.py` as a pure function (no IO, no LLM calls).
- [ ] `QualityReport` exposes per-type `precision`/`recall`/`f1` plus an overall `macro_f1`, and a relationship-level score block.
- [ ] Entity matching keys on `(type, natural_key)`; relationship matching keys on `(type, source_natural_key, target_natural_key)`.
- [ ] Fully typed (`pyright --strict` clean), no `Any`.
- [ ] Unit tests cover: exact match (F1=1.0), missing prediction (recall drop), spurious prediction (precision drop), per-type aggregation, and empty-gold / empty-predicted edge cases; coverage ≥ 85% on the new module.

### Verification
- `pytest backend/tests/analytics/metrics/test_extraction_quality.py -v` green; coverage ≥ 85% on `backend/analytics/metrics/extraction_quality.py`.

### Code touch points
- `backend/analytics/metrics/extraction_quality.py` (new)
- `backend/tests/analytics/metrics/test_extraction_quality.py` (new)

---

## Story analytics.34: Trigger GNN/graph analytics after records-only ingestion

**ID:** analytics.34
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** fraud-analytics engineer,
**I need** records-only knowledge bases (CSV/JSONL/API-push feeds with no document ingest) to trigger GNN, risk, and explainability analytics the same way document ingest does,
**so that** KBs populated exclusively through `records/` are not permanently invisible to `/analytics/gnn/clusters` and the rest of Flow B.

### Current State
- `GraphService.upsert_records_graph` (`backend/graph/service.py:196-209`) deliberately upserts entities/relationships for a structured-records feed but publishes no `GraphUpdatedEvent` — the docstring says records writes have "no parsed-document lineage" and the worker's Flow 1 handler must stay safely replayable.
- `agent.coordinator.handle_graph_updated_for_analytics` (Flow B: GNN → risk → explainability → alerts) is subscribed only to `GraphUpdatedEvent`, so it never runs for a KB whose only writes came through `handle_records_ingested` / `upsert_records_graph`.
- Observed directly during Sprint 2026-28 B1 (GNN live, `feat/sprint-2026-28-b1-gnn-live`): a pure-records KB shows zero GNN clusters indefinitely, with no error or log signal that anything is missing — the gap is silent, distinct from the controlled `GnnSnapshotUnavailableError`/`GnnInsufficientGraphError` skips Flow B already logs for document-driven KBs that are merely too small yet.
- `docs/backlog/records.md` story `records.12` (planned) documents the same `upsert_records_graph`-does-not-publish-`GraphUpdatedEvent` design gap and proposes an opt-in `RecordsConfig.emit_graph_updated_event` toggle aimed at Flow 2/3 (graph metrics, risk recompute). If `records.12` ships as designed, Flow B would pick up the resulting `GraphUpdatedEvent` for free (it already subscribes to that event type) — this story exists to decide and implement the analytics-specific trigger regardless of whether `records.12`'s general toggle lands first.
- Re-confirmed during the Sprint 2026-28 B3 (BL-048) Task 9 live pass (2026-07-23): since Flow B never fires for a records-only KB, the gap is not limited to GNN clusters — the same silent no-op means no risk profile recompute, no evidence packs (`ExplainabilityService`/`LlmNarrativeGenerator`/`ShapRiskAttributor` are never invoked), and no alerts for such a KB, since all three sit downstream of the same `handle_graph_updated_for_analytics` fan-out this story's fix must reach.

### Acceptance Criteria
- [ ] A design decision is recorded between the two options below (or `records.12`'s toggle is adopted explicitly as the mechanism, with this story then reduced to "confirm Flow B fires under the toggle"):
  - **Option A — `RecordsIngestedEvent`-triggered Flow B:** `handle_graph_updated_for_analytics` (or a thin wrapper) is additionally invoked in response to `RecordsIngestedEvent`, resolving the upserted entity ids from the records-upsert result rather than a `graph_update_storage_key`.
  - **Option B — explicit analytics trigger after records upsert:** `handle_records_ingested` calls the GNN/risk/explainability fan-out directly (in-process, or via a new dedicated event) immediately after `upsert_records_graph` succeeds, without changing what `GraphUpdatedEvent` means for documents.
- [ ] Whichever option is chosen, it is gated so high-volume records feeds are not forced into a GNN/risk recompute on every batch (e.g. reuse `MetricsRecomputeThrottle` or an equivalent throttle already used by Flow 2).
- [ ] `backend/records/README.md` and `backend/analytics/README.md` both note that GNN/risk/explainability analytics fire for records-ingested KBs once this ships (cross-reference `records.12` if that story's toggle is the chosen mechanism).
- [ ] Coverage ≥ 85% on the new/modified handler path.

### Verification
- `pytest backend/tests/agent -q -k records` green, including a new test asserting a records-only KB (no document ingest) produces at least one GNN cluster/community after the triggering mechanism runs.
- `pyright` clean.

### Code touch points
- `backend/agent/coordinator.py` (modify — `handle_records_ingested` and/or `handle_graph_updated_for_analytics` wiring)
- `backend/config/schema.py` (modify, if a throttle/toggle field is added)
- `backend/records/README.md`, `backend/analytics/README.md` (modify)
- `backend/tests/agent/test_handle_records_ingested.py` (modify/new)

---

## Story analytics.35: Timeseries anomaly store never retracts stale rows
**ID:** analytics.35
**Status:** planned
**Prerequisites:** [analytics.07]
**Unblocks:** []
**Estimated size:** S

**As a** fraud analyst reviewing an entity's timeseries chart,
**I need** `timeseries_anomalies` rows that stop being anomalous under the latest detection pass to be removed rather than left in place,
**so that** `GET /analytics/timeseries/{entity_id}` never keeps flagging a bucket as an anomaly after a backfill or a config change means the current detection logic would no longer flag it.

### Current State
- `run_timeseries_stage` (`backend/agent/coordinator.py:2735`) recomputes detection over the full per-spec, per-KB series on every `RecordsIngestedEvent`, then calls `anomaly_store.write_anomalies(anomaly_records)` for whatever anomalies that pass found.
- `PostgresTimeseriesAnomalyStore.write_anomalies` (`backend/analytics/timeseries/adapters/postgres.py`, `_ANOMALY_UPSERT_SQL`) is `INSERT ... ON CONFLICT (knowledge_base_id, entity_id, metric_name, observed_at) DO UPDATE` — it upserts each detected anomaly but never deletes a `timeseries_anomalies` row for a bucket the current pass did *not* flag. `InMemoryTimeseriesAnomalyStore.write_anomalies` has the identical upsert-only shape (`backend/analytics/timeseries/adapters/in_memory.py:91-100`).
- `TimeseriesAnomalyStoreProtocol` (`backend/analytics/timeseries/adapters/protocols.py`) exposes only `write_anomalies` (upsert), `load_anomalies` (read), and `delete_by_kb` (whole-KB deletion, used only by the KB-delete cascade) — there is no per-metric or per-run replacement primitive.
- `get_timeseries_payload` (`backend/api/dependencies.py`) joins the record-aggregate series to `anomaly_store.load_anomalies(...)` purely by `observed_at` timestamp — it has no way to know a persisted anomaly row is stale, so an orphaned row renders as `is_anomaly=true` indefinitely.
- Consequence: a late-arriving backfill that changes an old bucket's aggregate value (so it's no longer `z_threshold` standard deviations from the baseline), or a config change that raises a metric's `z_threshold`, leaves the previously-written row in place — the API keeps reporting a bucket as anomalous that the current detection logic would no longer flag.
- Found during the Sprint 2026-28 B2 final whole-branch review (2026-07-19) as a durable-store honesty gap; low urgency at current (demo) scale since `raw_records` ingestion is append-mostly and historical-bucket backfills are rare in practice — not an active production incident.

### Acceptance Criteria
- [ ] `run_timeseries_stage`'s detection pass is treated as authoritative per `(knowledge_base_id, metric_name)`: each run's write replaces that metric's full anomaly row set rather than only upserting the anomalies found, so buckets that stop being anomalous are removed.
- [ ] `TimeseriesAnomalyStoreProtocol` gains a replacement primitive (e.g. `delete_by_kb_metric(knowledge_base_id, metric_name)` called immediately before `write_anomalies`, or an equivalent delete-then-write transaction) implemented on both `InMemoryTimeseriesAnomalyStore` and `PostgresTimeseriesAnomalyStore`, mirroring how `ObjectStoreClusterSummaryStore.put_clusters` (`backend/analytics/gnn/adapters/cluster_store.py`) already overwrites a KB's full cluster list on every GNN run instead of merging into stale results.
- [ ] The Postgres replacement happens inside the store's own write transaction (single connection, delete then inserts before commit) so a mid-run failure cannot leave a metric's anomaly rows partially cleared.
- [ ] A regression test demonstrates the retraction: seed an anomaly for a bucket, rerun detection with inputs that no longer flag it (via a raised `z_threshold` or a corrected aggregate), and assert the stale row is gone from both `load_anomalies` and the `GET /analytics/timeseries/{entity_id}` response.
- [ ] Coverage ≥ 85% on the modified store/stage paths.

### Verification
- `pytest backend/tests/analytics/timeseries -q` green, including the new retraction regression test.
- `pytest backend/tests/agent -q -k timeseries` green.
- `pyright` clean.

### Code touch points
- `backend/analytics/timeseries/adapters/protocols.py` (modify — new replacement method on `TimeseriesAnomalyStoreProtocol`)
- `backend/analytics/timeseries/adapters/in_memory.py` (modify)
- `backend/analytics/timeseries/adapters/postgres.py` (modify — replace the upsert-only write with a delete-then-write per `(kb, metric)`, inside one transaction)
- `backend/agent/coordinator.py` (modify — `run_timeseries_stage` write call)
- `backend/tests/analytics/timeseries/test_anomaly_store.py`, `backend/tests/analytics/timeseries/test_anomaly_store_postgres.py` (modify/new)
- `backend/tests/agent/test_coordinator.py` (modify — retraction regression test)
