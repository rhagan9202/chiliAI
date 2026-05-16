"""Service entry point for graph update flows."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TypeVar

from events.protocols import EventBus
from events.types import GraphUpdatedDocumentReference, GraphUpdatedEvent
from graph.adapters.protocols import GraphRepository
from graph.exceptions import BatchUpsertError, GraphPersistenceError
from graph.models import GraphMetrics, GraphUpsertResult, SubgraphResult
from graph.service_models import (
    EntitySearchQuery,
    GraphBuildReceipt,
    GraphBuildTask,
    GraphMetricsResult,
    NeighborhoodQuery,
)
from shared.protocols import ObjectStoreProtocol
from shared.types import Entity, Relationship

ItemT = TypeVar("ItemT")


class GraphService:
    """Persist validated runtime objects and publish graph update events."""

    # TODO(production): Add get_subgraph once repository adapters expose a filtered
    # subgraph query surface. Add idempotency (change detection / version
    # tracking on upsert to avoid redundant writes).

    def __init__(
        self,
        repository: GraphRepository,
        *,
        object_store: ObjectStoreProtocol,
        event_bus: EventBus,
        batch_size: int = 500,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("GraphService batch_size must be greater than 0.")

        self._repository = repository
        self._object_store = object_store
        self._event_bus = event_bus
        self._batch_size = batch_size

    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt:
        try:
            stored_entities = self._upsert_entities(task)
            stored_relationships = self._upsert_relationships(
                task,
                successful_entity_count=len(stored_entities),
            )
        except BatchUpsertError:
            raise
        except Exception as exc:
            raise GraphPersistenceError("Failed to upsert graph entities or relationships.") from exc

        result = GraphUpsertResult(
            knowledge_base_id=task.knowledge_base_id,
            source_document_id=task.source_document_id,
            parsed_document_id=task.parsed_document_id,
            validation_report_id=task.validation_report_id,
            extraction_result_id=task.extraction_result_id,
            upserted_entity_ids=[entity.id for entity in stored_entities],
            upserted_relationship_ids=[relationship.id for relationship in stored_relationships],
        )
        graph_update_storage_key = self._build_graph_update_storage_key(
            task.knowledge_base_id,
            task.extraction_result_id,
        )

        try:
            self._object_store.put_bytes(
                graph_update_storage_key,
                result.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": task.knowledge_base_id,
                    "source_document_id": task.source_document_id,
                    "parsed_document_id": task.parsed_document_id,
                    "validation_report_id": task.validation_report_id,
                    "upserted_entity_count": len(result.upserted_entity_ids),
                    "upserted_relationship_count": len(result.upserted_relationship_ids),
                },
            )
        except Exception as exc:
            raise GraphPersistenceError("Failed to persist graph update artifact.") from exc

        receipt = GraphBuildReceipt(
            knowledge_base_id=task.knowledge_base_id,
            source_document_id=task.source_document_id,
            parsed_document_id=task.parsed_document_id,
            extraction_result_id=task.extraction_result_id,
            validation_report_id=task.validation_report_id,
            validation_storage_key=task.validation_storage_key,
            graph_update_storage_key=graph_update_storage_key,
            upserted_entity_count=len(result.upserted_entity_ids),
            upserted_relationship_count=len(result.upserted_relationship_ids),
        )
        self._event_bus.publish(
            GraphUpdatedEvent(
                correlation_id=task.correlation_id,
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id=receipt.knowledge_base_id,
                        source_document_id=receipt.source_document_id,
                        parsed_document_id=receipt.parsed_document_id,
                        extraction_result_id=receipt.extraction_result_id,
                        validation_report_id=receipt.validation_report_id,
                        upserted_entity_count=receipt.upserted_entity_count,
                        upserted_relationship_count=receipt.upserted_relationship_count,
                        validation_storage_key=receipt.validation_storage_key,
                        graph_update_storage_key=receipt.graph_update_storage_key,
                    )
                ]
            )
        )
        return receipt

    def _upsert_entities(self, task: GraphBuildTask) -> list[Entity]:
        stored_entities: list[Entity] = []
        for entity_batch in self._chunk_items(task.entities):
            try:
                with self._repository.transaction(task.knowledge_base_id):
                    stored_entities.extend(
                        self._repository.upsert_entities(
                            task.knowledge_base_id,
                            entity_batch,
                        )
                    )
            except Exception as exc:
                raise BatchUpsertError(
                    successful_entity_count=len(stored_entities),
                    successful_relationship_count=0,
                ) from exc

        return stored_entities

    def _upsert_relationships(
        self,
        task: GraphBuildTask,
        *,
        successful_entity_count: int,
    ) -> list[Relationship]:
        stored_relationships: list[Relationship] = []
        for relationship_batch in self._chunk_items(task.relationships):
            try:
                with self._repository.transaction(task.knowledge_base_id):
                    stored_relationships.extend(
                        self._repository.upsert_relationships(
                            task.knowledge_base_id,
                            relationship_batch,
                        )
                    )
            except Exception as exc:
                raise BatchUpsertError(
                    successful_entity_count=successful_entity_count,
                    successful_relationship_count=len(stored_relationships),
                ) from exc

        return stored_relationships

    def _chunk_items(self, items: list[ItemT]) -> Iterator[list[ItemT]]:
        for start in range(0, len(items), self._batch_size):
            yield items[start : start + self._batch_size]

    def get_entity(self, knowledge_base_id: str, entity_id: str) -> Entity | None:
        return self._repository.get_entity(knowledge_base_id, entity_id)

    def update_entity_properties(
        self,
        knowledge_base_id: str,
        entity_id: str,
        properties: dict[str, object],
    ) -> Entity:
        """Idempotently merge properties onto an existing entity record."""

        return self._repository.update_entity_properties(
            knowledge_base_id, entity_id, properties
        )

    def upsert_records_graph(
        self,
        knowledge_base_id: str,
        entities: list[Entity],
        relationships: list[Relationship],
    ) -> tuple[list[Entity], list[Relationship]]:
        """Upsert entities and relationships from a structured-records feed.

        Unlike :meth:`upsert_task`, this writes no document-pipeline artifacts
        and publishes no ``GraphUpdatedEvent`` — structured records have no
        parsed-document lineage. Both writes are idempotent upserts, so the
        worker's Flow 1 handler is safely replayable.
        """

        stored_entities: list[Entity] = []
        for entity_batch in self._chunk_items(entities):
            try:
                with self._repository.transaction(knowledge_base_id):
                    stored_entities.extend(
                        self._repository.upsert_entities(knowledge_base_id, entity_batch)
                    )
            except Exception as exc:
                raise BatchUpsertError(
                    successful_entity_count=len(stored_entities),
                    successful_relationship_count=0,
                ) from exc

        stored_relationships: list[Relationship] = []
        for relationship_batch in self._chunk_items(relationships):
            try:
                with self._repository.transaction(knowledge_base_id):
                    stored_relationships.extend(
                        self._repository.upsert_relationships(knowledge_base_id, relationship_batch)
                    )
            except Exception as exc:
                raise BatchUpsertError(
                    successful_entity_count=len(stored_entities),
                    successful_relationship_count=len(stored_relationships),
                ) from exc

        return stored_entities, stored_relationships

    def query_neighborhood(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
    ) -> SubgraphResult:
        query = NeighborhoodQuery(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            depth=depth,
        )
        return self._repository.get_neighbors(
            query.knowledge_base_id,
            query.entity_id,
            query.depth,
            query.direction,
        )

    def get_neighbors(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int = 1,
    ) -> tuple[list[Entity], list[Relationship]]:
        """Return neighbors and relationships for ``entity_id``.

        Convenience over :meth:`query_neighborhood` that excludes the
        focal entity from the neighbor list and returns plain lists.
        """
        subgraph = self.query_neighborhood(knowledge_base_id, entity_id, depth)
        neighbors = [entity for entity in subgraph.entities if entity.id != entity_id]
        return neighbors, list(subgraph.relationships)

    def search_entities(
        self,
        knowledge_base_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        search_query = EntitySearchQuery(
            knowledge_base_id=knowledge_base_id,
            query=query,
            limit=limit,
            offset=offset,
        )
        repository_results = self._repository.search_entities(
            search_query.knowledge_base_id,
            search_query.query,
            search_query.limit + search_query.offset,
        )
        return repository_results[search_query.offset :]

    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics:
        entity_count = self._repository.count_entities(knowledge_base_id)
        relationship_count = self._repository.count_relationships(knowledge_base_id)
        avg_degree = 0.0
        if entity_count > 0:
            avg_degree = (2 * relationship_count) / entity_count

        result = GraphMetricsResult(
            knowledge_base_id=knowledge_base_id,
            metrics=GraphMetrics(
                entity_count=entity_count,
                relationship_count=relationship_count,
                avg_degree=avg_degree,
            ),
        )
        return result.metrics

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        """Remove all graph objects scoped to a knowledge base."""

        self._repository.delete_knowledge_base(knowledge_base_id)

    @staticmethod
    def _build_graph_update_storage_key(
        knowledge_base_id: str,
        extraction_result_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/graph_updates/{extraction_result_id}.json"


def create_graph_service(
    repository: GraphRepository,
    *,
    object_store: ObjectStoreProtocol,
    event_bus: EventBus,
    batch_size: int = 500,
) -> GraphService:
    """Create the default graph service."""

    return GraphService(
        repository,
        object_store=object_store,
        event_bus=event_bus,
        batch_size=batch_size,
    )


__all__ = ["GraphService", "create_graph_service"]