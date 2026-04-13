"""Service entry point for graph update flows."""

from __future__ import annotations

from events.protocols import EventBus
from events.types import GraphUpdatedDocumentReference, GraphUpdatedEvent
from graph.adapters.protocols import GraphRepository
from graph.exceptions import GraphPersistenceError
from graph.models import GraphUpsertResult
from graph.service_models import GraphBuildReceipt, GraphBuildTask
from storage.protocols import ObjectStore


class GraphService:
    """Persist validated runtime objects and publish graph update events."""

    def __init__(
        self,
        repository: GraphRepository,
        *,
        object_store: ObjectStore,
        event_bus: EventBus,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._event_bus = event_bus

    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt:
        try:
            stored_entities = self._repository.upsert_entities(
                task.knowledge_base_id,
                task.entities,
            )
            stored_relationships = self._repository.upsert_relationships(
                task.knowledge_base_id,
                task.relationships,
            )
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

    @staticmethod
    def _build_graph_update_storage_key(
        knowledge_base_id: str,
        extraction_result_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/graph_updates/{extraction_result_id}.json"


def create_graph_service(
    repository: GraphRepository,
    *,
    object_store: ObjectStore,
    event_bus: EventBus,
) -> GraphService:
    """Create the default graph service."""

    return GraphService(repository, object_store=object_store, event_bus=event_bus)


__all__ = ["GraphService", "create_graph_service"]