# analytics/gnn

Graph-structure analysis over a knowledge base's entity graph: node scoring,
community detection, spectral node embeddings and link prediction. The name is
aspirational — the current algorithms are deterministic heuristics (weighted
degree, Jaccard-style similarity, Laplacian eigenvectors via `networkx` +
`numpy`), not a trained graph neural network. It is the first stage of the
worker's Flow B and backs the `/analytics/gnn/clusters` read model.

See the package-level guide, [`../README.md`](../README.md), for the shared
analytics conventions this module follows.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | Internal models: `GraphNodeSignal`, `GraphEdgeSignal`, `GraphSnapshot`, `ScoredNode`, `PredictedLink`, `GnnCommunity`, `GnnAnalysisResult`, `ClusterSummary`. |
| `service_models.py` | API/service boundary: `GnnAnalysisRequest`/`GnnAnalysisResponse`, `GnnNodeScore`, `GnnLinkPrediction`, `GnnCommunityResult`, `GnnClusterRequest`/`GnnClusterResponse`, `ClusterResult`. |
| `protocols.py` | `GnnServiceProtocol` — `analyze` and `list_clusters`. |
| `service.py` | `GnnService` / `create_gnn_service`: loads a snapshot, scores nodes, detects communities, computes embeddings, predicts links, publishes `GnnAnalyzedEvent`. |
| `adapters/protocols.py` | `GraphSnapshotSourceProtocol` (`load_snapshot`, `load_clusters`) and `ClusterSummaryStoreProtocol` (`put_clusters`, `load_clusters`, `delete_by_kb`). |
| `adapters/graph_repository_source.py` | `GraphRepositorySnapshotSource` — builds a `GraphSnapshot` from any `graph` `GraphRepository` (in-memory or Neo4j), truncated to the top-N nodes by degree. |
| `adapters/cluster_store.py` | `InMemoryClusterSummaryStore` and `ObjectStoreClusterSummaryStore` (JSON at `system/analytics/gnn_clusters/<kb_id>.json`). |
| `adapters/in_memory.py` | `InMemoryGraphSnapshotSource` — seeded snapshots for tests. |
| `exceptions.py` | `GnnError` and subclasses `GnnConfigurationError`, `GnnDisabledError`, `GnnInsufficientGraphError`, `GnnSnapshotUnavailableError`, `GnnSourceError`. |

## Contracts and invariants

- `analyze` raises `GnnDisabledError` when the injected `gnn_enabled` callable
  returns false (wired to `config.capabilities.gnn`); `list_clusters` returns
  an empty list instead of raising in that case.
- A snapshot with fewer than two nodes raises `GnnInsufficientGraphError`; an
  empty KB raises `GnnSnapshotUnavailableError`. Unexpected source failures are
  wrapped in `GnnSourceError`.
- `GraphRepositorySnapshotSource` bounds the snapshot by
  `DomainConfig.gnn.snapshot_max_nodes` (`GnnConfig`, default 5000), keeping the
  highest-degree nodes and logging a warning when it truncates. Entities are
  read a page at a time, but relationships are read in one call and degree
  ranking needs the full graph, so the *read* is not bounded — only the
  snapshot handed to the service.
- `networkx` is imported lazily; without the `analytics` extra, `analyze`
  raises `GnnConfigurationError`.
- `GnnAnalyzedEvent` (`gnn.analyzed`) is published after every successful
  `analyze`. No worker handler subscribes to it (see
  [`docs/ledger/event-catalog.md`](../../../docs/ledger/event-catalog.md)).

## How it is reached

- **Worker (Flow B):** `agent/coordinator.py::handle_graph_updated_for_analytics`
  calls `_run_gnn_stage` (disabled / no snapshot / insufficient graph are logged
  skips; other `GnnError`s publish `analysis.failed`) and then
  `_persist_gnn_clusters`, which writes each community as a `ClusterSummary`
  whose `anomaly_score` is the max node score among its members. A skipped GNN
  stage skips the rest of Flow B (risk, explainability) for that document;
  otherwise `_write_analytics_properties_to_graph` writes the GNN-derived
  properties back onto each upserted entity.
- **API:** `GET /analytics/gnn/clusters` (viewer) in `api/routers/analytics.py`
  serves `list_clusters` from the cluster store wired in `api/dependencies.py`.
- **Embeddings:** `agent/embeddings_graph_bridge.py::GnnGraphEmbeddingProvider`
  exposes `analyze`'s node embeddings through the embeddings module's
  `GraphEmbeddingProviderProtocol`.

## Persistence

No Postgres tables. Cluster summaries live in the object store
(`ObjectStoreClusterSummaryStore`) and are removed on KB deletion by the
`gnn_clusters` step in `knowledgebases/cleanup.py`.

## Current gaps (from `TODO(production)` in code)

- `GnnService`: heuristic scoring and link prediction stand in for model-based
  inference (PyTorch Geometric / DGL).
- `GraphSnapshotSourceProtocol`: no filtered or incremental snapshot loading.

## Tests

`tests/analytics/gnn/` — models, service, in-memory source, graph-repository
source (truncation), cluster stores, and `test_gnn_live_integration.py`
(`@pytest.mark.integration`, live Neo4j round trip).
