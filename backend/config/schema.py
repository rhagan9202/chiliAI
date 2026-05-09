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
    # TODO(production): Extend with dedup_window_seconds: int, max_alerts_per_entity: int,
    # suppression_rules: list[SuppressionRule], escalation_policies: list[EscalationPolicy].
    # Add severity_levels: list[str] to make severity tiers configurable per domain.


class UiNavigationPageConfig(BaseModel):
    """A single frontend navigation page definition."""

    id: str
    label: str
    route: str
    capability: str | None = None


class UiNavigationConfig(BaseModel):
    """Frontend navigation structure."""

    pages: list[UiNavigationPageConfig]


class UiDisplayFieldsConfig(BaseModel):
    """Config-driven entity display field mapping for frontend rendering."""

    title: str
    subtitle: str | None = None
    chips: list[str] = Field(default_factory=list)


class UiRoleConfig(BaseModel):
    """Frontend role-driven navigation and permission hints."""

    landing_page: str
    pages: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class UiConfig(BaseModel):
    """Optional frontend UI metadata surfaced through the domain config."""

    default_entity_type: str | None = None
    navigation: UiNavigationConfig | None = None
    display_fields: dict[str, UiDisplayFieldsConfig] = Field(default_factory=dict)
    roles: dict[str, UiRoleConfig] = Field(default_factory=dict)


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
    ui: UiConfig | None = None
    # TODO(production): Add configuration sections for all external subsystems:
    # - graph: GraphDbConfig (backend: neo4j|memgraph|neptune, connection URI, pool size)
    # - vectorstore: VectorStoreConfig (backend: pgvector|qdrant|weaviate, connection, dims)
    # - llm: LlmConfig (provider: openai|anthropic|local, model, API key env, temperature)
    # - embeddings: EmbeddingsConfig (provider, model, dimensions, batch limits)
    # - storage: ObjectStoreConfig (backend: s3|gcs|minio|local, bucket, credentials env)
    # - events: EventBusConfig (absorb EventBusSettings from events/runtime.py into YAML)
    # - monitoring: MonitoringConfig (alerting rules, evaluation intervals, dedup windows)
    # - rag: RagConfig (top_k, expansion_depth, reranking, system_prompt template)
    # Add schema_version: str for config format versioning and migration.
    # See docs/architecture.md §9 and docs/config_engine_plan.md.

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
    "UiConfig",
    "UiDisplayFieldsConfig",
    "UiNavigationConfig",
    "UiNavigationPageConfig",
    "UiRoleConfig",
]
