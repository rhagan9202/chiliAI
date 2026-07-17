"""Live-Neo4j integration test for the GNN snapshot-source round trip.

Builds the live ``Neo4jGraphRepository`` exactly as
``tests/graph/test_neo4j_adapter.py``'s ``neo4j_repository`` fixture does
(same env-driven connection + skip conditions), seeds a small knowledge base,
and drives it end-to-end through ``GraphRepositorySnapshotSource`` and
``GnnService.analyze`` to prove the live GNN path (B1) actually produces
scored nodes and communities from real graph data — not just in-memory
fixtures.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from uuid import uuid4

import pytest

from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource
from analytics.gnn.service import GnnService
from analytics.gnn.service_models import GnnAnalysisRequest
from config.schema import GraphDbConfig
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.neo4j_adapter import Neo4jGraphRepository
from graph.exceptions import GraphPersistenceError
from shared.types import Entity, Relationship


@pytest.fixture()
def neo4j_repository() -> Generator[tuple[Neo4jGraphRepository, str], None, None]:
    """Live Neo4j repository fixture, mirrored from ``tests/graph/test_neo4j_adapter.py``."""

    pytest.importorskip("neo4j")
    from graph.adapters import neo4j_adapter

    if neo4j_adapter.GraphDatabase is None:
        pytest.skip("neo4j dependency is not installed.")

    uri = os.getenv("NEO4J_TEST_URI")
    password = os.getenv("NEO4J_TEST_PASSWORD")
    if uri is None or password is None:
        pytest.skip("NEO4J_TEST_URI and NEO4J_TEST_PASSWORD are required for Neo4j integration tests.")

    username = os.getenv("NEO4J_TEST_USERNAME", "neo4j")
    database = os.getenv("NEO4J_TEST_DATABASE")
    knowledge_base_id = f"kb-gnn-live-{uuid4()}"
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri=uri, pool_size=5),
        auth=(username, password),
        database=database,
    )

    try:
        repository.count_entities(knowledge_base_id)
    except GraphPersistenceError as exc:
        repository.close()
        pytest.skip(f"Neo4j integration database is unavailable: {exc}")

    try:
        yield repository, knowledge_base_id
    finally:
        repository.delete_knowledge_base(knowledge_base_id)
        repository.close()


@pytest.mark.integration
def test_gnn_snapshot_source_round_trips_live_neo4j(
    neo4j_repository: tuple[Neo4jGraphRepository, str],
) -> None:
    """Seed a small KB through the live Neo4j repository, load a snapshot,
    run GnnService.analyze, and assert scored nodes + >=1 community.
    """

    repository, knowledge_base_id = neo4j_repository

    repository.upsert_entities(
        knowledge_base_id,
        [
            Entity(id="e-1", type="provider", properties={"amount": 100}),
            Entity(id="e-2", type="claim", properties={"amount": 25.5}),
            Entity(id="e-3", type="provider", properties={"amount": 40}),
            Entity(id="e-4", type="claim", properties={"amount": 10}),
        ],
    )
    repository.upsert_relationships(
        knowledge_base_id,
        [
            Relationship(id="r-1", type="billed", source_id="e-2", target_id="e-1", weight=2.0),
            Relationship(id="r-2", type="submitted_by", source_id="e-1", target_id="e-2"),
            Relationship(id="r-3", type="billed", source_id="e-4", target_id="e-3", weight=1.5),
            Relationship(id="r-4", type="submitted_by", source_id="e-3", target_id="e-4"),
        ],
    )

    source = GraphRepositorySnapshotSource(repository, InMemoryClusterSummaryStore())
    service = GnnService(source, event_bus=InMemoryEventBus())

    response = service.analyze(GnnAnalysisRequest(knowledge_base_id=knowledge_base_id))

    assert response.node_count == 4
    assert len(response.communities) >= 1
    assert response.scored_nodes
    for scored_node in response.scored_nodes:
        assert 0.0 <= scored_node.score <= 1.0
