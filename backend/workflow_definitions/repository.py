"""Workflow definition repository protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from workflow_definitions.models import WorkflowDefinition, WorkflowDefinitionPage


@runtime_checkable
class WorkflowDefinitionRepository(Protocol):
    """Persist and retrieve versioned workflow definition snapshots."""

    def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition: ...

    def update_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition: ...

    def get_definition(
        self,
        knowledge_base_id: str,
        definition_id: str,
        version: str,
    ) -> WorkflowDefinition | None: ...

    def list_definitions(
        self,
        *,
        knowledge_base_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowDefinitionPage: ...


__all__ = ["WorkflowDefinitionRepository"]
