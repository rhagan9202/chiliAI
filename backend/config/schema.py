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

from typing import Literal, cast

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
    peer_stats: bool = False


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


class GnnConfig(BaseModel):
    """Configuration for the GNN analytics graph-snapshot source."""

    snapshot_max_nodes: int = Field(default=5000, gt=0)


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

    provider: Literal["openai", "anthropic", "local", "ollama"] = "local"
    model: str = "local-default"
    api_key_env_var: str | None = None
    base_url: str | None = None  # Used by ollama and any provider needing a custom endpoint.
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
    fallback: "LlmConfig | None" = None


class EmbeddingsConfig(BaseModel):
    """Configuration for selecting the embeddings provider and model."""

    provider: Literal["openai", "sentence_transformers", "local"] = (
        "sentence_transformers"
    )
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = Field(default=384, gt=0)
    batch_size: int = Field(default=32, gt=0)
    api_key_env_var: str | None = None
    cache_enabled: bool = True
    cache_max_entries: int = Field(default=4096, gt=0)


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
    stream_maxlen: int | None = Field(default=None, gt=0)
    reclaim_min_idle_ms: int | None = Field(default=None, gt=0)


class DatabaseConfig(BaseModel):
    """Configuration for selecting the relational / time-series database backend."""

    backend: Literal["postgres", "in_memory"] = "in_memory"
    dsn_env_var: str = "DATABASE_URL"
    pool_size: int = Field(default=10, gt=0)
    pool_max_overflow: int = Field(default=5, ge=0)
    statement_timeout_ms: int = Field(default=30000, gt=0)


class MonitoringConfig(BaseModel):
    """Configuration for alert deduplication, evaluation cadence, and severity tiers."""

    evaluation_interval_seconds: int = Field(default=300, gt=0)
    dedup_window_seconds: int = Field(default=3600, gt=0)
    max_alerts_per_entity: int = Field(default=10, gt=0)
    max_alerts_per_evaluation: int = Field(default=100, gt=0)
    grouping_window_seconds: int = Field(default=300, gt=0)
    medium_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    high_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> MonitoringConfig:
        if self.high_threshold <= self.medium_threshold:
            raise ValueError(
                "MonitoringConfig high_threshold must exceed medium_threshold."
            )
        return self


class AnalyticsConfig(BaseModel):
    """Configuration for analytics persistence, recompute behavior, and risk tiers."""

    metrics_recompute_min_interval_seconds: int = Field(default=300, gt=0)
    medium_risk_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    high_risk_threshold: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_risk_thresholds(self) -> AnalyticsConfig:
        if self.high_risk_threshold <= self.medium_risk_threshold:
            raise ValueError(
                "AnalyticsConfig high_risk_threshold must exceed medium_risk_threshold."
            )
        return self


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
            "text/html",
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
    """Maps a numeric record field onto a scored monitoring observation.

    ``MonitoringObservation.score`` is bounded to [0, 1].  ``score_max`` is an
    optional normalization divisor (``score = raw_value / score_max``) for
    fields declared on another bounded scale (e.g. a 0-100 index).  It is a
    scale conversion, not a clamp: values that still fall outside [0, 1] after
    normalization fail the record batch loudly.  DomainConfig cross-validation
    requires the score_field's declared record_schema bounds to prove every
    in-schema value normalizes into [0, 1] — see
    ``DomainConfig._validate_cross_references``.
    """

    metric_name: str
    entity_type: str
    score_field: str
    score_max: float | None = Field(default=None, gt=0)
    rationale: str = ""


class RecordFeedConfig(BaseModel):
    """A single structured-ingestion feed definition."""

    name: str
    record_type: str
    source: Literal["file_upload", "api_push"]
    id_field: str
    # id_template overrides id_field when composite row keys are needed.
    # Use Python str.format() syntax referencing column names, e.g.
    # ``"{CLM_ID}:{SEGMENT}"`` for CMS inpatient/outpatient claim segments.
    id_template: str | None = None
    record_schema: dict[str, PropertyDefinition] = Field(default_factory=dict)
    # When True, columns not listed in record_schema are stored in the raw
    # payload but skipped during entity validation.  Required for wide
    # real-world files where only a subset of fields need typed validation.
    allow_extra_fields: bool = False
    # File formats accepted by the file-upload endpoint for this feed. Uploads
    # whose extension is not listed are rejected with HTTP 415.
    accepted_formats: list[str] = Field(
        default_factory=lambda: ["csv", "jsonl"]
    )
    entities: list[RecordEntityMapping] = Field(default_factory=lambda: [])
    relationships: list[RecordRelationshipMapping] = Field(default_factory=lambda: [])
    observations: list[RecordObservationMapping] = Field(default_factory=lambda: [])


class RecordsConfig(BaseModel):
    """Structured-ingestion feed configuration for the domain."""

    feeds: list[RecordFeedConfig] = Field(default_factory=lambda: [])


# ---------------------------------------------------------------------------
# Policy rule-pack models
# ---------------------------------------------------------------------------


class PolicyPredicateValue(BaseModel):
    """A predicate's right-hand value: exactly one of an inline literal or a
    ``config_ref`` resolving against the owning pack's ``thresholds`` map."""

    literal: str | float | int | bool | list[str] | None = None
    config_ref: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> PolicyPredicateValue:
        has_literal = self.literal is not None
        has_ref = self.config_ref is not None
        if has_literal == has_ref:
            raise ValueError(
                "PolicyPredicateValue requires exactly one of 'literal' or 'config_ref'."
            )
        return self


class PolicyPredicate(BaseModel):
    """A single bounded comparison evaluated against a target's field."""

    field: str  # "properties.<name>" | "risk_score" | "metric.<name>"
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"]
    value: PolicyPredicateValue


class PolicyCitationRef(BaseModel):
    """A policy/document reference surfaced on every item a rule generates."""

    citation_id: str
    title: str
    source_ref: str
    excerpt: str | None = None


class PolicyRule(BaseModel):
    """A single rule: select targets, test one predicate, emit an item per hit."""

    id: str
    title_template: str
    severity: Literal["medium", "high", "critical"]
    target_kind: Literal["entity", "alert", "metric"]
    target_selector: dict[str, str] = Field(default_factory=lambda: cast(dict[str, str], {}))
    predicate: PolicyPredicate
    citations: list[PolicyCitationRef] = Field(
        default_factory=lambda: cast(list[PolicyCitationRef], [])
    )


class PolicyRulePack(BaseModel):
    """A named bundle of rules with shared, config-referenceable thresholds."""

    id: str
    name: str
    description: str | None = None
    thresholds: dict[str, str | float | int | bool] = Field(
        default_factory=lambda: cast(dict[str, str | float | int | bool], {})
    )
    rules: list[PolicyRule] = Field(default_factory=lambda: cast(list[PolicyRule], []))

    @model_validator(mode="after")
    def _validate_config_refs(self) -> PolicyRulePack:
        # Fail fast at config load if a predicate references a threshold key
        # that the pack does not declare — otherwise the worker would silently
        # raise KeyError at evaluation time and produce an empty queue.
        for rule in self.rules:
            ref = rule.predicate.value.config_ref
            if ref is not None and ref not in self.thresholds:
                raise ValueError(
                    f"Policy rule '{rule.id}' references unknown threshold "
                    f"'{ref}' in pack '{self.id}'. Declared thresholds: "
                    f"{sorted(self.thresholds)}."
                )
        return self


# ---------------------------------------------------------------------------
# Scorecard template config
# ---------------------------------------------------------------------------


class ScorecardMetricInputConfig(BaseModel):
    """One named input consumed by a configured scorecard metric."""

    name: str
    source: Literal["record_feed", "metric", "graph", "document"]
    ref: str
    field: str | None = None
    filter: dict[str, str | float | int | bool] = Field(default_factory=dict)


class ScorecardFormulaConfig(BaseModel):
    """Bounded scorecard formula; no arbitrary code execution."""

    operator: Literal["ratio", "sum", "mean", "weighted_mean", "latest"]
    numerator: str | None = None
    denominator: str | None = None
    value: str | None = None
    weight: str | None = None

    @model_validator(mode="after")
    def _validate_operator_shape(self) -> ScorecardFormulaConfig:
        if self.operator == "ratio":
            missing = [
                field_name
                for field_name, input_ref in (
                    ("numerator", self.numerator),
                    ("denominator", self.denominator),
                )
                if input_ref is None
            ]
            extra = [
                field_name
                for field_name, input_ref in (
                    ("value", self.value),
                    ("weight", self.weight),
                )
                if input_ref is not None
            ]
        elif self.operator in {"sum", "mean", "latest"}:
            missing = ["value"] if self.value is None else []
            extra = [
                field_name
                for field_name, input_ref in (
                    ("numerator", self.numerator),
                    ("denominator", self.denominator),
                    ("weight", self.weight),
                )
                if input_ref is not None
            ]
        else:
            missing = [
                field_name
                for field_name, input_ref in (
                    ("value", self.value),
                    ("weight", self.weight),
                )
                if input_ref is None
            ]
            extra = [
                field_name
                for field_name, input_ref in (
                    ("numerator", self.numerator),
                    ("denominator", self.denominator),
                )
                if input_ref is not None
            ]

        if missing or extra:
            message_parts: list[str] = []
            if missing:
                message_parts.append(f"requires {', '.join(missing)}")
            if extra:
                message_parts.append(f"does not accept {', '.join(extra)}")
            raise ValueError(
                f"Scorecard formula operator '{self.operator}' "
                f"{' and '.join(message_parts)}."
            )

        return self


class ScorecardThresholdConfig(BaseModel):
    """Thresholds used to classify a configured scorecard metric.

    Exactly one grading direction may be used per metric:

    - higher-is-better: ``pass_min`` / ``warn_min`` / ``fail_max``
    - lower-is-better: ``pass_max`` / ``warn_max`` / ``fail_min``

    Mixing fields from both directions is a validation error, and at least
    one threshold field must be set so every metric has a defined grade.
    Bounds must also be coherent within their direction so grading bands
    cannot overlap: higher-is-better requires ``pass_min >= warn_min >
    fail_max`` and lower-is-better requires ``pass_max <= warn_max <
    fail_min`` (each comparison applies where both fields are present).
    """

    pass_min: float | None = None
    warn_min: float | None = None
    fail_max: float | None = None
    pass_max: float | None = None
    warn_max: float | None = None
    fail_min: float | None = None
    incomplete_when_missing: bool = True

    @model_validator(mode="after")
    def validate_threshold_direction(self) -> ScorecardThresholdConfig:
        has_higher = any(
            bound is not None
            for bound in (self.pass_min, self.warn_min, self.fail_max)
        )
        has_lower = any(
            bound is not None
            for bound in (self.pass_max, self.warn_max, self.fail_min)
        )
        if has_higher and has_lower:
            raise ValueError(
                "Scorecard thresholds cannot mix higher-is-better fields "
                "(pass_min/warn_min/fail_max) with lower-is-better fields "
                "(pass_max/warn_max/fail_min)."
            )
        if not has_higher and not has_lower:
            raise ValueError(
                "Scorecard thresholds must set at least one of "
                "pass_min/warn_min/fail_max or pass_max/warn_max/fail_min."
            )

        # Intra-direction ordering: bounds must be coherent so grading
        # bands cannot overlap (red-cell finding B1).
        if (
            self.pass_min is not None
            and self.warn_min is not None
            and self.pass_min < self.warn_min
        ):
            raise ValueError(
                f"Scorecard thresholds: pass_min {self.pass_min} must be "
                f">= warn_min {self.warn_min}."
            )
        for field_name, bound in (
            ("pass_min", self.pass_min),
            ("warn_min", self.warn_min),
        ):
            if (
                bound is not None
                and self.fail_max is not None
                and bound <= self.fail_max
            ):
                raise ValueError(
                    f"Scorecard thresholds: {field_name} {bound} must be "
                    f"> fail_max {self.fail_max}."
                )
        if (
            self.pass_max is not None
            and self.warn_max is not None
            and self.pass_max > self.warn_max
        ):
            raise ValueError(
                f"Scorecard thresholds: pass_max {self.pass_max} must be "
                f"<= warn_max {self.warn_max}."
            )
        for field_name, bound in (
            ("pass_max", self.pass_max),
            ("warn_max", self.warn_max),
        ):
            if (
                bound is not None
                and self.fail_min is not None
                and bound >= self.fail_min
            ):
                raise ValueError(
                    f"Scorecard thresholds: {field_name} {bound} must be "
                    f"< fail_min {self.fail_min}."
                )
        return self


class ScorecardMetricConfig(BaseModel):
    """A configured scorecard metric with safe formula metadata."""

    id: str
    label: str
    description: str = ""
    unit: str = ""
    housing_category: Literal["UH", "MFH", "combined"] = "combined"
    inputs: list[ScorecardMetricInputConfig]
    formula: ScorecardFormulaConfig
    thresholds: ScorecardThresholdConfig
    freshness_days: int = Field(default=90, gt=0)
    required: bool = True


class ScorecardSectionConfig(BaseModel):
    """A grouped set of scorecard metrics."""

    id: str
    label: str
    metrics: list[ScorecardMetricConfig]


class ScorecardTemplateConfig(BaseModel):
    """A safe configurable scorecard template."""

    id: str
    name: str
    category: Literal["UH", "MFH", "combined"]
    scope: Literal["enterprise", "majcom", "region", "installation", "market_area"]
    period: Literal["monthly", "quarterly", "annual", "ad_hoc"]
    sections: list[ScorecardSectionConfig]
    export_formats: list[Literal["json", "markdown"]] = Field(
        default_factory=lambda: ["json", "markdown"]
    )


class ScorecardsConfig(BaseModel):
    """Collection of configured scorecard templates for the domain."""

    templates: list[ScorecardTemplateConfig] = Field(default_factory=lambda: [])

    @model_validator(mode="after")
    def _validate_template_ids(self) -> ScorecardsConfig:
        seen: set[str] = set()
        for template in self.templates:
            if template.id in seen:
                raise ValueError(f"Duplicate scorecard template id: '{template.id}'")
            seen.add(template.id)
            section_ids: set[str] = set()
            for section in template.sections:
                if section.id in section_ids:
                    raise ValueError(
                        f"Duplicate scorecard section id '{section.id}' "
                        f"in template '{template.id}'"
                    )
                section_ids.add(section.id)
        return self


# ---------------------------------------------------------------------------
# Peer-group z-score config
# ---------------------------------------------------------------------------


class PeerMetricSpec(BaseModel):
    """One cross-sectional peer-group z-score metric derived from a record column."""

    name: str
    record_type: str
    entity_type: str
    entity_id_field: str
    value_column: str
    aggregation: Literal["sum", "mean", "count", "max", "min"]
    interval: Literal["day", "week", "month"]
    time_column: str | None = None
    group_by: list[str] = Field(default_factory=lambda: [])
    direction: Literal["high", "low", "two_sided"] = "high"
    z_cap: float = Field(default=4.0, gt=0.0)
    weight: float = Field(default=1.0, gt=0.0)
    min_peers: int = Field(default=5, ge=2)
    rationale_template: str = "{name}: z={z:.2f} vs {peer_group} peers"


class PeerStatsConfig(BaseModel):
    """Collection of peer-group z-score metric specs for a domain."""

    metrics: list[PeerMetricSpec] = Field(default_factory=lambda: [])


class TimeseriesMetricSpec(BaseModel):
    """One self-history anomaly-detection series derived from a record column.

    The aggregate identity (record_type … time_column) mirrors
    ``PeerMetricSpec`` so the peerstats record-column SQL can serve both:
    peerstats compares an entity to its peers cross-sectionally; a
    timeseries spec compares an entity to its own interval history.
    """

    name: str
    record_type: str
    entity_type: str
    entity_id_field: str
    value_column: str
    aggregation: Literal["sum", "mean", "count", "max", "min"]
    interval: Literal["day", "week", "month"]
    time_column: str | None = None
    detection_strategy: Literal[
        "z_score", "stl_decomposition", "isolation_forest"
    ] = "z_score"
    baseline_window: int = Field(default=5, gt=1)
    min_history: int = Field(default=6, gt=2)
    z_threshold: float = Field(default=2.0, gt=0.0)
    z_cap: float = Field(default=4.0, gt=0.0)
    signal_weight: float = Field(default=1.0, gt=0.0)

    @model_validator(mode="after")
    def _validate_history_requirements(self) -> TimeseriesMetricSpec:
        if self.min_history <= self.baseline_window:
            raise ValueError(
                "TimeseriesMetricSpec min_history must exceed baseline_window."
            )
        return self


class TimeseriesAnalyticsConfig(BaseModel):
    """Collection of self-history anomaly series specs for a domain."""

    metrics: list[TimeseriesMetricSpec] = Field(default_factory=lambda: [])


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
    analytics: AnalyticsConfig | None = None
    gnn: GnnConfig | None = None
    peer_stats: PeerStatsConfig | None = None
    timeseries: TimeseriesAnalyticsConfig | None = None
    scorecards: ScorecardsConfig = Field(default_factory=ScorecardsConfig)
    policy_rules: list[PolicyRulePack] = Field(
        default_factory=lambda: cast(list[PolicyRulePack], [])
    )
    alerts: AlertsConfig
    ui: UiConfig | None = None
    default_reference_kb_id: str | None = Field(
        default=None,
        description=(
            "ID of a knowledge base that is auto-attached to every read in this "
            "domain (the 'policy graph'). When None, dual-graph behavior is disabled "
            "and reads scope to the primary KB only."
        ),
    )

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
        if self.analytics is None:
            self.analytics = AnalyticsConfig()
        if self.gnn is None:
            self.gnn = GnnConfig()

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
                if observation_mapping.score_field not in schema_fields:
                    errors.append(
                        f"Records feed '{feed.name}' observation mapping score_field "
                        f"'{observation_mapping.score_field}' is not in record_schema."
                    )
                else:
                    # MonitoringObservation.score is bounded to [0, 1]; the
                    # declared record_schema bounds must prove every in-schema
                    # value lands (or normalizes via score_max) into [0, 1].
                    score_def = feed.record_schema[observation_mapping.score_field]
                    label = (
                        f"Records feed '{feed.name}' observation "
                        f"'{observation_mapping.metric_name}' score_field "
                        f"'{observation_mapping.score_field}'"
                    )
                    if score_def.type.value not in ("integer", "decimal"):
                        # Bounds on non-numeric types are not enforced at
                        # record intake, so a non-numeric score_field with
                        # numeric-looking bounds would pass load-time checks
                        # yet still hard-fail worker-side at mapping time.
                        errors.append(
                            f"{label} must be a numeric record_schema type "
                            f"(integer or decimal), got "
                            f"'{score_def.type.value}'."
                        )
                    else:
                        if score_def.min_value is None or score_def.min_value < 0:
                            errors.append(
                                f"{label} must declare min_value >= 0 in "
                                f"record_schema; observation scores are "
                                f"bounded to [0, 1]."
                            )
                        if observation_mapping.score_max is None:
                            if score_def.max_value is None or score_def.max_value > 1:
                                errors.append(
                                    f"{label} must declare max_value <= 1 in "
                                    f"record_schema, or the observation must "
                                    f"set score_max to normalize the field's "
                                    f"scale into [0, 1]."
                                )
                        elif score_def.max_value is None:
                            # A field with no declared upper bound (e.g. a
                            # raw count) can never be proven to normalize
                            # into [0, 1], so score_max on such a field is
                            # rejected outright.
                            errors.append(
                                f"{label} sets score_max but record_schema "
                                f"declares no max_value; an unbounded field "
                                f"cannot be proven to normalize into [0, 1]. "
                                f"Declare max_value or drop the observation."
                            )
                        elif score_def.max_value > observation_mapping.score_max:
                            errors.append(
                                f"{label} declares max_value "
                                f"{score_def.max_value} greater than "
                                f"score_max {observation_mapping.score_max}; "
                                f"normalized scores could exceed 1."
                            )

        # --- timeseries metric references ---
        if self.timeseries is not None and self.timeseries.metrics:
            feeds_by_record_type: dict[str, list[RecordFeedConfig]] = {}
            for feed in records_config.feeds:
                feeds_by_record_type.setdefault(feed.record_type, []).append(feed)
            for spec in self.timeseries.metrics:
                matching = feeds_by_record_type.get(spec.record_type, [])
                if not matching:
                    errors.append(
                        f"Timeseries metric '{spec.name}' references record_type "
                        f"'{spec.record_type}' not declared by any records feed."
                    )
                    continue
                for feed in matching:
                    schema_fields = feed.record_schema
                    label = (
                        f"Timeseries metric '{spec.name}' on records feed "
                        f"'{feed.name}'"
                    )
                    if spec.entity_id_field not in schema_fields:
                        errors.append(
                            f"{label}: entity_id_field '{spec.entity_id_field}' "
                            f"is not in record_schema."
                        )
                    value_def = schema_fields.get(spec.value_column)
                    if value_def is None:
                        errors.append(
                            f"{label}: value_column '{spec.value_column}' is not "
                            f"in record_schema."
                        )
                    elif value_def.type.value not in ("integer", "decimal"):
                        errors.append(
                            f"{label}: value_column '{spec.value_column}' must be "
                            f"numeric (integer or decimal), got "
                            f"'{value_def.type.value}'."
                        )
                    if spec.time_column is not None:
                        time_def = schema_fields.get(spec.time_column)
                        if time_def is None:
                            errors.append(
                                f"{label}: time_column '{spec.time_column}' is "
                                f"not in record_schema."
                            )
                        elif time_def.type.value not in ("date", "datetime"):
                            errors.append(
                                f"{label}: time_column '{spec.time_column}' must "
                                f"be a date or datetime field, got "
                                f"'{time_def.type.value}'."
                            )

        # --- scorecard template references ---
        feed_schemas = {
            feed.name: set(feed.record_schema.keys())
            for feed in records_config.feeds
        }
        for template in self.scorecards.templates:
            metric_ids: set[str] = set()
            for section in template.sections:
                for metric in section.metrics:
                    if metric.id in metric_ids:
                        errors.append(
                            f"Duplicate scorecard metric id '{metric.id}' in "
                            f"template '{template.id}'."
                        )
                    metric_ids.add(metric.id)

                    input_names = {metric_input.name for metric_input in metric.inputs}
                    for metric_input in metric.inputs:
                        if metric_input.source == "record_feed":
                            feed_schema = feed_schemas.get(metric_input.ref)
                            if feed_schema is None:
                                errors.append(
                                    f"Scorecard metric '{metric.id}' in template "
                                    f"'{template.id}' references unknown records feed "
                                    f"'{metric_input.ref}'."
                                )
                            elif metric_input.field is None:
                                errors.append(
                                    f"Scorecard metric '{metric.id}' in template "
                                    f"'{template.id}' record_feed input "
                                    f"'{metric_input.name}' requires field."
                                )
                            elif metric_input.field not in feed_schema:
                                errors.append(
                                    f"Scorecard metric '{metric.id}' in template "
                                    f"'{template.id}' record_feed input "
                                    f"'{metric_input.name}' references unknown field "
                                    f"'{metric_input.field}' in records feed "
                                    f"'{metric_input.ref}'."
                                )
                            # Filter keys must be declared feed fields; a
                            # typo'd key would otherwise match no records and
                            # silently degrade the metric to incomplete
                            # (red-cell finding B4/C1).
                            if feed_schema is not None:
                                for filter_key in sorted(metric_input.filter):
                                    if filter_key not in feed_schema:
                                        errors.append(
                                            f"Scorecard metric '{metric.id}' in "
                                            f"template '{template.id}' record_feed "
                                            f"input '{metric_input.name}' filter key "
                                            f"'{filter_key}' is not declared in "
                                            f"records feed '{metric_input.ref}'."
                                        )

                    formula_refs = (
                        ("numerator", metric.formula.numerator),
                        ("denominator", metric.formula.denominator),
                        ("value", metric.formula.value),
                        ("weight", metric.formula.weight),
                    )
                    for field_name, input_ref in formula_refs:
                        if input_ref is not None and input_ref not in input_names:
                            errors.append(
                                f"Scorecard metric '{metric.id}' in template "
                                f"'{template.id}' formula field '{field_name}' "
                                f"references undeclared input '{input_ref}'."
                            )

        if errors:
            raise ValueError(
                "Domain config validation failed:\n  - " + "\n  - ".join(errors)
            )

        return self


__all__ = [
    "AlertsConfig",
    "AnalyticsConfig",
    "AuthConfig",
    "CapabilitiesConfig",
    "ChunkingConfig",
    "DatabaseConfig",
    "DomainConfig",
    "DomainInfo",
    "GnnConfig",
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
    "PolicyCitationRef",
    "PolicyPredicate",
    "PolicyPredicateValue",
    "PolicyRule",
    "PolicyRulePack",
    "PeerMetricSpec",
    "PeerStatsConfig",
    "RagConfig",
    "RecordEntityMapping",
    "RecordFeedConfig",
    "RecordObservationMapping",
    "RecordRelationshipMapping",
    "RecordsConfig",
    "TimeseriesAnalyticsConfig",
    "TimeseriesMetricSpec",
    "ValidationConfig",
    "VectorStoreConfig",
    "ScorecardFormulaConfig",
    "ScorecardMetricConfig",
    "ScorecardMetricInputConfig",
    "ScorecardSectionConfig",
    "ScorecardTemplateConfig",
    "ScorecardThresholdConfig",
    "ScorecardsConfig",
]
