"""Pydantic models for the domain configuration schema.

The ``DomainConfig`` model is the top-level object produced by loading a
domain YAML/JSON configuration file.  Cross-field validation ensures
referential integrity between entities and relationships.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from shared.types import EntityDefinition, RelationshipDefinition


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class DomainInfo(BaseModel):
    """Metadata about the domain."""

    name: str
    display_name: str
    description: str


class CapabilitiesConfig(BaseModel):
    """Feature toggles for optional analytics capabilities."""

    timeseries: bool = False
    gnn: bool = False
    risk_scoring: bool = False
    rag_chat: bool = False
    explainability: bool = False


class IngestionSourceConfig(BaseModel):
    """A single ingestion source definition."""

    type: Literal["file_upload", "api_push"]
    formats: list[str] | None = None
    format: str | None = None
    endpoint: str | None = None


class ChunkingConfig(BaseModel):
    """Configuration for parsed document chunking."""

    strategy: Literal["recursive", "fixed_size", "sentence"] = "recursive"
    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=200, ge=0)
    min_chunk_size: int = Field(default=50, gt=0)
    record_template: str | None = None

    @model_validator(mode="after")
    def _validate_sizes(self) -> ChunkingConfig:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        if self.min_chunk_size > self.chunk_size:
            if "min_chunk_size" not in self.model_fields_set:
                self.min_chunk_size = self.chunk_size
                return self
            raise ValueError("min_chunk_size must be <= chunk_size.")
        return self


class IngestionConfig(BaseModel):
    """Ingestion configuration."""

    sources: list[IngestionSourceConfig]
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)


class AlertsConfig(BaseModel):
    """Alert thresholds keyed by entity type, then metric name."""

    thresholds: dict[str, dict[str, float]]


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class DomainConfig(BaseModel):
    """Top-level domain configuration model.

    Validated from a YAML or JSON file at startup, then shared with all
    backend modules via dependency injection.
    """

    domain: DomainInfo
    entities: list[EntityDefinition]
    relationships: list[RelationshipDefinition]
    capabilities: CapabilitiesConfig
    ingestion: IngestionConfig
    alerts: AlertsConfig

    @model_validator(mode="after")
    def _validate_cross_references(self) -> DomainConfig:
        errors: list[str] = []

        # --- duplicate entity names ---
        entity_names: list[str] = [e.name for e in self.entities]
        seen: set[str] = set()
        for name in entity_names:
            if name in seen:
                errors.append(f"Duplicate entity name: '{name}'")
            seen.add(name)

        # --- duplicate relationship names ---
        rel_names: list[str] = [r.name for r in self.relationships]
        seen_rels: set[str] = set()
        for name in rel_names:
            if name in seen_rels:
                errors.append(f"Duplicate relationship name: '{name}'")
            seen_rels.add(name)

        # --- relationship source/target must reference a declared entity ---
        entity_name_set = set(entity_names)
        for rel in self.relationships:
            if rel.source not in entity_name_set:
                errors.append(
                    f"Relationship '{rel.name}' source '{rel.source}' "
                    f"does not match any declared entity."
                )
            if rel.target not in entity_name_set:
                errors.append(
                    f"Relationship '{rel.name}' target '{rel.target}' "
                    f"does not match any declared entity."
                )

        # --- enum properties must declare enum_values ---
        for entity in self.entities:
            for prop_name, prop_def in entity.properties.items():
                if prop_def.type.value == "enum" and not prop_def.enum_values:
                    errors.append(
                        f"Entity '{entity.name}' property '{prop_name}' "
                        f"has type 'enum' but no enum_values defined."
                    )

        if errors:
            raise ValueError(
                "Domain config validation failed:\n  - " + "\n  - ".join(errors)
            )

        return self


__all__ = [
    "AlertsConfig",
    "CapabilitiesConfig",
    "ChunkingConfig",
    "DomainConfig",
    "DomainInfo",
    "IngestionConfig",
    "IngestionSourceConfig",
]
