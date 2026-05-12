"""Integration tests for the Neo4j graph adapter."""

from __future__ import annotations

import os
from collections.abc import Callable, Generator
from uuid import uuid4

import pytest

from config.schema import GraphDbConfig
from graph.adapters import neo4j_adapter
from graph.adapters.neo4j_adapter import Neo4jGraphRepository
from graph.exceptions import GraphPersistenceError
from shared.types import Entity, Relationship

FakeRecord = dict[str, object]


class _FakeGraphDatabase:
    captured: list[tuple[str, tuple[str, str] | None, int]] = []
    driver_instance: _FakeDriver | None = None

    @classmethod
    def driver(
        cls,
        uri: str,
        *,
        auth: tuple[str, str] | None,
        max_connection_pool_size: int,
    ) -> _FakeDriver:
        cls.captured.append((uri, auth, max_connection_pool_size))
        cls.driver_instance = _FakeDriver()
        return cls.driver_instance


class _FakeDriver:
    def __init__(self) -> None:
        self.results: list[list[FakeRecord]] = []
        self.queries: list[tuple[str, dict[str, object], str]] = []
        self.session_kwargs: list[dict[str, object]] = []
        self.closed = False
        self.begin_transaction_calls = 0
        self.last_transaction: _FakeManagedTransaction | None = None

    def session(self, **kwargs: object) -> _FakeSession:
        self.session_kwargs.append(kwargs)
        return _FakeSession(self)

    def close(self) -> None:
        self.closed = True


class _FakeSession:
    def __init__(self, driver: _FakeDriver) -> None:
        self._driver = driver

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def execute_read(
        self,
        callback: Callable[..., list[FakeRecord]],
        query: str,
        **parameters: object,
    ) -> list[FakeRecord]:
        self._driver.queries.append((query, parameters, "read"))
        return callback(_FakeTransaction(self._driver), query, **parameters)

    def execute_write(
        self,
        callback: Callable[..., list[FakeRecord]],
        query: str,
        **parameters: object,
    ) -> list[FakeRecord]:
        self._driver.queries.append((query, parameters, "write"))
        return callback(_FakeTransaction(self._driver), query, **parameters)

    def begin_transaction(self) -> _FakeManagedTransaction:
        self._driver.begin_transaction_calls += 1
        self._driver.last_transaction = _FakeManagedTransaction(self._driver)
        return self._driver.last_transaction


class _FakeTransaction:
    def __init__(self, driver: _FakeDriver) -> None:
        self._driver = driver

    def run(self, query: str, **parameters: object) -> list[FakeRecord]:
        return self._driver.results.pop(0)


class _FakeManagedTransaction(_FakeTransaction):
    def __init__(self, driver: _FakeDriver) -> None:
        super().__init__(driver)
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class _FakePath:
    def __init__(self, nodes: list[FakeRecord], relationships: list[FakeRecord]) -> None:
        self.nodes = nodes
        self.relationships = relationships


def test_neo4j_repository_constructor_uses_configured_pool_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeGraphDatabase.captured = []
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)

    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=23),
        auth=("neo4j", "password"),
        database="neo4j",
    )

    assert _FakeGraphDatabase.captured == [
        ("bolt://localhost:7687", ("neo4j", "password"), 23)
    ]
    repository.close()
    assert _FakeGraphDatabase.driver_instance is not None
    assert _FakeGraphDatabase.driver_instance.closed is True


def test_neo4j_repository_upserts_entities_and_relationships_with_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    driver.results = [
        [
            {
                "entity": {
                    "entity_id": "entity-1",
                    "type": "claim",
                    "properties": {"description": "Cardiac investigation"},
                    "metadata": {},
                    "created_at": "2026-04-20T00:00:00+00:00",
                    "updated_at": None,
                    "version": 1,
                }
            }
        ],
        [
            {
                "relationship": {
                    "relationship_id": "relationship-1",
                    "type": "submitted_by",
                    "properties": {},
                    "created_at": "2026-04-20T00:00:00+00:00",
                    "updated_at": None,
                    "version": 1,
                    "weight": None,
                },
                "source_id": "entity-1",
                "target_id": "entity-2",
            }
        ],
    ]

    entities = repository.upsert_entities(
        "kb-1",
        [Entity(id="entity-1", type="claim", properties={"description": "Cardiac investigation"})],
    )
    relationships = repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="relationship-1",
                type="submitted_by",
                source_id="entity-1",
                target_id="entity-2",
            )
        ],
    )

    assert entities[0].id == "entity-1"
    assert relationships[0].id == "relationship-1"
    assert "MERGE (entity:Entity" in driver.queries[0][0]
    assert "MERGE (source)-[relationship:RELATES" in driver.queries[1][0]


def test_neo4j_repository_reads_searches_counts_and_deletes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    driver.results = [
        [{"entity": {"entity_id": "entity-1", "type": "claim", "properties": {}, "metadata": {}, "created_at": "2026-04-20T00:00:00+00:00", "updated_at": None, "version": 1}}],
        [{"entity": {"entity_id": "entity-2", "type": "provider", "properties": {"name": "Alice Clinic"}, "metadata": {}, "created_at": "2026-04-20T00:00:00+00:00", "updated_at": None, "version": 1}}],
        [{"count": 3}],
        [{"count": 2}],
        [],
        [],
        [],
    ]

    assert repository.get_entity("kb-1", "entity-1") is not None
    assert repository.search_entities("kb-1", "alice", limit=10)[0].id == "entity-2"
    assert repository.count_entities("kb-1") == 3
    assert repository.count_relationships("kb-1") == 2
    repository.delete_knowledge_base("kb-1")
    repository.delete_entity("kb-1", "entity-2")
    repository.delete_relationship("kb-1", "relationship-2")

    assert "entity.properties_json" in driver.queries[1][0]
    assert "DETACH DELETE entity" in driver.queries[-3][0]
    assert "DELETE relationship" in driver.queries[-1][0]


def test_neo4j_repository_get_neighbors_uses_variable_length_path_pattern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    root_node: FakeRecord = {
        "entity_id": "entity-1",
        "type": "claim",
        "properties": {},
        "metadata": {},
        "created_at": "2026-04-20T00:00:00+00:00",
        "updated_at": None,
        "version": 1,
    }
    neighbor_node: FakeRecord = {
        "entity_id": "entity-2",
        "type": "provider",
        "properties": {},
        "metadata": {},
        "created_at": "2026-04-20T00:00:00+00:00",
        "updated_at": None,
        "version": 1,
    }
    relationship: FakeRecord = {
        "relationship_id": "relationship-1",
        "type": "submitted_by",
        "properties": {},
        "created_at": "2026-04-20T00:00:00+00:00",
        "updated_at": None,
        "version": 1,
        "weight": None,
    }
    driver.results = [
        [{"entity": root_node}],
        [
            {
                "root": root_node,
                "path": _FakePath([root_node, neighbor_node], [relationship]),
                "relationship_source_ids": ["entity-1"],
                "relationship_target_ids": ["entity-2"],
            }
        ],
        [{"entity": root_node}],
    ]

    result = repository.get_neighbors("kb-1", "entity-1", depth=2, direction="out")
    zero_depth_result = repository.get_neighbors("kb-1", "entity-1", depth=0, direction="both")

    assert {entity.id for entity in result.entities} == {"entity-1", "entity-2"}
    assert [relationship.id for relationship in result.relationships] == ["relationship-1"]
    assert [entity.id for entity in zero_depth_result.entities] == ["entity-1"]
    assert "*1..2" in driver.queries[1][0]


def test_neo4j_repository_get_neighbors_preserves_inbound_relationship_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    root_node: FakeRecord = {
        "entity_id": "entity-1",
        "type": "claim",
        "properties": {},
        "metadata": {},
        "created_at": "2026-04-20T00:00:00+00:00",
        "updated_at": None,
        "version": 1,
    }
    neighbor_node: FakeRecord = {
        "entity_id": "entity-2",
        "type": "provider",
        "properties": {},
        "metadata": {},
        "created_at": "2026-04-20T00:00:00+00:00",
        "updated_at": None,
        "version": 1,
    }
    relationship: FakeRecord = {
        "relationship_id": "relationship-1",
        "type": "submitted_by",
        "properties": {},
        "created_at": "2026-04-20T00:00:00+00:00",
        "updated_at": None,
        "version": 1,
        "weight": None,
    }
    driver.results = [
        [{"entity": root_node}],
        [
            {
                "root": root_node,
                "path": _FakePath([root_node, neighbor_node], [relationship]),
                "relationship_source_ids": ["entity-2"],
                "relationship_target_ids": ["entity-1"],
            }
        ],
    ]

    result = repository.get_neighbors("kb-1", "entity-1", depth=1, direction="in")

    assert len(result.relationships) == 1
    assert result.relationships[0].source_id == "entity-2"
    assert result.relationships[0].target_id == "entity-1"


def test_neo4j_repository_get_neighbors_rejects_invalid_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )

    with pytest.raises(ValueError, match="direction must be one of"):
        repository.get_neighbors(
            "kb-1",
            "entity-1",
            depth=1,
            direction="sideways",  # type: ignore[arg-type]
        )


def test_neo4j_repository_transaction_commits_and_reuses_driver_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None
    driver.results = [
        [
            {
                "entity": {
                    "entity_id": "entity-1",
                    "type": "claim",
                    "properties": {},
                    "metadata": {},
                    "created_at": "2026-04-20T00:00:00+00:00",
                    "updated_at": None,
                    "version": 1,
                }
            }
        ]
    ]

    with repository.transaction("kb-1"):
        repository.upsert_entities(
            "kb-1",
            [Entity(id="entity-1", type="claim", properties={})],
        )

    assert driver.begin_transaction_calls == 1
    assert driver.last_transaction is not None
    assert driver.last_transaction.committed is True
    assert driver.last_transaction.rolled_back is False


def test_neo4j_repository_transaction_rolls_back_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(neo4j_adapter, "GraphDatabase", _FakeGraphDatabase)
    repository = Neo4jGraphRepository(
        GraphDbConfig(backend="neo4j", uri="bolt://localhost:7687", pool_size=5),
        auth=("neo4j", "password"),
    )
    driver = _FakeGraphDatabase.driver_instance
    assert driver is not None

    with pytest.raises(RuntimeError, match="boom"):
        with repository.transaction("kb-1"):
            raise RuntimeError("boom")

    assert driver.last_transaction is not None
    assert driver.last_transaction.rolled_back is True
    assert driver.last_transaction.committed is False


@pytest.fixture()
def neo4j_repository() -> Generator[tuple[Neo4jGraphRepository, str], None, None]:
    pytest.importorskip("neo4j")
    if neo4j_adapter.GraphDatabase is None:
        pytest.skip("neo4j dependency is not installed.")


    uri = os.getenv("NEO4J_TEST_URI")
    password = os.getenv("NEO4J_TEST_PASSWORD")
    if uri is None or password is None:
        pytest.skip("NEO4J_TEST_URI and NEO4J_TEST_PASSWORD are required for Neo4j integration tests.")

    username = os.getenv("NEO4J_TEST_USERNAME", "neo4j")
    database = os.getenv("NEO4J_TEST_DATABASE")
    knowledge_base_id = f"kb-neo4j-{uuid4()}"
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

    yield repository, knowledge_base_id

    repository.delete_knowledge_base(knowledge_base_id)
    repository.close()


@pytest.mark.integration
def test_neo4j_repository_round_trip_crud(
    neo4j_repository: tuple[Neo4jGraphRepository, str],
) -> None:
    repository, knowledge_base_id = neo4j_repository

    stored_entities = repository.upsert_entities(
        knowledge_base_id,
        [
            Entity(
                id="entity-1",
                type="claim",
                properties={"description": "Cardiac investigation"},
            ),
            Entity(
                id="entity-2",
                type="provider",
                properties={"name": "Alice Clinic"},
            ),
            Entity(
                id="entity-3",
                type="provider",
                properties={"name": "Bob Partners"},
            ),
        ],
    )
    stored_relationships = repository.upsert_relationships(
        knowledge_base_id,
        [
            Relationship(
                id="relationship-1",
                type="submitted_by",
                source_id="entity-1",
                target_id="entity-2",
            ),
            Relationship(
                id="relationship-2",
                type="referred_to",
                source_id="entity-2",
                target_id="entity-3",
            ),
        ],
    )

    assert [entity.id for entity in stored_entities] == ["entity-1", "entity-2", "entity-3"]
    assert [relationship.id for relationship in stored_relationships] == [
        "relationship-1",
        "relationship-2",
    ]
    assert repository.get_entity(knowledge_base_id, "entity-2") is not None
    assert repository.count_entities(knowledge_base_id) == 3
    assert repository.count_relationships(knowledge_base_id) == 2
    assert [
        entity.id
        for entity in repository.get_entities_by_type(
            knowledge_base_id,
            "provider",
            limit=10,
            offset=0,
        )
    ] == ["entity-2", "entity-3"]
    assert [entity.id for entity in repository.search_entities(knowledge_base_id, "alice", limit=10)] == [
        "entity-2"
    ]

    neighbors = repository.get_neighbors(knowledge_base_id, "entity-1", depth=2, direction="out")
    assert {entity.id for entity in neighbors.entities} == {"entity-1", "entity-2", "entity-3"}
    assert {relationship.id for relationship in neighbors.relationships} == {
        "relationship-1",
        "relationship-2",
    }

    repository.delete_relationship(knowledge_base_id, "relationship-2")
    assert repository.count_relationships(knowledge_base_id) == 1

    repository.upsert_relationships(
        knowledge_base_id,
        [
            Relationship(
                id="relationship-2",
                type="referred_to",
                source_id="entity-2",
                target_id="entity-3",
            )
        ],
    )
    repository.delete_entity(knowledge_base_id, "entity-2")

    assert repository.get_entity(knowledge_base_id, "entity-2") is None
    assert repository.count_entities(knowledge_base_id) == 2
    assert repository.count_relationships(knowledge_base_id) == 0

    repository.delete_knowledge_base(knowledge_base_id)
    assert repository.count_entities(knowledge_base_id) == 0
    assert repository.count_relationships(knowledge_base_id) == 0


@pytest.mark.integration
def test_neo4j_repository_transaction_rolls_back_changes(
    neo4j_repository: tuple[Neo4jGraphRepository, str],
) -> None:
    repository, knowledge_base_id = neo4j_repository

    with pytest.raises(RuntimeError, match="rollback"):
        with repository.transaction(knowledge_base_id):
            repository.upsert_entities(
                knowledge_base_id,
                [Entity(id="rollback-entity", type="claim", properties={"description": "rollback"})],
            )
            raise RuntimeError("rollback")

    assert repository.get_entity(knowledge_base_id, "rollback-entity") is None