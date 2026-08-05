"""In-memory workflow definition repository for tests and local development."""

from __future__ import annotations

from threading import RLock

from workflow_definitions.models import WorkflowDefinition, WorkflowDefinitionPage

__all__ = ["InMemoryWorkflowDefinitionRepository"]


class InMemoryWorkflowDefinitionRepository:
    """A seeded workflow definition repository keyed by KB, definition, and version."""

    def __init__(self, definitions: list[WorkflowDefinition] | None = None) -> None:
        self._lock = RLock()
        self._definitions: dict[tuple[str, str, str], WorkflowDefinition] = {}
        for definition in definitions or []:
            self.save_definition(definition)

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        key = self._key(definition)
        with self._lock:
            if key in self._definitions:
                raise ValueError("Workflow definition snapshot already exists.")
            stored = self._copy_definition(definition)
            self._definitions[key] = stored
            return self._copy_definition(stored)

    def update_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        key = self._key(definition)
        with self._lock:
            if key not in self._definitions:
                raise KeyError(key)
            stored = self._copy_definition(definition)
            self._definitions[key] = stored
            return self._copy_definition(stored)

    def get_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition | None:
        with self._lock:
            definition = self._definitions.get((knowledge_base_id, definition_id, version))
            if definition is None:
                return None
            return self._copy_definition(definition)

    def list_definitions(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowDefinitionPage:
        if limit < 1:
            raise ValueError("limit must be positive.")
        if offset < 0:
            raise ValueError("offset must be non-negative.")
        with self._lock:
            definitions = [
                definition
                for definition in self._definitions.values()
                if knowledge_base_id is None
                or definition.knowledge_base_id == knowledge_base_id
            ]
            definitions.sort(
                key=lambda definition: (
                    definition.definition_id,
                    definition.version,
                    definition.knowledge_base_id,
                )
            )
            total_items = len(definitions)
            items = definitions[offset : offset + limit]
            return WorkflowDefinitionPage(
                items=[self._copy_definition(definition) for definition in items],
                total_items=total_items,
                limit=limit,
                offset=offset,
            )

    @staticmethod
    def _key(definition: WorkflowDefinition) -> tuple[str, str, str]:
        return (
            definition.knowledge_base_id,
            definition.definition_id,
            definition.version,
        )

    @staticmethod
    def _copy_definition(definition: WorkflowDefinition) -> WorkflowDefinition:
        return definition.model_copy(deep=True)
