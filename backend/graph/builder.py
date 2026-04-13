"""Graph-builder service for validated ingestion artifacts."""

from __future__ import annotations

from graph.models import GraphUpsertResult
from graph.protocols import GraphRepository
from ingestion.models import ValidationReport


class GraphBuilder:
    """Upsert validated runtime objects into the graph repository."""

    def __init__(self, repository: GraphRepository) -> None:
        self._repository = repository

    def upsert_validation_report(
        self,
        knowledge_base_id: str,
        validation_report: ValidationReport,
    ) -> GraphUpsertResult:
        stored_entities = self._repository.upsert_entities(
            knowledge_base_id,
            validation_report.valid_entities,
        )
        stored_relationships = self._repository.upsert_relationships(
            knowledge_base_id,
            validation_report.valid_relationships,
        )
        return GraphUpsertResult(
            knowledge_base_id=knowledge_base_id,
            validation_report_id=validation_report.id,
            extraction_result_id=validation_report.extraction_result_id,
            upserted_entity_ids=[entity.id for entity in stored_entities],
            upserted_relationship_ids=[relationship.id for relationship in stored_relationships],
        )


def create_graph_builder(repository: GraphRepository) -> GraphBuilder:
    """Create the default graph-builder service."""

    return GraphBuilder(repository)


__all__ = ["GraphBuilder", "create_graph_builder"]