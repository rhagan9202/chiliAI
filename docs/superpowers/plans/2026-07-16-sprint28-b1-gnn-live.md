# Sprint 2026-28 B1 — GNN Live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed the existing GNN engine real graph data so clustering, link prediction, and community scores go live end-to-end (pipeline → persistence → `GET /analytics/gnn/clusters` → dashboard), per `docs/superpowers/specs/2026-07-16-sprint28-cms-fraud-workbench-design.md` §3.1 B1.

**Architecture:** A `GraphRepositorySnapshotSource` implements the existing `GraphSnapshotSourceProtocol` by wrapping `GraphRepository` (`get_entities`/`get_relationships`) — backend-agnostic (Neo4j + in-memory). Node features = numeric entity properties (deterministic order) + degree; snapshot bounded by a config-knobbed top-degree node cap. A new `ClusterSummaryStore` (in-memory + object-store) persists communities after each pipeline GNN run so `load_clusters` serves real data; the store joins the KB-delete cascade. The pipeline stage (`GraphUpdatedEvent → analyze`) and per-entity `community_id`/`centrality_score` write-back already exist — no new pipeline wiring.

**Tech Stack:** Python 3.12, Pydantic v2, networkx/numpy (already in use by GnnService), FastAPI, object store protocol.

## Global Constraints

- No hardcoded domain types; feature extraction is generic over `Entity.properties` (spec §3.1).
- Cross-module imports only via the three sanctioned paths; `analytics/gnn` may import `graph.adapters.protocols` (protocol contract) and `storage.protocols`, never concrete adapters of other modules.
- Contract changes ADDITIVE ONLY. `DomainConfig` gains an optional `gnn` section — regen: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` (repo root) then `cd chili_app && npm run codegen:api && npm run build` (build is mandatory after regen — Vitest does not type-check).
- Gates from `/home/rdhagan92/chiliAI/backend`: targeted suites per task; full `.venv/bin/pytest -q -m "not integration"`; bare `.venv/bin/pyright` 0 errors; `.venv/bin/ruff check --no-cache .` (always `--no-cache`). `make test` (host venv, chili_test) for the full pass.
- GNN stage failures stay non-fatal: existing `_run_gnn_stage` catch/skip semantics must not change.
- Caps must log when they truncate — no silent partiality (spec §3.1).
- All commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Live verification (Task 6) is RESERVED FOR THE CONTROLLER (no Docker in subagents).

---

### Task 1: `ClusterSummaryStore` protocol + in-memory + object-store adapters

**Files:**
- Modify: `backend/analytics/gnn/adapters/protocols.py` (add `ClusterSummaryStoreProtocol`)
- Create: `backend/analytics/gnn/adapters/cluster_store.py`
- Test: `backend/tests/analytics/gnn/test_cluster_store.py` (new)

**Interfaces:**
- Consumes: `analytics.gnn.models.ClusterSummary` (existing), `storage.protocols.ObjectStore` (existing: `put_bytes(key, content, *, media_type, metadata)`, `get_bytes(key)`, `exists(key)`, `delete(key)`, `list_keys(prefix)`).
- Produces:
  ```python
  @runtime_checkable
  class ClusterSummaryStoreProtocol(Protocol):
      def put_clusters(self, knowledge_base_id: str, clusters: list[ClusterSummary]) -> None: ...
      def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]: ...
      def delete_by_kb(self, knowledge_base_id: str) -> None: ...
  ```
  `InMemoryClusterSummaryStore()` and `ObjectStoreClusterSummaryStore(object_store)` (storage key `system/analytics/gnn_clusters/{knowledge_base_id}.json`).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for GNN cluster summary stores."""

from __future__ import annotations

from analytics.gnn.adapters.cluster_store import (
    InMemoryClusterSummaryStore,
    ObjectStoreClusterSummaryStore,
)
from analytics.gnn.models import ClusterSummary
from storage.adapters.in_memory import InMemoryObjectStore


def _summary(cluster_id: str, *, score: float = 0.5) -> ClusterSummary:
    return ClusterSummary(
        cluster_id=cluster_id,
        entity_ids=[f"{cluster_id}-a", f"{cluster_id}-b"],
        anomaly_score=score,
    )


def test_in_memory_store_round_trips_and_replaces() -> None:
    store = InMemoryClusterSummaryStore()
    assert store.load_clusters(knowledge_base_id="kb-1") == []
    store.put_clusters("kb-1", [_summary("c-1")])
    store.put_clusters("kb-1", [_summary("c-2"), _summary("c-3")])
    loaded = store.load_clusters(knowledge_base_id="kb-1")
    assert [s.cluster_id for s in loaded] == ["c-2", "c-3"]  # replace, not append
    assert store.load_clusters(knowledge_base_id="kb-other") == []


def test_in_memory_store_delete_by_kb() -> None:
    store = InMemoryClusterSummaryStore()
    store.put_clusters("kb-1", [_summary("c-1")])
    store.put_clusters("kb-2", [_summary("c-9")])
    store.delete_by_kb("kb-1")
    assert store.load_clusters(knowledge_base_id="kb-1") == []
    assert [s.cluster_id for s in store.load_clusters(knowledge_base_id="kb-2")] == ["c-9"]
    store.delete_by_kb("kb-missing")  # idempotent no-op


def test_object_store_round_trips_across_instances() -> None:
    object_store = InMemoryObjectStore()
    ObjectStoreClusterSummaryStore(object_store).put_clusters("kb-1", [_summary("c-1", score=0.9)])
    reloaded = ObjectStoreClusterSummaryStore(object_store).load_clusters(knowledge_base_id="kb-1")
    assert len(reloaded) == 1
    assert reloaded[0].cluster_id == "c-1"
    assert reloaded[0].anomaly_score == 0.9


def test_object_store_delete_by_kb_removes_key() -> None:
    object_store = InMemoryObjectStore()
    store = ObjectStoreClusterSummaryStore(object_store)
    store.put_clusters("kb-1", [_summary("c-1")])
    store.delete_by_kb("kb-1")
    assert store.load_clusters(knowledge_base_id="kb-1") == []
    assert not object_store.exists("system/analytics/gnn_clusters/kb-1.json")
    store.delete_by_kb("kb-1")  # idempotent no-op
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/analytics/gnn/test_cluster_store.py -q`
Expected: FAIL — `ModuleNotFoundError: analytics.gnn.adapters.cluster_store`.

- [ ] **Step 3: Implement**

`adapters/protocols.py`: add `ClusterSummaryStoreProtocol` exactly as in Interfaces (import `ClusterSummary` already present); extend `__all__`.

`adapters/cluster_store.py`:

```python
"""Durable cluster-summary stores for GNN pipeline results."""

from __future__ import annotations

from pydantic import BaseModel, Field

from analytics.gnn.models import ClusterSummary
from storage.protocols import ObjectStore

__all__ = ["InMemoryClusterSummaryStore", "ObjectStoreClusterSummaryStore"]


class _ClusterSnapshot(BaseModel):
    """Serialized per-KB cluster list for object-store persistence."""

    clusters: list[ClusterSummary] = Field(default_factory=list[ClusterSummary])


class InMemoryClusterSummaryStore:
    """Process-local cluster summary store for tests and in-memory stacks."""

    def __init__(self) -> None:
        self._clusters: dict[str, list[ClusterSummary]] = {}

    def put_clusters(self, knowledge_base_id: str, clusters: list[ClusterSummary]) -> None:
        self._clusters[knowledge_base_id] = list(clusters)

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        return list(self._clusters.get(knowledge_base_id, []))

    def delete_by_kb(self, knowledge_base_id: str) -> None:
        self._clusters.pop(knowledge_base_id, None)


class ObjectStoreClusterSummaryStore:
    """Cluster summaries persisted per-KB in the configured object store."""

    _KEY_PREFIX = "system/analytics/gnn_clusters/"

    def __init__(self, object_store: ObjectStore) -> None:
        self._object_store = object_store

    def _key(self, knowledge_base_id: str) -> str:
        return f"{self._KEY_PREFIX}{knowledge_base_id}.json"

    def put_clusters(self, knowledge_base_id: str, clusters: list[ClusterSummary]) -> None:
        snapshot = _ClusterSnapshot(clusters=list(clusters))
        self._object_store.put_bytes(
            self._key(knowledge_base_id),
            snapshot.model_dump_json().encode("utf-8"),
            media_type="application/json",
            metadata={"record_type": "gnn_cluster_summaries"},
        )

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        key = self._key(knowledge_base_id)
        if not self._object_store.exists(key):
            return []
        stored = self._object_store.get_bytes(key)
        return list(_ClusterSnapshot.model_validate_json(stored.content).clusters)

    def delete_by_kb(self, knowledge_base_id: str) -> None:
        self._object_store.delete(self._key(knowledge_base_id))
```

(Verify `ObjectStore.delete` is a missing-key no-op — `storage/adapters/local_fs_adapter.py` documents "missing objects are a no-op"; mirror-check the in-memory adapter. If not a no-op there, guard with `exists`.)

- [ ] **Step 4: Run tests + gates**

Run: `.venv/bin/pytest tests/analytics/gnn -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/gnn backend/tests/analytics/gnn
git commit -m "feat(analytics): ClusterSummaryStore protocol with in-memory and object-store adapters (B1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `GraphRepositorySnapshotSource` — real snapshots from the graph repository

**Files:**
- Create: `backend/analytics/gnn/adapters/graph_repository_source.py`
- Test: `backend/tests/analytics/gnn/test_graph_repository_source.py` (new)

**Interfaces:**
- Consumes: `graph.adapters.protocols.GraphRepository` (`get_entities(knowledge_base_id) -> list[Entity]`, `get_relationships(knowledge_base_id) -> list[Relationship]`); `ClusterSummaryStoreProtocol` from Task 1; `shared.types.Entity` (`id`, `type`, `properties: dict[str, object]`), `Relationship` (`source_id`, `target_id`, `weight: float | None`).
- Produces:
  ```python
  class GraphRepositorySnapshotSource:
      def __init__(
          self,
          repository: GraphRepository,
          cluster_store: ClusterSummaryStoreProtocol,
          *,
          max_nodes: int = 5000,
      ) -> None: ...
      def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot: ...  # GnnSnapshotUnavailableError when KB has no entities
      def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]: ...  # delegates to cluster_store
  ```
  Feature vector per node: `[degree] + [float value of each numeric property, sorted by property name]` — numeric = `int`/`float` (not `bool`), plus strings parseable as float. Degree first guarantees `GraphNodeSignal`'s ≥1-feature invariant. Cap: when entity count exceeds `max_nodes`, keep the top-`max_nodes` by degree (ties broken by entity id for determinism), drop edges touching dropped nodes, and `logger.warning` the truncation with kept/dropped counts.

- [ ] **Step 1: Write the failing tests** (use `InMemoryGraphRepository` from `graph.adapters.in_memory` seeded via its public `upsert_entities`/`upsert_relationships` — same pattern as `tests/graph/test_in_memory_adapter.py`):

```python
"""Tests for the graph-repository-backed GNN snapshot source."""

from __future__ import annotations

import logging

import pytest

from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource
from analytics.gnn.exceptions import GnnSnapshotUnavailableError
from analytics.gnn.models import ClusterSummary
from graph.adapters.in_memory import InMemoryGraphRepository
from shared.types import Entity, Relationship


def _source(
    repository: InMemoryGraphRepository, *, max_nodes: int = 5000
) -> GraphRepositorySnapshotSource:
    return GraphRepositorySnapshotSource(
        repository, InMemoryClusterSummaryStore(), max_nodes=max_nodes
    )


def _seed_triangle(repository: InMemoryGraphRepository, kb: str) -> None:
    repository.upsert_entities(
        kb,
        [
            Entity(id="e-1", type="provider", properties={"amount": 100, "npi": "x"}),
            Entity(id="e-2", type="claim", properties={"amount": 25.5}),
            Entity(id="e-3", type="claim", properties={}),
        ],
    )
    repository.upsert_relationships(
        kb,
        [
            Relationship(id="r-1", type="billed", source_id="e-2", target_id="e-1", weight=2.0),
            Relationship(id="r-2", type="billed", source_id="e-3", target_id="e-1"),
        ],
    )


def test_load_snapshot_builds_features_and_edges() -> None:
    repository = InMemoryGraphRepository()
    _seed_triangle(repository, "kb-1")

    snapshot = _source(repository).load_snapshot(knowledge_base_id="kb-1")

    assert snapshot.knowledge_base_id == "kb-1"
    nodes = {node.entity_id: node for node in snapshot.nodes}
    assert set(nodes) == {"e-1", "e-2", "e-3"}
    # degree first, then numeric properties sorted by name; non-numeric skipped
    assert nodes["e-1"].feature_values == [2.0, 100.0]
    assert nodes["e-2"].feature_values == [1.0, 25.5]
    assert nodes["e-3"].feature_values == [1.0]  # degree only — invariant holds
    edges = {(edge.source_id, edge.target_id): edge.weight for edge in snapshot.edges}
    assert edges[("e-2", "e-1")] == 2.0
    assert edges[("e-3", "e-1")] == 1.0  # default weight when relationship weight is None


def test_load_snapshot_empty_kb_raises_unavailable() -> None:
    with pytest.raises(GnnSnapshotUnavailableError):
        _source(InMemoryGraphRepository()).load_snapshot(knowledge_base_id="kb-empty")


def test_load_snapshot_caps_to_top_degree_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = InMemoryGraphRepository()
    # hub e-hub connects to e-1..e-4; e-iso is isolated (degree 0)
    repository.upsert_entities(
        "kb-1",
        [Entity(id=f"e-{i}", type="claim", properties={}) for i in (1, 2, 3, 4)]
        + [Entity(id="e-hub", type="provider", properties={}), Entity(id="e-iso", type="claim", properties={})],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(id=f"r-{i}", type="billed", source_id=f"e-{i}", target_id="e-hub")
            for i in (1, 2, 3, 4)
        ],
    )

    with caplog.at_level(logging.WARNING):
        snapshot = _source(repository, max_nodes=5).load_snapshot(knowledge_base_id="kb-1")

    kept = {node.entity_id for node in snapshot.nodes}
    assert len(kept) == 5
    assert "e-hub" in kept and "e-iso" not in kept  # lowest degree dropped
    assert len(snapshot.edges) == 4  # no edge touches a dropped node
    assert any("truncat" in record.message.lower() for record in caplog.records)


def test_bool_properties_are_not_numeric_features() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e-1", type="claim", properties={"flagged": True, "amount": 10}),
            Entity(id="e-2", type="claim", properties={}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [Relationship(id="r-1", type="rel", source_id="e-1", target_id="e-2")],
    )
    snapshot = _source(repository).load_snapshot(knowledge_base_id="kb-1")
    node = next(n for n in snapshot.nodes if n.entity_id == "e-1")
    assert node.feature_values == [1.0, 10.0]  # bool excluded


def test_load_clusters_delegates_to_store() -> None:
    repository = InMemoryGraphRepository()
    store = InMemoryClusterSummaryStore()
    store.put_clusters("kb-1", [ClusterSummary(cluster_id="c-1", entity_ids=["e-1"], anomaly_score=0.4)])
    source = GraphRepositorySnapshotSource(repository, store)
    assert [c.cluster_id for c in source.load_clusters(knowledge_base_id="kb-1")] == ["c-1"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/analytics/gnn/test_graph_repository_source.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** `adapters/graph_repository_source.py`:

```python
"""Graph-repository-backed snapshot source: feeds the GNN engine real graph data."""

from __future__ import annotations

import logging

from analytics.gnn.adapters.protocols import ClusterSummaryStoreProtocol
from analytics.gnn.exceptions import GnnSnapshotUnavailableError
from analytics.gnn.models import ClusterSummary, GraphEdgeSignal, GraphNodeSignal, GraphSnapshot
from graph.adapters.protocols import GraphRepository
from shared.types import Entity

logger = logging.getLogger(__name__)

__all__ = ["GraphRepositorySnapshotSource"]

_DEFAULT_MAX_NODES = 5000


def _numeric_features(entity: Entity) -> list[float]:
    """Numeric property values sorted by property name; bools excluded."""
    values: list[tuple[str, float]] = []
    for name, value in entity.properties.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values.append((name, float(value)))
        elif isinstance(value, str):
            try:
                values.append((name, float(value)))
            except ValueError:
                continue
    return [value for _, value in sorted(values)]


class GraphRepositorySnapshotSource:
    """Build bounded GNN snapshots from the configured graph repository."""

    def __init__(
        self,
        repository: GraphRepository,
        cluster_store: ClusterSummaryStoreProtocol,
        *,
        max_nodes: int = _DEFAULT_MAX_NODES,
    ) -> None:
        self._repository = repository
        self._cluster_store = cluster_store
        self._max_nodes = max_nodes

    def load_snapshot(self, *, knowledge_base_id: str) -> GraphSnapshot:
        entities = self._repository.get_entities(knowledge_base_id)
        if not entities:
            raise GnnSnapshotUnavailableError(
                f"Knowledge base '{knowledge_base_id}' has no graph entities yet."
            )
        relationships = self._repository.get_relationships(knowledge_base_id)

        degree: dict[str, int] = {entity.id: 0 for entity in entities}
        for relationship in relationships:
            if relationship.source_id in degree:
                degree[relationship.source_id] += 1
            if relationship.target_id in degree:
                degree[relationship.target_id] += 1

        if len(entities) > self._max_nodes:
            ranked = sorted(entities, key=lambda e: (-degree[e.id], e.id))
            kept, dropped = ranked[: self._max_nodes], ranked[self._max_nodes :]
            logger.warning(
                "GNN snapshot truncated for kb=%s: kept top-%d of %d nodes by degree "
                "(%d dropped).",
                knowledge_base_id, self._max_nodes, len(entities), len(dropped),
            )
            entities = kept
        kept_ids = {entity.id for entity in entities}

        nodes = [
            GraphNodeSignal(
                entity_id=entity.id,
                feature_values=[float(degree[entity.id])] + _numeric_features(entity),
                metadata={"entity_type": entity.type},
            )
            for entity in entities
        ]
        edges = [
            GraphEdgeSignal(
                source_id=relationship.source_id,
                target_id=relationship.target_id,
                weight=relationship.weight if relationship.weight is not None else 1.0,
            )
            for relationship in relationships
            if relationship.source_id in kept_ids and relationship.target_id in kept_ids
        ]
        return GraphSnapshot(knowledge_base_id=knowledge_base_id, nodes=nodes, edges=edges)

    def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
        return self._cluster_store.load_clusters(knowledge_base_id=knowledge_base_id)
```

(Adjust `Relationship.weight` handling to the actual field type in `shared/types.py` — read it first; if `weight` is non-optional with a default, drop the `None` branch and the test's comment.)

- [ ] **Step 4: Run tests + gates** — `pytest tests/analytics/gnn -q`, pyright, ruff → green.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/gnn backend/tests/analytics/gnn
git commit -m "feat(analytics): graph-repository-backed GNN snapshot source with degree cap (B1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `gnn` config section + factory wiring (worker + API)

**Files:**
- Modify: `backend/config/schema.py` (add `GnnConfig` section; wire into `DomainConfig` like sibling sections)
- Modify: `backend/agent/coordinator.py:563-573` (`build_graph_snapshot_source`) and its call site (`coordinator.py:1002-1007` region — pass repository + object store)
- Modify: `backend/api/dependencies.py:1281-1283` (`get_graph_snapshot_source`) — memoized per app like sibling config-derived singletons; register in the config-cache reset registry if siblings are (read `CONFIG_CACHE_REGISTRY` usage first and follow it)
- Modify: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts` (regen)
- Test: `backend/tests/config/test_schema.py` (section defaults), `backend/tests/agent/test_coordinator.py` (factory), `backend/tests/api/test_dependencies.py` or the module where sibling `get_*` factories are tested (read first, extend in place)

**Interfaces:**
- Produces: `DomainConfig.gnn: GnnConfig` with `GnnConfig(snapshot_max_nodes: int = Field(default=5000, gt=0))`; `build_graph_snapshot_source(config, *, repository, object_store) -> GraphSnapshotSourceProtocol` returning `GraphRepositorySnapshotSource(repository, ObjectStoreClusterSummaryStore(object_store), max_nodes=config.gnn.snapshot_max_nodes)`; API `get_graph_snapshot_source` mirroring it from DI (`get_graph_repository()`, `get_object_store()`).
- Consumes: Tasks 1–2 classes.

- [ ] **Step 1: Failing tests.** (a) `GnnConfig` defaults: `DomainConfig` built from a minimal dict has `config.gnn.snapshot_max_nodes == 5000`; explicit YAML value round-trips. (b) Coordinator factory returns `GraphRepositorySnapshotSource` wired to the given repository (seed a 2-node KB through the repository, then `source.load_snapshot(...)` returns it). (c) API `get_graph_snapshot_source` returns the repository-backed source (follow the sibling memoized-singleton test pattern in the file you extend — read it first).

- [ ] **Step 2: Verify failure** — attribute/type errors as expected.

- [ ] **Step 3: Implement.** Schema: follow an existing optional section (e.g. how `scorecards`/`analytics`-style sections default via the post-validator — read `config/schema.py`'s pattern for sections with model defaults and copy it exactly). Coordinator: change signature to `build_graph_snapshot_source(config: DomainConfig, *, repository: GraphRepository, object_store: ObjectStore)`; update the single call site (`create_gnn_service(...)` block) to pass the worker's already-built repository + object store. API: build from `get_graph_repository()` + `get_object_store()` + active config, memoized consistently with siblings.

- [ ] **Step 4: Regen contracts** (repo root): export_openapi, `npm run codegen:api`, `npm run build` — `git diff --stat chili_app` shows only generated files.

- [ ] **Step 5: Run + gates** — `pytest tests/config tests/agent tests/api -q -m "not integration"`, pyright, ruff, `cd chili_app && npm run lint && npm run test:run && npm run build` → green.

- [ ] **Step 6: Commit**

```bash
git add backend/config backend/agent backend/api backend/tests chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(analytics,config): wire repository-backed GNN snapshot source via DomainConfig.gnn (B1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Persist communities after the pipeline GNN stage

**Files:**
- Modify: `backend/agent/coordinator.py` (Flow B handler `handle_graph_updated_for_analytics`, after the `_run_gnn_stage` call at ~line 1982; new helper `_persist_gnn_clusters`)
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Consumes: `GnnAnalysisResponse.communities: list[GnnCommunityResult(community_id, member_entity_ids, density)]`, `.scored_nodes: list[GnnNodeScore(entity_id, score, cluster_id)]`; `ClusterSummaryStoreProtocol.put_clusters` (Task 1).
- Produces: after a successful GNN stage, `ClusterSummary(cluster_id=community.community_id, entity_ids=community.member_entity_ids, anomaly_score=max member ScoredNode.score, default 0.0, label=None)` per community, persisted via the store. Store failure logs a warning and never fails the pipeline (mirror `_write_analytics_properties_to_graph`'s catch pattern). The worker's cluster store is the same `ObjectStoreClusterSummaryStore` instance the snapshot source holds — build it once in `build_worker_dependencies` and pass to both.

- [ ] **Step 1: Failing test.** Extend the Flow B test that stubs the GNN service (find the existing `handle_graph_updated_for_analytics` test that seeds a snapshot via `InMemoryGraphSnapshotSource` — it now seeds through an `InMemoryGraphRepository` + `InMemoryClusterSummaryStore` per Task 3's factory): after handling a `GraphUpdatedEvent` for a KB whose snapshot yields ≥1 community, `cluster_store.load_clusters(knowledge_base_id=kb)` returns summaries whose `cluster_id`s match the response communities and whose `anomaly_score` equals the max member score. Second test: a store whose `put_clusters` raises → handler still completes, warning logged, downstream stages unaffected.

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement** `_persist_gnn_clusters(*, cluster_store, knowledge_base_id, gnn_response)`:

```python
def _persist_gnn_clusters(
    *,
    cluster_store: ClusterSummaryStoreProtocol,
    knowledge_base_id: str,
    gnn_response: GnnAnalysisResponse,
) -> None:
    """Persist pipeline community results so /analytics/gnn/clusters serves real data."""
    score_by_entity = {node.entity_id: node.score for node in gnn_response.scored_nodes}
    summaries = [
        ClusterSummary(
            cluster_id=community.community_id,
            entity_ids=list(community.member_entity_ids),
            anomaly_score=max(
                (score_by_entity.get(member, 0.0) for member in community.member_entity_ids),
                default=0.0,
            ),
        )
        for community in gnn_response.communities
    ]
    try:
        cluster_store.put_clusters(knowledge_base_id, summaries)
    except Exception as exc:  # noqa: BLE001 - persistence must not fail the pipeline
        logger.warning(
            "Failed to persist GNN cluster summaries kb=%s: %s", knowledge_base_id, exc
        )
```

Call it in Flow B immediately after a non-`None` `gnn_response` (empty `communities` still writes — an honest empty list replaces stale clusters).

- [ ] **Step 4: Run + gates** — `pytest tests/agent -q`, pyright, ruff → green.

- [ ] **Step 5: Commit**

```bash
git add backend/agent backend/tests/agent
git commit -m "feat(agent): persist GNN community summaries after the pipeline stage (B1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Cluster store joins the KB-delete cascade

**Files:**
- Modify: `backend/knowledgebases/cleanup.py` (field + step), `backend/api/_kb_cleanup.py` (DI wiring), `backend/agent/coordinator.py` (`build_kb_deletion_stores` — worker CAN wire this one: the store is analytics-owned, not API-owned)
- Test: `backend/tests/api/test_kb_cleanup.py` (step list), `backend/tests/agent/test_handle_knowledge_base_deleted.py` + `backend/tests/agent/test_coordinator.py` (worker bundle fixtures)

**Interfaces:**
- Consumes: `ClusterSummaryStoreProtocol.delete_by_kb` (Task 1).
- Produces: `KbDeletionStores.gnn_cluster_store: GnnClusterPurger` (narrow structural protocol in `cleanup.py`, same pattern as `AlertProjectionPurger`: `def delete_by_kb(self, knowledge_base_id: str) -> None: ...`) — REQUIRED field (both API and worker bundles carry it, unlike the API-only alert projection); step name `"gnn_clusters"` placed after `"alert_projection"` in the ordered list.

- [ ] **Step 1: Failing tests.** Extend `_STORE_FIELDS`/`_EXPECTED_STEP_NAMES` in `tests/api/test_kb_cleanup.py` with `gnn_cluster_store`/`"gnn_clusters"` and assert `delete_by_kb("kb-1")` called; update the worker-side mock-bundle builders (they construct `SimpleNamespace(**mocks, alert_projection_store=None)` — the new field is a plain MagicMock in `_STORE_FIELDS`).

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement.** `cleanup.py`: `GnnClusterPurger` protocol + required field + unconditional step `("gnn_clusters", lambda: stores.gnn_cluster_store.delete_by_kb(kb))` in the literal list. `api/_kb_cleanup.py`: build `ObjectStoreClusterSummaryStore(object_store)` from the already-injected object store (no new DI dependency). `coordinator.build_kb_deletion_stores`: same construction from its `object_store` argument.

- [ ] **Step 4: Run + gates** — `pytest tests/api/test_kb_cleanup.py tests/agent tests/api/test_knowledgebases_router.py -q -m "not integration"`, pyright, ruff → green.

- [ ] **Step 5: Commit**

```bash
git add backend/knowledgebases backend/api backend/agent backend/tests
git commit -m "feat(knowledgebases): GNN cluster summaries join the KB-delete cascade (B1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Integration test, docs, and controller live pass

**Files:**
- Test: `backend/tests/analytics/gnn/test_gnn_live_integration.py` (new, `@pytest.mark.integration`)
- Modify: `backend/analytics/README.md` (or module README covering gnn — find and update the snapshot-source description), `backend/README.md` (GNN stage description), `docs/architecture.md` (analytics flow section), `docs/backlog/analytics.md` (mark analytics.03/.05 and the delivered slice of .04/.24 with resolution notes)

**Interfaces:** none new.

- [ ] **Step 1: Integration test** (runs against live Neo4j via the standard integration env):

```python
@pytest.mark.integration
def test_gnn_snapshot_source_round_trips_live_neo4j() -> None:
    """Seed a small KB through the live Neo4j repository, load a snapshot,
    run GnnService.analyze, and assert scored nodes + >=1 community."""
```

Full body: build the live `Neo4jGraphRepository` exactly as `tests/graph/test_neo4j_adapter.py`'s live fixture does (reuse/import its fixture pattern — read that file first), seed 4 entities + 4 relationships forming two connected pairs, build `GraphRepositorySnapshotSource(repository, InMemoryClusterSummaryStore())`, construct `GnnService(source, event_bus=InMemoryEventBus())`, call `analyze(GnnAnalysisRequest(knowledge_base_id=kb))`, assert `node_count == 4`, `len(response.communities) >= 1`, every scored node has `0.0 <= score <= 1.0`; delete the KB in a finally block.

- [ ] **Step 2: Run non-integration gates + full suite**

Run: `make test` (host venv vs chili_test — includes the integration subset with the stack up) and `.venv/bin/pyright` and `.venv/bin/ruff check --no-cache .`
Expected: all green, coverage ≥ 85%.

- [ ] **Step 3: Update docs** — READMEs + architecture.md describe the repository-backed snapshot source, the cluster store (incl. cascade membership), and that the GNN pipeline stage is now live; backlog notes per Files list. Before committing, per CLAUDE.md, re-check instruction files for contradictions.

- [ ] **Step 4: Commit**

```bash
git add backend docs chili_app
git commit -m "test(analytics): live Neo4j GNN round-trip; docs for the live GNN path (B1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Live verification — RESERVED FOR THE CONTROLLER.** Against `make dev` (api+worker restarted onto the branch), medicare_fraud_cms_desynpuf pack: run `make demo-tn-subset` (1% sample); after ingest completes verify (1) worker logs show the GNN stage running (no "no graph snapshot" skip); (2) `GET /analytics/gnn/clusters?knowledge_base_id=<kb>` returns non-empty communities; (3) Dashboard → Policy Signals tab shows real clusters; (4) a graph entity carries `community_id`/`centrality_score` properties (cypher-shell); (5) `DELETE` a scratch KB removes its cluster key from the object store.

---

## Self-review notes (already applied)

- Spec coverage: §3.1 B1 fully covered — snapshot source (T2), caps+logging (T2), factories both sites (T3), cluster persistence + real `/analytics/gnn/clusters` (T1+T4), write-back already existing (verified, no task needed), non-fatal stage semantics untouched (T4 catch), cascade hygiene (T5), live verification (T6). B2/B3/U1/U2/D1/S1 are separate plans per the two-track ruling.
- Type consistency: `ClusterSummaryStoreProtocol` names match across T1 (definition), T2 (constructor), T3 (factories), T4 (persist), T5 (purge protocol mirrors `delete_by_kb`).
- The `GnnService` constructor takes the source positionally (verified `create_gnn_service(build_graph_snapshot_source(...), ...)` at coordinator.py:1003) — factory signature change in T3 touches exactly one call site per process.
