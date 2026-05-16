"""Pydantic models for the domain configuration schema.

The ``DomainConfig`` model is the top-level object produced by loading a
domain YAML/JSON configuration file.  Cross-field validation ensures
referential integrity between entities and relationships.

Secret handling -- ``*_env_var`` pattern (E10-S12)
--------------------------------------------------
Secrets (LLM API keys, DB credentials, object-store credentials) are
**never** stored inline in the config file. Instead, every config section
that needs a secret declares an ``*_env_var: str`` field -- for example
``LlmConfig.api_key_env_var``, ``GraphDbConfig.auth_env_var``,
``EmbeddingsConfig.api_key_env_var``, ``ObjectStoreConfig.credentials_env_var``.
The field's value is the **name** of an environment variable (e.g.
``"OPENAI_API_KEY"``); adapters read ``os.environ[<name>]`` at construction
time. Required runtime secret env vars (provisioned by ops via Kubernetes
Secrets, see ``infra/README.md``):

    NEO4J_PASSWORD, REDIS_PASSWORD, QDRANT_API_KEY,
    MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    OPENAI_API_KEY, ANTHROPIC_API_KEY, JWT_SIGNING_KEY

This keeps secret material out of the repository, out of YAML config files,
out of logs, and out of any structured ``model_dump()`` output.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from shared.types import EntityDefinition, PropertyDefinition, RelationshipDefinition


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
    structured_ingestion: bool = False


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

    backend: Literal["neo4j", "in_memory"] = "in_memory"
    uri: str | None = None
    pool_size: int = 10
    auth_env_var: str | None = None


class VectorStoreConfig(BaseModel):
    """Configuration for selecting the vector store backend."""

    backend: Literal["qdrant", "in_memory"] = "in_memory"
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

    backend: Literal["s3", "minio", "local"] = "local"
    endpoint_url: str | None = None
    bucket: str | None = None
    base_path: str | None = None
    credentials_env_var: str | None = None


class EventBusConfig(BaseModel):
    """Configuration for selecting the event transport backend."""

    backend: Literal["redis", "in_memory"] = "in_memory"
    uri: str | None = None
    stream_prefix: str = "chili"
    consumer_group: str = "chili-workers"


class DatabaseConfig(BaseModel):
    """Configuration for selecting the relational / time-series database backend."""

    backend: Literal["postgres", "in_memory"] = "in_memory"
    dsn_env_var: str = "DATABASE_URL"
    pool_size: int = Field(default=10, gt=0)
    pool_max_overflow: int = Field(default=5, ge=0)
    statement_timeout_ms: int = Field(default=30000, gt=0)


class MonitoringConfig(BaseModel):
    """Configuration for alert deduplication and evaluation cadence."""

    evaluation_interval_seconds: int = Field(default=300, gt=0)
    dedup_window_seconds: int = Field(default=3600, gt=0)
    max_alerts_per_entity: int = Field(default=10, gt=0)
    max_alerts_per_evaluation: int = Field(default=100, gt=0)
    grouping_window_seconds: int = Field(default=300, gt=0)


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
class AuthConfig(BaseModel):
    """JWT/OIDC authentication configuration (E10-S06)."""

    enabled: bool = False
    issuer_url: str | None = None
    audience: str | None = None
    jwks_uri: str | None = None
    roles_claim: str = "roles"
    jwks_cache_seconds: int = Field(default=3600, gt=0)

    # OIDC client (used by the BFF auth router)
    client_id: str | None = None
    client_secret_env_var: str | None = None
    authorize_endpoint: str | None = None
    token_endpoint: str | None = None
    end_session_endpoint: str | None = None
    scopes: list[str] = Field(
        default_factory=lambda: ["openid", "email", "profile"]
    )
    redirect_uri: str | None = None

    # Cookie / session
    cookie_secure: bool = True
    cookie_domain: str | None = None
    session_ttl_seconds: int = Field(default=3600, gt=0)


class ValidationConfig(BaseModel):
    """Inbound payload limits applied across the API gateway (E10-S10)."""

    max_file_size_mb: int = Field(default=50, gt=0)
    allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "text/plain",
            "text/csv",
            "application/json",
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ]
    )
    max_query_length: int = Field(default=10000, gt=0)
    max_rag_question_length: int = Field(default=5000, gt=0)


class RecordEntityMapping(BaseModel):
    """Maps fields of a record row onto one graph entity."""

    entity_type: str
    id_field: str
    property_fields: dict[str, str] = Field(default_factory=dict)


class RecordRelationshipMapping(BaseModel):
    """Maps a pair of a row's mapped entities onto one graph relationship."""

    relationship_type: str
    source_entity_type: str
    target_entity_type: str


class RecordObservationMapping(BaseModel):
    """Maps a numeric record field onto a scored monitoring observation."""

    metric_name: str
    entity_type: str
    score_field: str
    rationale: str = ""


class RecordFeedConfig(BaseModel):
    """A single structured-ingestion feed definition."""

    name: str
    record_type: str
    source: Literal["file_upload", "api_push"]
    id_field: str
    record_schema: dict[str, PropertyDefinition] = Field(default_factory=dict)
    entities: list[RecordEntityMapping] = Field(default_factory=lambda: [])
    relationships: list[RecordRelationshipMapping] = Field(default_factory=lambda: [])
    observations: list[RecordObservationMapping] = Field(default_factory=lambda: [])


class RecordsConfig(BaseModel):
    """Structured-ingestion feed configuration for the domain."""

    feeds: list[RecordFeedConfig] = Field(default_factory=lambda: [])


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
    database: DatabaseConfig | None = None
    monitoring: MonitoringConfig | None = None
    rag: RagConfig | None = None
    auth: AuthConfig | None = None
    validation: ValidationConfig | None = None
    records: RecordsConfig | None = None
    alerts: AlertsConfig
    ui: UiConfig | None = None

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
        if self.database is None:
            self.database = DatabaseConfig()
        if self.monitoring is None:
            self.monitoring = MonitoringConfig()
        if self.rag is None:
            self.rag = RagConfig()
        if self.auth is None:
            self.auth = AuthConfig()
        if self.validation is None:
            self.validation = ValidationConfig()
        if self.records is None:
            self.records = RecordsConfig()

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

        # --- records feed references ---
        records_config: RecordsConfig = self.records
        relationship_name_set = set(rel_names)
        for feed in records_config.feeds:
            schema_fields = set(feed.record_schema.keys())
            if feed.id_field not in schema_fields:
                errors.append(
                    f"Records feed '{feed.name}' id_field '{feed.id_field}' "
                    f"is not declared in record_schema."
                )
            feed_entity_types: set[str] = set()
            for entity_mapping in feed.entities:
                feed_entity_types.add(entity_mapping.entity_type)
                if entity_mapping.entity_type not in entity_name_set:
                    errors.append(
                        f"Records feed '{feed.name}' maps to unknown entity "
                        f"type '{entity_mapping.entity_type}'."
                    )
                if entity_mapping.id_field not in schema_fields:
                    errors.append(
                        f"Records feed '{feed.name}' entity mapping id_field "
                        f"'{entity_mapping.id_field}' is not in record_schema."
                    )
            for relationship_mapping in feed.relationships:
                if relationship_mapping.relationship_type not in relationship_name_set:
                    errors.append(
                        f"Records feed '{feed.name}' maps to unknown relationship "
                        f"type '{relationship_mapping.relationship_type}'."
                    )
                if relationship_mapping.source_entity_type not in feed_entity_types:
                    errors.append(
                        f"Records feed '{feed.name}' relationship mapping "
                        f"source_entity_type '{relationship_mapping.source_entity_type}' "
                        f"is not mapped by the feed."
                    )
                if relationship_mapping.target_entity_type not in feed_entity_types:
                    errors.append(
                        f"Records feed '{feed.name}' relationship mapping "
                        f"target_entity_type '{relationship_mapping.target_entity_type}' "
                        f"is not mapped by the feed."
                    )
            for observation_mapping in feed.observations:
                if observation_mapping.entity_type not in feed_entity_types:
                    errors.append(
                        f"Records feed '{feed.name}' observation references entity "
                        f"type '{observation_mapping.entity_type}' not mapped by the feed."
                    )

        if errors:
            raise ValueError(
                "Domain config validation failed:\n  - " + "\n  - ".join(errors)
            )

        return self


__all__ = [
    "AlertsConfig",
    "AuthConfig",
    "CapabilitiesConfig",
    "ChunkingConfig",
    "DatabaseConfig",
    "DomainConfig",
    "DomainInfo",
    "GraphDbConfig",
    "IngestionConfig",
    "IngestionSourceConfig",
    "UiConfig",
    "UiDisplayFieldsConfig",
    "UiNavigationConfig",
    "UiNavigationPageConfig",
    "UiRoleConfig",
    "EmbeddingsConfig",
    "EventBusConfig",
    "LlmConfig",
    "MonitoringConfig",
    "ObjectStoreConfig",
    "RagConfig",
    "RecordEntityMapping",
    "RecordFeedConfig",
    "RecordObservationMapping",
    "RecordRelationshipMapping",
    "RecordsConfig",
    "ValidationConfig",
    "VectorStoreConfig",
]
