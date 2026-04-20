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


class GraphDbConfig(BaseModel):
    """Configuration for selecting the graph database backend."""

    backend: Literal["neo4j", "memgraph", "in_memory"] = "in_memory"
    uri: str | None = None
    pool_size: int = 10
    auth_env_var: str | None = None


class VectorStoreConfig(BaseModel):
    """Configuration for selecting the vector store backend."""

    backend: Literal["qdrant", "pgvector", "in_memory"] = "in_memory"
    uri: str | None = None
    dimensions: int = Field(default=384, gt=0)
    distance_metric: Literal["cosine", "dot", "euclidean"] = "cosine"
    # Cross-validation with EmbeddingsConfig.dimensions is deferred to E1-S06.


class LlmConfig(BaseModel):
    """Configuration for selecting the LLM provider and model."""

    provider: Literal["openai", "anthropic", "local"] = "local"
    model: str = "local-default"
    api_key_env_var: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)


class EmbeddingsConfig(BaseModel):
    """Configuration for selecting the embeddings provider and model."""

    provider: Literal["openai", "sentence_transformers", "local"] = (
        "sentence_transformers"
    )
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = Field(default=384, gt=0)
    batch_size: int = Field(default=32, gt=0)
    api_key_env_var: str | None = None


class ObjectStoreConfig(BaseModel):
    """Configuration for selecting the object store backend."""

    backend: Literal["s3", "gcs", "minio", "local"] = "local"
    bucket: str | None = None
    base_path: str | None = None
    credentials_env_var: str | None = None


class EventBusConfig(BaseModel):
    """Configuration for selecting the event transport backend."""

    backend: Literal["redis", "in_memory"] = "in_memory"
    uri: str | None = None
    stream_prefix: str = "chili"
    consumer_group: str = "chili-workers"


class MonitoringConfig(BaseModel):
    """Configuration for alert deduplication and evaluation cadence."""

    evaluation_interval_seconds: int = Field(default=300, gt=0)
    dedup_window_seconds: int = Field(default=3600, gt=0)
    max_alerts_per_entity: int = Field(default=10, gt=0)


class RagConfig(BaseModel):
    """Configuration for retrieval-augmented generation behavior."""

    top_k: int = Field(default=5, gt=0)
    expansion_depth: int = Field(default=2, ge=0)
    reranking_enabled: bool = False
    system_prompt_template: str | None = None


class AlertsConfig(BaseModel):
    """Alert thresholds keyed by entity type, then metric name."""

    thresholds: dict[str, dict[str, float]]
    # TODO(production): Extend with dedup_window_seconds: int, max_alerts_per_entity: int,
    # suppression_rules: list[SuppressionRule], escalation_policies: list[EscalationPolicy].
    # Add severity_levels: list[str] to make severity tiers configurable per domain.


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class DomainConfig(BaseModel):
    """Top-level domain configuration model.

    Validated from a YAML or JSON file at startup, then shared with all
    backend modules via dependency injection.
    """

    schema_version: str = "1.0"
    domain: DomainInfo
    entities: list[EntityDefinition]
    relationships: list[RelationshipDefinition]
    capabilities: CapabilitiesConfig
    ingestion: IngestionConfig
    graph: GraphDbConfig | None = None
    vectorstore: VectorStoreConfig | None = None
    llm: LlmConfig | None = None
    embeddings: EmbeddingsConfig | None = None
    storage: ObjectStoreConfig | None = None
    events: EventBusConfig | None = None
    monitoring: MonitoringConfig | None = None
    rag: RagConfig | None = None
    alerts: AlertsConfig

    @model_validator(mode="after")
    def _validate_cross_references(self) -> DomainConfig:
        provided_vectorstore = self.vectorstore
        provided_embeddings = self.embeddings

        if (
            provided_vectorstore is not None
            and provided_embeddings is not None
            and provided_vectorstore.dimensions != provided_embeddings.dimensions
        ):
            raise ValueError(
                "Embeddings dimensions must match vectorstore dimensions when both sections are configured."
            )

        if self.graph is None:
            self.graph = GraphDbConfig()
        if self.vectorstore is None:
            self.vectorstore = VectorStoreConfig()
        if self.llm is None:
            self.llm = LlmConfig()
        if self.embeddings is None:
            self.embeddings = EmbeddingsConfig()
        if self.storage is None:
            self.storage = ObjectStoreConfig()
        if self.events is None:
            self.events = EventBusConfig()
        if self.monitoring is None:
            self.monitoring = MonitoringConfig()
        if self.rag is None:
            self.rag = RagConfig()

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
    "GraphDbConfig",
    "IngestionConfig",
    "IngestionSourceConfig",
    "EmbeddingsConfig",
    "EventBusConfig",
    "LlmConfig",
    "MonitoringConfig",
    "ObjectStoreConfig",
    "RagConfig",
    "VectorStoreConfig",
]
