"""Tests for the graph service."""

from __future__ import annotations

from contextlib import contextmanager
from typing import cast
import pytest

from events.adapters.in_memory import InMemoryEventBus
from events.types import GraphUpdatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository
from graph.exceptions import BatchUpsertError
from graph.models import GraphMetrics, SubgraphResult
from graph.service import GraphService, create_graph_service
from graph.service_models import GraphBuildTask
from shared.types import Entity, Relationship
from storage.adapters.in_memory import InMemoryObjectStore


def _repository_for(service: GraphService) -> GraphRepository:
    return cast(GraphRepository, getattr(service, "_repository"))


def test_graph_service_upserts_and_publishes_update() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )

    receipt = service.upsert_task(
        GraphBuildTask(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
            correlation_id="corr-graph-456",
            entities=[
                Entity(id="entity-1", type="claim", properties={"claim_id": "42"}),
                Entity(id="entity-2", type="provider", properties={"npi": "1234567890"}),
            ],
            relationships=[
                Relationship(
                    id="relationship-1",
                    type="submitted_by",
                    source_id="entity-1",
                    target_id="entity-2",
                )
            ],
        )
    )

    assert receipt.graph_update_storage_key == "knowledgebases/kb-1/graph_updates/extract-1.json"
    assert receipt.upserted_entity_count == 2
    assert receipt.upserted_relationship_count == 1
    assert isinstance(event_bus.published_events[-1], GraphUpdatedEvent)
    assert event_bus.published_events[-1].correlation_id == "corr-graph-456"

    stored = object_store.get_bytes(receipt.graph_update_storage_key)
    assert b'"validation_report_id":"validate-1"' in stored.content


def test_graph_service_upsert_task_uses_repository_transaction() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = InMemoryGraphRepository()
    service = create_graph_service(
        repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    entered: list[str] = []

    @contextmanager
    def fake_transaction(knowledge_base_id: str):
        entered.append(knowledge_base_id)
        yield

    repository.transaction = fake_transaction  # type: ignore[method-assign]

    service.upsert_task(
        GraphBuildTask(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
            entities=[Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
        )
    )

    assert entered == ["kb-1"]


def test_graph_service_upsert_task_chunks_large_entity_batches() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = InMemoryGraphRepository()
    service = create_graph_service(
        repository,
        object_store=object_store,
        event_bus=event_bus,
        batch_size=500,
    )
    entity_batch_sizes: list[int] = []

    original_upsert_entities = repository.upsert_entities

    def recording_upsert_entities(
        knowledge_base_id: str,
        entities: list[Entity],
    ) -> list[Entity]:
        entity_batch_sizes.append(len(entities))
        return original_upsert_entities(knowledge_base_id, entities)

    repository.upsert_entities = recording_upsert_entities  # type: ignore[method-assign]

    receipt = service.upsert_task(
        GraphBuildTask(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
            entities=[
                Entity(id=f"entity-{index}", type="claim", properties={"claim_id": str(index)})
                for index in range(1500)
            ],
        )
    )

    repository.upsert_entities = original_upsert_entities  # type: ignore[method-assign]

    assert entity_batch_sizes == [500, 500, 500]
    assert receipt.upserted_entity_count == 1500
    assert repository.count_entities("kb-1") == 1500


def test_graph_service_upsert_task_chunks_large_relationship_batches() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = InMemoryGraphRepository()
    service = create_graph_service(
        repository,
        object_store=object_store,
        event_bus=event_bus,
        batch_size=500,
    )
    relationship_batch_sizes: list[int] = []

    original_upsert_relationships = repository.upsert_relationships

    def recording_upsert_relationships(
        knowledge_base_id: str,
        relationships: list[Relationship],
    ) -> list[Relationship]:
        relationship_batch_sizes.append(len(relationships))
        return original_upsert_relationships(knowledge_base_id, relationships)

    repository.upsert_relationships = recording_upsert_relationships  # type: ignore[method-assign]

    receipt = service.upsert_task(
        GraphBuildTask(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
            entities=[
                Entity(id=f"entity-{index}", type="claim", properties={"claim_id": str(index)})
                for index in range(1501)
            ],
            relationships=[
                Relationship(
                    id=f"relationship-{index}",
                    type="related_to",
                    source_id=f"entity-{index}",
                    target_id=f"entity-{index + 1}",
                )
                for index in range(1500)
            ],
        )
    )

    repository.upsert_relationships = original_upsert_relationships  # type: ignore[method-assign]

    assert relationship_batch_sizes == [500, 500, 500]
    assert receipt.upserted_relationship_count == 1500
    assert repository.count_relationships("kb-1") == 1500


def test_create_graph_service_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        create_graph_service(
            InMemoryGraphRepository(),
            object_store=InMemoryObjectStore(),
            event_bus=InMemoryEventBus(),
            batch_size=0,
        )


def test_graph_service_upsert_task_raises_batch_error_and_keeps_prior_batches() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = InMemoryGraphRepository()
    service = create_graph_service(
        repository,
        object_store=object_store,
        event_bus=event_bus,
        batch_size=2,
    )

    original_upsert_relationships = repository.upsert_relationships
    relationship_batch_calls = 0

    def failing_upsert_relationships(
        knowledge_base_id: str,
        relationships: list[Relationship],
    ) -> list[Relationship]:
        nonlocal relationship_batch_calls
        relationship_batch_calls += 1
        if relationship_batch_calls == 2:
            raise RuntimeError("relationship upsert failed")
        return original_upsert_relationships(knowledge_base_id, relationships)

    repository.upsert_relationships = failing_upsert_relationships  # type: ignore[method-assign]

    with pytest.raises(BatchUpsertError) as exc_info:
        service.upsert_task(
            GraphBuildTask(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="validate-1",
                validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
                entities=[
                    Entity(id=f"entity-{index}", type="claim", properties={"claim_id": str(index)})
                    for index in range(3)
                ],
                relationships=[
                    Relationship(
                        id="relationship-1",
                        type="submitted_by",
                        source_id="entity-0",
                        target_id="entity-1",
                    ),
                    Relationship(
                        id="relationship-2",
                        type="submitted_by",
                        source_id="entity-1",
                        target_id="entity-2",
                    ),
                    Relationship(
                        id="relationship-3",
                        type="submitted_by",
                        source_id="entity-2",
                        target_id="entity-0",
                    ),
                    Relationship(
                        id="relationship-4",
                        type="submitted_by",
                        source_id="entity-0",
                        target_id="entity-2",
                    ),
                ],
            )
        )

    repository.upsert_relationships = original_upsert_relationships  # type: ignore[method-assign]

    assert exc_info.value.successful_entity_count == 3
    assert exc_info.value.successful_relationship_count == 2
    assert repository.count_entities("kb-1") == 3
    assert repository.count_relationships("kb-1") == 2
    assert event_bus.published_events == []
    with pytest.raises(KeyError):
        object_store.get_bytes("knowledgebases/kb-1/graph_updates/extract-1.json")


def test_graph_service_upsert_task_suppresses_artifact_and_event_on_entity_failure() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = InMemoryGraphRepository()
    service = create_graph_service(
        repository,
        object_store=object_store,
        event_bus=event_bus,
        batch_size=2,
    )

    def failing_upsert_entities(
        knowledge_base_id: str,
        entities: list[Entity],
    ) -> list[Entity]:
        raise RuntimeError("entity upsert failed")

    repository.upsert_entities = failing_upsert_entities  # type: ignore[method-assign]

    with pytest.raises(BatchUpsertError) as exc_info:
        service.upsert_task(
            GraphBuildTask(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="validate-1",
                validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
                entities=[Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
            )
        )

    assert exc_info.value.successful_entity_count == 0
    assert exc_info.value.successful_relationship_count == 0
    assert event_bus.published_events == []
    with pytest.raises(KeyError):
        object_store.get_bytes("knowledgebases/kb-1/graph_updates/extract-1.json")


@pytest.fixture()
def graph_service() -> GraphService:
    return create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )


def test_graph_service_get_entity_delegates(
    graph_service: GraphService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository_for(graph_service)
    expected_entity = Entity(id="entity-1", type="claim", properties={"claim_id": "42"})

    def fake_get_entity(knowledge_base_id: str, entity_id: str) -> Entity | None:
        assert knowledge_base_id == "kb-1"
        assert entity_id == "entity-1"
        return expected_entity

    monkeypatch.setattr(repository, "get_entity", fake_get_entity)

    assert graph_service.get_entity("kb-1", "entity-1") == expected_entity


def test_graph_service_query_neighborhood_delegates_with_default_direction(
    graph_service: GraphService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository_for(graph_service)
    expected_result = SubgraphResult(
        entities=[Entity(id="entity-1", type="claim", properties={})],
        relationships=[],
    )

    def fake_get_neighbors(
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
        direction: str,
    ) -> SubgraphResult:
        assert knowledge_base_id == "kb-1"
        assert entity_id == "entity-1"
        assert depth == 2
        assert direction == "both"
        return expected_result

    monkeypatch.setattr(repository, "get_neighbors", fake_get_neighbors)

    assert graph_service.query_neighborhood("kb-1", "entity-1", 2) == expected_result


def test_graph_service_query_neighborhood_rejects_excessive_depth(
    graph_service: GraphService,
) -> None:
    with pytest.raises(ValueError):
        graph_service.query_neighborhood("kb-1", "entity-1", 6)


def test_graph_service_search_entities_delegates_and_applies_offset(
    graph_service: GraphService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository_for(graph_service)
    repository_entities = [
        Entity(id="entity-1", type="claim", properties={"description": "alpha"}),
        Entity(id="entity-2", type="claim", properties={"description": "beta"}),
        Entity(id="entity-3", type="claim", properties={"description": "gamma"}),
    ]

    def fake_search_entities(
        knowledge_base_id: str,
        query: str,
        limit: int,
    ) -> list[Entity]:
        assert knowledge_base_id == "kb-1"
        assert query == "claim"
        assert limit == 4
        return repository_entities

    monkeypatch.setattr(repository, "search_entities", fake_search_entities)

    assert graph_service.search_entities("kb-1", "claim", limit=2, offset=2) == [
        repository_entities[2]
    ]


def test_graph_service_search_entities_rejects_excessive_limit(
    graph_service: GraphService,
) -> None:
    with pytest.raises(ValueError):
        graph_service.search_entities("kb-1", "claim", limit=501, offset=0)


def test_graph_service_compute_metrics_uses_repository_counts(
    graph_service: GraphService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository_for(graph_service)
    def fake_count_entities(knowledge_base_id: str) -> int:
        assert knowledge_base_id == "kb-1"
        return 4

    def fake_count_relationships(knowledge_base_id: str) -> int:
        assert knowledge_base_id == "kb-1"
        return 6

    monkeypatch.setattr(repository, "count_entities", fake_count_entities)
    monkeypatch.setattr(
        repository,
        "count_relationships",
        fake_count_relationships,
    )

    assert graph_service.compute_metrics("kb-1") == GraphMetrics(
        entity_count=4,
        relationship_count=6,
        avg_degree=3.0,
    )


def test_graph_service_compute_metrics_handles_empty_graph(
    graph_service: GraphService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository_for(graph_service)

    def fake_count_entities(_: str) -> int:
        return 0

    def fake_count_relationships(_: str) -> int:
        return 3

    monkeypatch.setattr(repository, "count_entities", fake_count_entities)
    monkeypatch.setattr(repository, "count_relationships", fake_count_relationships)

    assert graph_service.compute_metrics("kb-1") == GraphMetrics(
        entity_count=0,
        relationship_count=3,
        avg_degree=0.0,
    )