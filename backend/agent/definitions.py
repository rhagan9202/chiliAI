"""Workflow definition registry for agent-managed pipeline plans."""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field, model_validator


class WorkflowStepDef(BaseModel):
    """Static definition for a workflow step name."""

    name: str


class WorkflowDefinition(BaseModel):
    """Static workflow shape and event-to-step mapping."""

    definition_id: str
    steps: tuple[WorkflowStepDef, ...]
    default_step_sequence: tuple[str, ...] = ()
    event_step_mapping: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_definition(self) -> WorkflowDefinition:
        step_names = [step.name for step in self.steps]
        if not step_names:
            raise ValueError("WorkflowDefinition requires at least one step.")
        if len(set(step_names)) != len(step_names):
            raise ValueError("WorkflowDefinition step names must be unique.")

        known_steps = set(step_names)
        if not self.default_step_sequence:
            self.default_step_sequence = tuple(step_names)

        unknown_default_steps = [
            step_name
            for step_name in self.default_step_sequence
            if step_name not in known_steps
        ]
        if unknown_default_steps:
            raise ValueError(
                "WorkflowDefinition default sequence references unknown step "
                f"'{unknown_default_steps[0]}'."
            )

        for event_type, step_name in self.event_step_mapping.items():
            if step_name not in known_steps:
                raise ValueError(
                    "WorkflowDefinition event mapping references unknown step "
                    f"'{step_name}' for event '{event_type}'."
                )
        return self

    def step_names(self) -> list[str]:
        return [step.name for step in self.steps]

    def has_step(self, step_name: str) -> bool:
        return step_name in set(self.step_names())


class WorkflowDefinitionRegistry(BaseModel):
    """Registry of workflow definitions available to the agent module."""

    definitions: tuple[WorkflowDefinition, ...]
    default_definition_id: str

    @model_validator(mode="after")
    def _validate_registry(self) -> WorkflowDefinitionRegistry:
        definition_ids = [definition.definition_id for definition in self.definitions]
        if not definition_ids:
            raise ValueError("WorkflowDefinitionRegistry requires at least one definition.")
        if len(set(definition_ids)) != len(definition_ids):
            raise ValueError("WorkflowDefinition definition ids must be unique.")
        if self.default_definition_id not in set(definition_ids):
            raise ValueError(
                "WorkflowDefinitionRegistry default_definition_id must reference a "
                "registered definition."
            )
        return self

    def default_definition(self) -> WorkflowDefinition:
        for definition in self.definitions:
            if definition.definition_id == self.default_definition_id:
                return definition
        raise ValueError("Default workflow definition is not registered.")

    def default_step_names(self) -> list[str]:
        return list(self.default_definition().default_step_sequence)

    def step_for_event_type(self, event_type: str) -> str | None:
        return self.default_definition().event_step_mapping.get(event_type)

    def has_step(self, step_name: str) -> bool:
        return self.default_definition().has_step(step_name)

    def validate_step_names(self, step_names: list[str] | tuple[str, ...]) -> None:
        for step_name in step_names:
            if not self.has_step(step_name):
                raise ValueError(f"Unknown workflow step '{step_name}'.")


_DEFAULT_STEP_SEQUENCE: tuple[str, ...] = (
    "parse",
    "chunk",
    "extract",
    "validate",
    "graph_build",
    "embed",
    "vector_index",
    "ready",
    "monitoring",
)

_DEFAULT_EVENT_STEP_MAPPING: dict[str, str] = {
    "documents.uploaded": "parse",
    "documents.parsed": "chunk",
    "documents.failed": "parse",
    "records.ingested": "records_ingest",
    "documents.chunked": "extract",
    "entities.extracted": "validate",
    "entities.validated": "graph_build",
    "graph.updated": "embed",
    "embeddings.complete": "vector_index",
    "vectors.indexed": "ready",
    "kb.ready": "ready",
    "risk.scored": "monitoring",
}


@lru_cache(maxsize=1)
def default_workflow_registry() -> WorkflowDefinitionRegistry:
    """Return the built-in registry for current workflow behavior."""

    step_names = (*_DEFAULT_STEP_SEQUENCE, "records_ingest")
    return WorkflowDefinitionRegistry(
        definitions=(
            WorkflowDefinition(
                definition_id="default",
                steps=tuple(WorkflowStepDef(name=step_name) for step_name in step_names),
                default_step_sequence=_DEFAULT_STEP_SEQUENCE,
                event_step_mapping=_DEFAULT_EVENT_STEP_MAPPING,
            ),
        ),
        default_definition_id="default",
    )


__all__ = [
    "WorkflowDefinition",
    "WorkflowDefinitionRegistry",
    "WorkflowStepDef",
    "default_workflow_registry",
]
