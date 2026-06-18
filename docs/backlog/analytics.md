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
**Status:** planned
**Prerequisites:** [graph.06]
**Unblocks:** [analytics.04]
**Estimated size:** L
**As a** fraud-analytics engineer,
**I need** a graph-DB-backed `GraphSnapshotSource` that loads nodes + edges from Neo4j (and the in-memory backend) for a knowledge base,
**so that** `GnnService.analyze` can run against real ingested graphs rather than only what tests put into the in-memory source.

### Current State
- `GraphSnapshotSourceProtocol` (`backend/analytics/gnn/adapters/protocols.py:11-21`) has an explicit `TODO(production)` calling for filtered + incremental loads.
- Only `InMemoryGraphSnapshotSource` (`backend/analytics/gnn/adapters/in_memory.py:11-44`) exists.
- `get_graph_snapshot_source` (`backend/api/dependencies.py:660-662`) always returns `InMemoryGraphSnapshotSource()` with no config branch.
- `GraphServiceProtocol` exposes neighborhood/search but no whole-KB snapshot export today.

### Acceptance Criteria
- [ ] `GraphGraphSnapshotSource` adapter at `backend/analytics/gnn/adapters/graph_backed.py` consumes the new graph paginated/iterator surface from graph.06 and assembles `GraphSnapshot` instances bounded by an explicit `max_nodes` parameter.
- [ ] `load_clusters` reads cluster summaries that were written back by the analytics.24 handler (when present); empty list otherwise.
- [ ] `get_graph_snapshot_source` picks adapter by `DomainConfig.analytics.gnn_snapshot_backend: Literal["in_memory","graph"]`.
- [ ] Coverage ≥ 85% on the new adapter (integration test marked `@pytest.mark.integration` for the Neo4j path).

### Verification
- `pytest -m "not integration" backend/tests/analytics/gnn` green.
- `pytest -m integration backend/tests/analytics/gnn/test_graph_backed_source.py` green when Neo4j extras are installed.
- `pyright` clean.

### Code touch points
- `backend/analytics/gnn/adapters/graph_backed.py` (new)
- `backend/analytics/gnn/adapters/protocols.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/analytics/gnn/test_graph_backed_source.py` (new)

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

### Current State
- `_compute_embeddings` materializes a full `node_count × node_count` Laplacian and calls `np.linalg.eigh` — O(n³) time and O(n²) memory (`backend/analytics/gnn/service.py:287-345`).
- `_predict_links` is O(n²) double-loop over all node pairs (`backend/analytics/gnn/service.py:214-237`).
- No `max_nodes` guard exists in `GnnAnalysisRequest` and no per-stage memory metric is emitted.

### Acceptance Criteria
- [ ] `GnnAnalysisRequest` gains `max_nodes: int = 5000` (or similar) and `analyze()` raises `GnnInsufficientGraphError` (or new `GnnGraphTooLargeError`) when the source returns more nodes.
- [ ] `_compute_embeddings` is replaced by a sparse-matrix path (`scipy.sparse.linalg.eigsh` with `k=dimension`) so memory is O(n·k) rather than O(n²).
- [ ] `_predict_links` is replaced by approximate nearest-neighbor candidate selection (e.g. FAISS / annoy or a degree-capped neighborhood) and is documented in the README.
- [ ] Per-stage memory / duration counters emitted via the observability primitive from `_observability.04`.

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
**Status:** planned
**Prerequisites:** [analytics.24]
**Unblocks:** []
**Estimated size:** M
**As a** fraud analyst,
**I need** `GET /analytics/gnn/clusters` to return clusters derived from the graph (written back by the self-reinforcing loop) rather than only what tests stuff into the in-memory source,
**so that** cluster summaries are durable across worker restarts and reflect the latest analyze run.

### Current State
- `GnnService.list_clusters` reads `_snapshot_source.load_clusters` (`backend/analytics/gnn/service.py:149-169`).
- `InMemoryGraphSnapshotSource.load_clusters` (`backend/analytics/gnn/adapters/in_memory.py:43-44`) returns whatever fixtures pushed in via `put_clusters`; no production adapter writes cluster summaries anywhere.

### Acceptance Criteria
- [ ] `GraphGraphSnapshotSource.load_clusters` (analytics.03) reads `cluster_id`/`anomaly_score` from graph entity properties written by the analytics.24 handler.
- [ ] When no clusters exist, `list_clusters` returns an empty list (no error) — covered by a regression test.
- [ ] Coverage ≥ 85% on the read path.

### Verification
- `pytest backend/tests/analytics/gnn/test_service.py::test_list_clusters_from_graph -q` green.
- Manual integration: run a GNN analyze, observe `cluster_id` written on entities, then call `/analytics/gnn/clusters` and confirm the summaries match.

### Code touch points
- `backend/analytics/gnn/adapters/graph_backed.py` (modify)
- `backend/analytics/gnn/service.py` (modify)
- `backend/tests/analytics/gnn/test_service.py` (modify)

---

## Story analytics.06: Timeseries: Add Postgres `load_series` for per-entity metrics
**ID:** analytics.06
**Status:** planned
**Prerequisites:** [monitoring.02, records.07]
**Unblocks:** [frontend.04]
**Estimated size:** M
**As a** fraud-analytics engineer,
**I need** `TimeSeriesHistorySource.load_series` to return per-entity series populated by the monitoring/records `observations` write path, not only graph-scope metrics keyed on the `__graph__` sentinel,
**so that** per-entity anomaly detection runs against real observation streams.

### Current State
- `PostgresTimeSeriesHistorySource._SERIES_SQL` selects from `entity_metric_history` (`backend/analytics/timeseries/adapters/postgres.py:17-30`).
- `entity_metric_history` is only written by Flow 2 with `entity_id="__graph__"` (`backend/analytics/metrics/models.py:11-16`, `backend/agent/coordinator.py:1096-1300`).
- Per-entity observations land in `observations` via `monitoring/adapters/postgres.py::PostgresObservationStore`, but the timeseries adapter does not read them.

### Acceptance Criteria
- [ ] `PostgresTimeSeriesHistorySource` gains an `observations`-backed path (separate adapter or branch) keyed on `(knowledge_base_id, entity_id, metric_name)` and selected via `DomainConfig.analytics.timeseries_source: Literal["entity_metric_history","observations"]`.
- [ ] Cross-edge contract is documented in `backend/analytics/README.md` (per-entity timeseries reads `observations`, graph-scope reads `entity_metric_history`).
- [ ] Coverage ≥ 85% on the new branch; integration test runs against a Postgres fixture with seeded observation rows.

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
**Status:** planned
**Prerequisites:** [database.05]
**Unblocks:** [analytics.08, ingestion.19]
**Estimated size:** S
**As a** API developer,
**I need** `get_timeseries_history_source()` to select the Postgres adapter when `DomainConfig.database.backend == "postgres"`,
**so that** `/analytics/timeseries` reads from the same hypertable that Flow 2 writes to, instead of always returning empty in-memory data.

### Current State
- `get_timeseries_history_source` (`backend/api/dependencies.py:644-647`) is hardcoded to `InMemoryTimeSeriesHistorySource()`.
- `PostgresTimeSeriesHistorySource` already ships (`backend/analytics/timeseries/adapters/postgres.py:33-94`) but has no DI caller.

### Acceptance Criteria
- [ ] `get_timeseries_history_source` returns `PostgresTimeSeriesHistorySource(provider)` when the connection provider is non-None.
- [ ] An override hook (DI dependency override) lets tests inject the in-memory adapter without env shenanigans.
- [ ] A request-level integration test demonstrates `/analytics/timeseries?kb_id=…` returning seeded Postgres rows.

### Verification
- `pytest backend/tests/api/test_analytics_router.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/api/dependencies.py` (modify)
- `backend/tests/api/test_analytics_router.py` (modify)

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
**Status:** planned
**Prerequisites:** [llm.06, analytics.16]
**Unblocks:** []
**Estimated size:** M
**As a** investigator,
**I need** evidence-pack narratives composed by an LLM (with structured headings, claims, and citations to evidence items), not a space-joined string of rationales,
**so that** packs read as analyst-ready prose rather than a debug dump.

### Current State
- `_build_reasoning` joins string rationales with spaces (`backend/analytics/explainability/service.py:115-123`).
- `_build_narrative` groups by `source_type` only (`backend/analytics/explainability/service.py:126-148`).
- Module-level `TODO(production)` on `ExplainabilityService` (`backend/analytics/explainability/service.py:30-33`) explicitly calls for LLM-generated narrative explanations.

### Acceptance Criteria
- [ ] `NarrativeGeneratorProtocol` introduced under `backend/analytics/explainability/protocols.py` with a `summarize(items, context) -> ExplanationNarrative` method.
- [ ] `LlmNarrativeGenerator` adapter consumes an `LlmServiceProtocol` (cross-edge to llm.md) and emits multi-section prose grounded in `ExplanationItem.source_id` references.
- [ ] `DeterministicNarrativeGenerator` retains the legacy join-of-rationales behaviour for tests and offline mode.
- [ ] `ExplainabilityService.generate` dispatches via the protocol; `DomainConfig.analytics.narrative_backend` selects.

### Verification
- `pytest backend/tests/analytics/explainability -q` green.
- Integration test stubs an LLM client and asserts the narrative contains structured sections matching the input items.
- `pyright` clean.

### Code touch points
- `backend/analytics/explainability/protocols.py` (modify)
- `backend/analytics/explainability/service.py` (modify)
- `backend/analytics/explainability/adapters/llm_narrative.py` (new)
- `backend/analytics/explainability/adapters/deterministic.py` (new)
- `backend/config/schema.py` (modify)
- `backend/api/dependencies.py` (modify)
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

### Current State
- `ShapExplainabilityContextSource` exists (`backend/analytics/explainability/adapters/shap_adapter.py:97-158`) but is never registered in DI.
- API only exposes `InMemoryExplainabilityContextSource` (no `get_explainability_*` helper in `backend/api/dependencies.py`).
- No LIME or permutation-importance adapter exists.

### Acceptance Criteria
- [ ] `get_explainability_context_source` factory added to `backend/api/dependencies.py` keyed by `DomainConfig.analytics.explainability_backend: Literal["in_memory","shap","lime"]`.
- [ ] `LimeExplainabilityContextSource` (or `PermutationImportanceContextSource`) added under `backend/analytics/explainability/adapters/` with lazy import.
- [ ] Coverage ≥ 85% on each new adapter (integration test marked `@pytest.mark.integration` for the SHAP and LIME paths).
- [ ] SHAP unit/integration test exists where there was none.

### Verification
- `pytest -m integration backend/tests/analytics/explainability/test_shap_adapter.py -q` green.
- `pyright` clean.

### Code touch points
- `backend/api/dependencies.py` (modify)
- `backend/analytics/explainability/adapters/lime_adapter.py` (new)
- `backend/analytics/explainability/adapters/shap_adapter.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/analytics/explainability/test_shap_adapter.py` (new)
- `backend/tests/analytics/explainability/test_lime_adapter.py` (new)

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
**Unblocks:** [analytics.05]
**Estimated size:** M
**As a** fraud-analytics engineer,
**I need** a worker handler that consumes `GnnAnalyzedEvent` and writes `cluster_id`, `predicted_neighbor_ids`, and `anomaly_score` back onto graph entities,
**so that** subsequent risk and timeseries analyses can use GNN-derived structural features.

### Current State
- `GnnAnalyzedEvent` carries reference counts only (`backend/events/types.py:258-269`).
- No `handle_gnn_analyzed_for_graph` exists in `backend/agent/coordinator.py`.
- Architecture §6.7 (`docs/architecture.md:757-764`) calls for this feedback loop.

### Acceptance Criteria
- [ ] `GnnAnalyzedEvent` (or a new `GnnAnalyzedDetailEvent`) gains optional per-entity reference fields (`cluster_id`, `score`) sufficient for the handler to update entities without re-fetching the full analysis (cross-edge to events.04 for catalog drift).
- [ ] New `handle_gnn_analyzed_for_graph` handler in `backend/agent/coordinator.py` calls `GraphService.update_entity_properties` for each scored node, idempotent on redelivery.
- [ ] Property contract (`cluster_id`, `predicted_neighbor_ids`, `anomaly_score`, `gnn_analyzed_at`) documented in `backend/agent/AGENT.md`.
- [ ] Coverage ≥ 85% on the handler.

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
**Status:** planned
**Prerequisites:** [api.29, frontend.04]
**Unblocks:** []
**Estimated size:** M
**As a** API maintainer,
**I need** `/analytics/risk-scores/{entity_id}` and `/analytics/timeseries/{entity_id}` to read from the live service + persistence layer rather than the seeded in-memory payloads in `ApiState`,
**so that** the dashboard and entity-detail views reflect real data and the seeded fallback can be removed.

### Current State
- `/analytics/overview` now uses `get_analytics_overview_payload` and `build_analytics_overview(...)` to aggregate durable alert projections, durable cases, and KB metadata (`backend/api/dependencies.py`, `backend/api/_analytics_overview.py`).
- `/analytics/risk-scores/{entity_id}` and `/analytics/timeseries/{entity_id}` still read from `ApiState.get_risk_score` / `ApiState.get_timeseries` (`backend/api/dependencies.py`).
- Seeded `ApiState` analytics helpers remain for the entity-scoped shortcuts.

### Acceptance Criteria
- [ ] Remaining entity-scoped endpoints switch to DI factories that compose the live analytics services and persistence (`get_risk_service`, `get_timeseries_service`, the metric repository).
- [ ] Deprecation note in `backend/api/AGENT.md` (if present) or `backend/api/state.py` docstring.
- [ ] `ApiState` seeded analytics payloads removed once api.01 ships (or moved to a `tools/seed_demo_state.py`).
- [ ] Frontend Dashboard/EntityDetail (frontend.04) confirmed to render correctly on live data.

### Verification
- `pytest backend/tests/api/test_analytics_router.py -q` green.
- Manual e2e: load Dashboard against a freshly-ingested KB, observe live metrics.
- `pyright` clean.

### Code touch points
- `backend/api/routers/analytics.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/api/state.py` (modify)
- `backend/tests/api/test_analytics_router.py` (modify)

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
