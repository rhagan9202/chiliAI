"""Tests for config.schema — DomainConfig validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import (
    AlertsConfig,
    AnalyticsConfig,
    AuthConfig,
    CapabilitiesConfig,
    ChunkingConfig,
    DomainConfig,
    DomainInfo,
    EmbeddingsConfig,
    EventBusConfig,
    GnnConfig,
    GraphDbConfig,
    IngestionConfig,
    IngestionSourceConfig,
    TimeseriesMetricSpec,
    UiConfig,
    UiDisplayFieldsConfig,
    UiNavigationConfig,
    UiNavigationPageConfig,
    UiRoleConfig,
    LlmConfig,
    MonitoringConfig,
    ObjectStoreConfig,
    RagConfig,
    RecordsAnalyticsTriggerConfig,
    RecordsConfig,
    ValidationConfig,
    VectorStoreConfig,
)
from shared.types import (
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    RelationshipDefinition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_entity(name: str = "thing") -> EntityDefinition:
    return EntityDefinition(
        name=name,
        display_label=name.title(),
        icon="box",
        properties={
            "id": PropertyDefinition(type=PropertyType.STRING, display="ID"),
        },
    )


def _make_config(
    *,
    entities: list[EntityDefinition] | None = None,
    relationships: list[RelationshipDefinition] | None = None,
    graph: GraphDbConfig | None = None,
    vectorstore: VectorStoreConfig | None = None,
    llm: LlmConfig | None = None,
    embeddings: EmbeddingsConfig | None = None,
    storage: ObjectStoreConfig | None = None,
    events: EventBusConfig | None = None,
    monitoring: MonitoringConfig | None = None,
    rag: RagConfig | None = None,
    gnn: GnnConfig | None = None,
    schema_version: str = "1.0",
    default_reference_kb_id: str | None = None,
) -> DomainConfig:
    """Build a minimal valid DomainConfig, optionally overriding parts."""
    ents = entities if entities is not None else [_minimal_entity("alpha")]
    rels = relationships if relationships is not None else []
    return DomainConfig(
        schema_version=schema_version,
        domain=DomainInfo(
            name="test", display_name="Test", description="Test domain"
        ),
        entities=ents,
        relationships=rels,
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(
            sources=[IngestionSourceConfig(type="file_upload", formats=["csv"])]
        ),
        graph=graph,
        vectorstore=vectorstore,
        llm=llm,
        embeddings=embeddings,
        storage=storage,
        events=events,
        monitoring=monitoring,
        rag=rag,
        gnn=gnn,
        alerts=AlertsConfig(thresholds={}),
        ui=UiConfig(
            default_entity_type="alpha",
            navigation=UiNavigationConfig(
                pages=[
                    UiNavigationPageConfig(
                        id="dashboard",
                        label="Dashboard",
                        route="/dashboard",
                    )
                ]
            ),
            display_fields={
                "alpha": UiDisplayFieldsConfig(title="id")
            },
            roles={
                "analyst": UiRoleConfig(
                    landing_page="dashboard",
                    pages=["dashboard"],
                    permissions=["alerts:read"],
                )
            },
        ),
        default_reference_kb_id=default_reference_kb_id,
    )


def _scorecard_metric_data(
    *,
    formula: dict[str, str],
    inputs: list[dict[str, str]],
    metric_id: str = "metric",
) -> dict[str, object]:
    return {
        "id": metric_id,
        "label": "Metric",
        "inputs": inputs,
        "formula": formula,
        "thresholds": {"pass_min": 1.0},
    }


def _config_data_with_scorecard_metric(metric: dict[str, object]) -> dict[str, object]:
    data = _make_config().model_dump()
    data["scorecards"] = {
        "templates": [
            {
                "id": "readiness",
                "name": "Readiness",
                "category": "combined",
                "scope": "installation",
                "period": "quarterly",
                "sections": [
                    {
                        "id": "section",
                        "label": "Section",
                        "metrics": [metric],
                    }
                ],
            }
        ]
    }
    return data


def _config_data_with_record_feed_scorecard_input(
    metric_input: dict[str, str],
) -> dict[str, object]:
    data = _config_data_with_scorecard_metric(
        _scorecard_metric_data(
            formula={"operator": "latest", "value": "source"},
            inputs=[metric_input],
        )
    )
    data["records"] = {
        "feeds": [
            {
                "name": "source_feed",
                "record_type": "source_record",
                "source": "file_upload",
                "id_field": "record_id",
                "record_schema": {
                    "record_id": {
                        "type": "string",
                        "display": "Record ID",
                        "required": True,
                    },
                    "score": {"type": "decimal", "display": "Score"},
                },
            }
        ]
    }
    return data


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestDomainConfigValid:
    def test_minimal_config(self) -> None:
        cfg = _make_config()
        assert cfg.schema_version == "1.0"
        assert cfg.domain.name == "test"
        assert len(cfg.entities) == 1

    def test_roundtrip(self) -> None:
        cfg = _make_config()
        data = cfg.model_dump()
        restored = DomainConfig.model_validate(data)
        assert restored == cfg

    def test_roundtrip_with_graph_config(self) -> None:
        cfg = _make_config(
            graph=GraphDbConfig(
                backend="neo4j",
                uri="bolt://localhost:7687",
                pool_size=20,
                auth_env_var="GRAPH_DB_AUTH",
            )
        )

        data = cfg.model_dump()
        restored = DomainConfig.model_validate(data)

        assert restored == cfg
        assert restored.graph is not None
        assert restored.graph.backend == "neo4j"

    def test_roundtrip_with_vectorstore_config(self) -> None:
        cfg = _make_config(
            embeddings=EmbeddingsConfig(dimensions=768),
            vectorstore=VectorStoreConfig(
                backend="qdrant",
                uri="http://localhost:6333",
                dimensions=768,
                distance_metric="dot",
            )
        )

        data = cfg.model_dump()
        restored = DomainConfig.model_validate(data)

        assert restored == cfg
        assert restored.vectorstore is not None
        assert restored.vectorstore.backend == "qdrant"

    def test_roundtrip_with_extended_subsystem_config(self) -> None:
        cfg = _make_config(
            llm=LlmConfig(
                provider="openai",
                model="gpt-4.1-mini",
                api_key_env_var="OPENAI_API_KEY",
                temperature=0.3,
                max_tokens=2048,
            ),
            embeddings=EmbeddingsConfig(
                provider="openai",
                model="text-embedding-3-small",
                dimensions=768,
                batch_size=16,
                api_key_env_var="OPENAI_API_KEY",
            ),
            vectorstore=VectorStoreConfig(
                backend="qdrant",
                uri="http://localhost:6333",
                dimensions=768,
                distance_metric="cosine",
            ),
            storage=ObjectStoreConfig(
                backend="s3",
                endpoint_url="http://localhost:9000",
                bucket="chili-docs",
                base_path="knowledgebases/",
                credentials_env_var="AWS_CREDENTIALS",
            ),
            events=EventBusConfig(
                backend="redis",
                uri="redis://localhost:6379/0",
                stream_prefix="chili",
                consumer_group="workers",
            ),
            monitoring=MonitoringConfig(
                evaluation_interval_seconds=120,
                dedup_window_seconds=900,
                max_alerts_per_entity=5,
            ),
            rag=RagConfig(
                top_k=8,
                expansion_depth=3,
                reranking_enabled=True,
                system_prompt_template="Answer with citations.",
            ),
            schema_version="1.1",
        )

        data = cfg.model_dump()
        restored = DomainConfig.model_validate(data)

        assert restored == cfg

    def test_multiple_entities_and_relationships(self) -> None:
        ents = [_minimal_entity("a"), _minimal_entity("b")]
        rels = [
            RelationshipDefinition(
                name="a_to_b", display_label="A→B", source="a", target="b"
            )
        ]
        cfg = _make_config(entities=ents, relationships=rels)
        assert len(cfg.relationships) == 1

    def test_ingestion_chunking_defaults(self) -> None:
        cfg = _make_config()
        assert cfg.ingestion.chunking.strategy == "recursive"
        assert cfg.ingestion.chunking.chunk_size == 1000
        assert cfg.ingestion.chunking.chunk_overlap == 200

    def test_graph_config_defaults_to_in_memory_when_absent(self) -> None:
        cfg = _make_config()

        assert cfg.graph is not None
        assert cfg.graph.backend == "in_memory"
        assert cfg.graph.uri is None
        assert cfg.graph.pool_size == 10
        assert cfg.graph.auth_env_var is None

    def test_vectorstore_config_defaults_to_in_memory_when_absent(self) -> None:
        cfg = _make_config()

        assert cfg.vectorstore is not None
        assert cfg.vectorstore.backend == "in_memory"
        assert cfg.vectorstore.uri is None
        assert cfg.vectorstore.dimensions == 384
        assert cfg.vectorstore.distance_metric == "cosine"

    def test_validation_defaults_allow_every_registered_parser_content_type(self) -> None:
        cfg = _make_config()

        assert cfg.validation is not None
        allowed = set(cfg.validation.allowed_content_types)
        # Every content type the parser registry can handle must be uploadable,
        # otherwise a registered parser is unreachable through the API.
        assert "text/html" in allowed
        assert "application/pdf" in allowed
        assert "text/plain" in allowed

    def test_new_subsystem_config_defaults_when_absent(self) -> None:
        cfg = _make_config()

        assert cfg.llm is not None
        assert cfg.llm.provider == "local"
        assert cfg.llm.model == "local-default"
        assert cfg.embeddings is not None
        assert cfg.embeddings.provider == "sentence_transformers"
        assert cfg.embeddings.dimensions == 384
        assert cfg.storage is not None
        assert cfg.storage.backend == "local"
        assert cfg.events is not None
        assert cfg.events.backend == "in_memory"
        assert cfg.monitoring is not None
        assert cfg.monitoring.evaluation_interval_seconds == 300
        assert cfg.rag is not None
        assert cfg.rag.top_k == 5

    def test_self_referencing_relationship(self) -> None:
        ents = [_minimal_entity("node")]
        rels = [
            RelationshipDefinition(
                name="links_to", display_label="Links To", source="node", target="node"
            )
        ]
        cfg = _make_config(entities=ents, relationships=rels)
        assert cfg.relationships[0].source == "node"

    def test_ui_config_roundtrip(self) -> None:
        cfg = _make_config()
        assert cfg.ui is not None
        assert cfg.ui.default_entity_type == "alpha"
        assert cfg.ui.navigation is not None
        assert cfg.ui.navigation.pages[0].route == "/dashboard"


def test_typologies_and_feature_catalog_round_trip() -> None:
    payload = _make_config(entities=[_minimal_entity("provider")]).model_dump(
        mode="json"
    )
    payload["policy_rules"] = [
        {
            "id": "billing_thresholds",
            "name": "Billing thresholds",
            "thresholds": {"max_billed_amount": 5000},
            "rules": [
                {
                    "id": "claim_over_billed",
                    "title_template": "Claim {target_ref} exceeds threshold",
                    "severity": "high",
                    "target_kind": "entity",
                    "target_selector": {"entity_type": "provider"},
                    "predicate": {
                        "field": "properties.amount",
                        "op": "gt",
                        "value": {"config_ref": "max_billed_amount"},
                    },
                    "citations": [],
                }
            ],
        }
    ]
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing spike",
            "description": "Provider billing volume increased beyond peer norms.",
            "entity_types": ["provider"],
            "severity_hint": "high",
            "feature_ids": ["weekly_provider_billing_zscore"],
            "policy_rule_ids": ["billing_thresholds.claim_over_billed"],
        }
    ]
    payload["feature_catalog"] = {
        "version": "cms-fraud-features-v1",
        "features": [
            {
                "id": "weekly_provider_billing_zscore",
                "label": "Weekly provider billing z-score",
                "description": "Peer-normalized weekly billed amount.",
                "value_type": "decimal",
                "entity_types": ["provider"],
                "source_mappings": [
                    {
                        "source_type": "derived_signal",
                        "source_ref": "entity_derived_signals.weekly_provider_billing",
                        "raw_fields": [
                            "billed_amount",
                            "service_date",
                            "provider_npi",
                        ],
                    }
                ],
                "peer_dimensions": ["provider"],
                "threshold_hints": {"high": 2.0, "critical": 3.0},
                "transformation_version": "peerstats-zscore-v1",
                "typology_ids": ["billing_spike"],
            }
        ],
    }

    config = DomainConfig.model_validate(payload)

    assert config.typologies[0].id == "billing_spike"
    assert config.feature_catalog.version == "cms-fraud-features-v1"
    assert config.feature_catalog.features[0].source_mappings[0].raw_fields == [
        "billed_amount",
        "service_date",
        "provider_npi",
    ]


def test_playbooks_and_typology_refs_round_trip() -> None:
    payload = _make_config(entities=[_minimal_entity("provider")]).model_dump(
        mode="json"
    )
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing Spike",
            "entity_types": ["provider"],
            "feature_ids": ["billing_outlier"],
            "policy_rule_ids": [],
            "playbook_ids": ["provider_billing_spike_review"],
        }
    ]
    payload["feature_catalog"] = {
        "version": "cms-features-v1",
        "features": [
            {
                "id": "billing_outlier",
                "label": "Billing outlier",
                "entity_types": ["provider"],
                "typology_ids": ["billing_spike"],
            }
        ],
    }
    payload["playbooks"] = {
        "version": "cms-playbooks-v1",
        "items": [
            {
                "id": "provider_billing_spike_review",
                "version": "v1",
                "title": "Provider billing spike review",
                "summary": "Review a provider whose billing pattern moved outside baseline.",
                "status": "draft",
                "typology_ids": ["billing_spike"],
                "feature_ids": ["billing_outlier"],
                "policy_rule_ids": [],
                "evidence_requirements": [
                    {
                        "id": "billing_trend",
                        "label": "Billing trend",
                        "description": (
                            "Compare current billing to historical and peer baselines."
                        ),
                        "source_types": ["risk_projection", "timeseries"],
                        "required": True,
                    }
                ],
                "workflow_steps": [
                    {
                        "id": "review_risk",
                        "label": "Review risk projection",
                        "capability_ref": "analytics.risk_projection.read",
                        "input_refs": ["entity_id", "knowledge_base_id"],
                        "output_refs": ["risk_summary"],
                        "requires_human_approval": False,
                    }
                ],
                "rag_prompts": [
                    {
                        "id": "billing_context",
                        "model_ref": "default",
                        "prompt_version": "v1",
                        "system_prompt": "Answer with cited evidence only.",
                        "user_prompt": (
                            "Summarize the billing spike evidence for {entity_id}."
                        ),
                    }
                ],
                "decision_guidance": [
                    "Open a case when billing spike evidence is corroborated."
                ],
                "export_tags": ["cms", "billing"],
            }
        ],
    }

    config = DomainConfig.model_validate(payload)

    assert config.playbooks.version == "cms-playbooks-v1"
    playbook = config.playbooks.items[0]
    assert playbook.id == "provider_billing_spike_review"
    assert playbook.evidence_requirements[0].source_types == [
        "risk_projection",
        "timeseries",
    ]
    assert config.typologies[0].playbook_ids == ["provider_billing_spike_review"]


def test_typology_rejects_unknown_playbook_reference() -> None:
    payload = _make_config(entities=[_minimal_entity("provider")]).model_dump(
        mode="json"
    )
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing Spike",
            "entity_types": ["provider"],
            "feature_ids": [],
            "policy_rule_ids": [],
            "playbook_ids": ["missing_playbook"],
        }
    ]

    with pytest.raises(ValidationError, match="unknown playbook_id 'missing_playbook'"):
        DomainConfig.model_validate(payload)


def test_playbook_rejects_unknown_references() -> None:
    payload = _make_config().model_dump(mode="json")
    payload["playbooks"] = {
        "version": "cms-playbooks-v1",
        "items": [
            {
                "id": "bad_review",
                "version": "v1",
                "title": "Bad Review",
                "summary": "Bad refs",
                "typology_ids": ["missing_typology"],
                "feature_ids": ["missing_feature"],
                "policy_rule_ids": ["missing_pack.missing_rule"],
                "evidence_requirements": [],
                "workflow_steps": [],
                "rag_prompts": [],
                "decision_guidance": [],
            }
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        DomainConfig.model_validate(payload)

    message = str(exc_info.value)
    assert (
        "Playbook 'bad_review' references unknown typology_id 'missing_typology'"
        in message
    )
    assert (
        "Playbook 'bad_review' references unknown feature_id 'missing_feature'"
        in message
    )
    assert (
        "Playbook 'bad_review' references unknown policy_rule_id "
        "'missing_pack.missing_rule'" in message
    )


@pytest.mark.parametrize(
    ("section_name", "duplicate_item"),
    [
        (
            "evidence_requirements",
            {
                "id": "duplicate",
                "label": "Evidence",
                "source_types": [],
            },
        ),
        (
            "workflow_steps",
            {
                "id": "duplicate",
                "label": "Workflow",
                "capability_ref": "analytics.read",
            },
        ),
        (
            "rag_prompts",
            {
                "id": "duplicate",
                "system_prompt": "Answer with cited evidence only.",
                "user_prompt": "Summarize {entity_id}.",
            },
        ),
    ],
)
def test_playbook_rejects_duplicate_nested_ids(
    section_name: str, duplicate_item: dict[str, object]
) -> None:
    payload = _make_config().model_dump(mode="json")
    playbook = {
        "id": "duplicate_nested_review",
        "version": "v1",
        "title": "Duplicate Nested Review",
        "typology_ids": [],
        "feature_ids": [],
        "policy_rule_ids": [],
        "evidence_requirements": [],
        "workflow_steps": [],
        "rag_prompts": [],
        "decision_guidance": [],
    }
    playbook[section_name] = [duplicate_item, duplicate_item]
    payload["playbooks"] = {
        "version": "cms-playbooks-v1",
        "items": [playbook],
    }

    with pytest.raises(
        ValidationError,
        match=(
            f"Playbook 'duplicate_nested_review' {section_name} ids must be unique"
        ),
    ):
        DomainConfig.model_validate(payload)


def test_playbook_catalog_rejects_duplicate_playbook_ids() -> None:
    payload = _make_config().model_dump(mode="json")
    base_playbook = {
        "id": "duplicate_review",
        "title": "Duplicate Review",
        "typology_ids": [],
        "feature_ids": [],
        "policy_rule_ids": [],
        "evidence_requirements": [],
        "workflow_steps": [],
        "rag_prompts": [],
        "decision_guidance": [],
    }
    payload["playbooks"] = {
        "version": "cms-playbooks-v1",
        "items": [
            {**base_playbook, "version": "v1"},
            {**base_playbook, "version": "v2"},
        ],
    }

    with pytest.raises(ValidationError, match="playbook ids must be unique"):
        DomainConfig.model_validate(payload)


def test_playbook_catalog_rejects_duplicate_playbook_versions() -> None:
    payload = _make_config().model_dump(mode="json")
    playbook = {
        "id": "duplicate_review",
        "version": "v1",
        "title": "Duplicate Review",
        "typology_ids": [],
        "feature_ids": [],
        "policy_rule_ids": [],
        "evidence_requirements": [],
        "workflow_steps": [],
        "rag_prompts": [],
        "decision_guidance": [],
    }
    payload["playbooks"] = {
        "version": "cms-playbooks-v1",
        "items": [playbook, playbook],
    }

    with pytest.raises(ValidationError, match="id/version pairs must be unique"):
        DomainConfig.model_validate(payload)


def test_typology_rejects_unknown_feature_reference() -> None:
    payload = _make_config().model_dump(mode="json")
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing spike",
            "description": "Provider billing volume increased beyond peer norms.",
            "entity_types": ["alpha"],
            "feature_ids": ["missing_feature"],
        }
    ]
    payload["feature_catalog"] = {"version": "v1", "features": []}

    with pytest.raises(
        ValidationError,
        match=(
            "Typology 'billing_spike' references unknown feature_id "
            "'missing_feature'"
        ),
    ):
        DomainConfig.model_validate(payload)


def test_feature_catalog_rejects_duplicate_feature_ids() -> None:
    payload = _make_config(entities=[_minimal_entity("provider")]).model_dump(
        mode="json"
    )
    feature = {
        "id": "weekly_provider_billing_zscore",
        "label": "Weekly provider billing z-score",
        "description": "Peer-normalized weekly billed amount.",
        "value_type": "decimal",
        "entity_types": ["provider"],
        "source_mappings": [
            {
                "source_type": "derived_signal",
                "source_ref": "entity_derived_signals.weekly_provider_billing",
                "raw_fields": ["billed_amount"],
            }
        ],
        "transformation_version": "peerstats-zscore-v1",
        "typology_ids": [],
    }
    payload["feature_catalog"] = {
        "version": "cms-fraud-features-v1",
        "features": [feature, feature],
    }

    with pytest.raises(ValidationError, match="feature ids must be unique"):
        DomainConfig.model_validate(payload)


def test_typologies_reject_duplicate_ids() -> None:
    payload = _make_config().model_dump(mode="json")
    typology = {
        "id": "billing_spike",
        "label": "Billing spike",
        "entity_types": ["alpha"],
        "feature_ids": [],
    }
    payload["typologies"] = [typology, typology]

    with pytest.raises(ValidationError, match="Typology ids must be unique"):
        DomainConfig.model_validate(payload)


def test_typology_rejects_unknown_policy_rule_reference() -> None:
    payload = _make_config().model_dump(mode="json")
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing spike",
            "entity_types": ["alpha"],
            "feature_ids": [],
            "policy_rule_ids": ["billing_thresholds.missing_rule"],
        }
    ]

    with pytest.raises(
        ValidationError,
        match=(
            "Typology 'billing_spike' references unknown policy_rule_id "
            "'billing_thresholds.missing_rule'"
        ),
    ):
        DomainConfig.model_validate(payload)


# ---------------------------------------------------------------------------
# Cross-field validation failures
# ---------------------------------------------------------------------------


class TestDomainConfigValidation:
    def test_duplicate_entity_names(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate entity name"):
            _make_config(entities=[_minimal_entity("x"), _minimal_entity("x")])

    def test_duplicate_relationship_names(self) -> None:
        ents = [_minimal_entity("a"), _minimal_entity("b")]
        dup_rel = RelationshipDefinition(
            name="link", display_label="Link", source="a", target="b"
        )
        with pytest.raises(ValidationError, match="Duplicate relationship name"):
            _make_config(entities=ents, relationships=[dup_rel, dup_rel])

    def test_relationship_bad_source(self) -> None:
        ents = [_minimal_entity("a")]
        rels = [
            RelationshipDefinition(
                name="r", display_label="R", source="missing", target="a"
            )
        ]
        with pytest.raises(ValidationError, match="source 'missing'"):
            _make_config(entities=ents, relationships=rels)

    def test_relationship_bad_target(self) -> None:
        ents = [_minimal_entity("a")]
        rels = [
            RelationshipDefinition(
                name="r", display_label="R", source="a", target="missing"
            )
        ]
        with pytest.raises(ValidationError, match="target 'missing'"):
            _make_config(entities=ents, relationships=rels)

    def test_enum_property_without_values(self) -> None:
        bad_entity = EntityDefinition(
            name="bad",
            display_label="Bad",
            icon="x",
            properties={
                "status": PropertyDefinition(
                    type=PropertyType.ENUM, display="Status"
                ),
            },
        )
        with pytest.raises(ValidationError, match="enum_values"):
            _make_config(entities=[bad_entity])

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            DomainConfig.model_validate({"domain": {"name": "x"}})

    def test_embeddings_and_vectorstore_dimensions_must_match_when_both_present(self) -> None:
        with pytest.raises(ValidationError, match="Embeddings dimensions"):
            _make_config(
                embeddings=EmbeddingsConfig(dimensions=768),
                vectorstore=VectorStoreConfig(dimensions=384),
            )

    def test_embeddings_dimensions_not_checked_when_vectorstore_absent(self) -> None:
        cfg = _make_config(embeddings=EmbeddingsConfig(dimensions=768))

        assert cfg.embeddings is not None
        assert cfg.embeddings.dimensions == 768
        assert cfg.vectorstore is not None
        assert cfg.vectorstore.dimensions == 384

    def test_duplicate_scorecard_metric_ids_across_template_sections_fail(self) -> None:
        data = _make_config().model_dump()
        data["scorecards"] = {
            "templates": [
                {
                    "id": "readiness",
                    "name": "Readiness",
                    "category": "combined",
                    "scope": "installation",
                    "period": "quarterly",
                    "sections": [
                        {
                            "id": "supply",
                            "label": "Supply",
                            "metrics": [
                                {
                                    "id": "duplicate_metric",
                                    "label": "Supply Metric",
                                    "inputs": [
                                        {
                                            "name": "value",
                                            "source": "metric",
                                            "ref": "source_metric",
                                        }
                                    ],
                                    "formula": {
                                        "operator": "latest",
                                        "value": "value",
                                    },
                                    "thresholds": {"pass_min": 1.0},
                                }
                            ],
                        },
                        {
                            "id": "condition",
                            "label": "Condition",
                            "metrics": [
                                {
                                    "id": "duplicate_metric",
                                    "label": "Condition Metric",
                                    "inputs": [
                                        {
                                            "name": "value",
                                            "source": "metric",
                                            "ref": "source_metric",
                                        }
                                    ],
                                    "formula": {
                                        "operator": "latest",
                                        "value": "value",
                                    },
                                    "thresholds": {"pass_min": 1.0},
                                }
                            ],
                        },
                    ],
                }
            ]
        }

        with pytest.raises(ValidationError, match="Duplicate scorecard metric id"):
            DomainConfig.model_validate(data)

    def test_scorecard_ratio_formula_requires_denominator(self) -> None:
        data = _config_data_with_scorecard_metric(
            _scorecard_metric_data(
                formula={"operator": "ratio", "numerator": "value"},
                inputs=[
                    {
                        "name": "value",
                        "source": "metric",
                        "ref": "source_metric",
                    }
                ],
            )
        )

        with pytest.raises(ValidationError, match="ratio"):
            DomainConfig.model_validate(data)

    @pytest.mark.parametrize("operator", ["sum", "mean", "latest"])
    def test_scorecard_value_formulas_require_value_input(self, operator: str) -> None:
        data = _config_data_with_scorecard_metric(
            _scorecard_metric_data(
                formula={"operator": operator, "numerator": "value"},
                inputs=[
                    {
                        "name": "value",
                        "source": "metric",
                        "ref": "source_metric",
                    }
                ],
            )
        )

        with pytest.raises(ValidationError, match=operator):
            DomainConfig.model_validate(data)

    def test_scorecard_weighted_mean_formula_requires_weight(self) -> None:
        data = _config_data_with_scorecard_metric(
            _scorecard_metric_data(
                formula={"operator": "weighted_mean", "value": "value"},
                inputs=[
                    {
                        "name": "value",
                        "source": "metric",
                        "ref": "source_metric",
                    }
                ],
            )
        )

        with pytest.raises(ValidationError, match="weighted_mean"):
            DomainConfig.model_validate(data)

    def test_scorecard_record_feed_input_requires_field(self) -> None:
        data = _config_data_with_record_feed_scorecard_input(
            {
                "name": "source",
                "source": "record_feed",
                "ref": "source_feed",
            }
        )

        with pytest.raises(ValidationError, match="requires field"):
            DomainConfig.model_validate(data)

    def test_scorecard_record_feed_input_rejects_unknown_field(self) -> None:
        data = _config_data_with_record_feed_scorecard_input(
            {
                "name": "source",
                "source": "record_feed",
                "ref": "source_feed",
                "field": "missing_score",
            }
        )

        with pytest.raises(ValidationError, match="unknown field"):
            DomainConfig.model_validate(data)


class TestChunkingConfig:
    def test_default_min_chunk_size_is_capped_for_small_chunk_sizes(self) -> None:
        config = ChunkingConfig(chunk_size=24, chunk_overlap=4)

        assert config.min_chunk_size == 24

    def test_chunk_overlap_must_be_smaller_than_chunk_size(self) -> None:
        with pytest.raises(ValidationError, match="chunk_overlap"):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)

    def test_min_chunk_size_must_not_exceed_chunk_size(self) -> None:
        with pytest.raises(ValidationError, match="min_chunk_size"):
            ChunkingConfig(chunk_size=100, min_chunk_size=101)


class TestGraphDbConfig:
    def test_defaults(self) -> None:
        config = GraphDbConfig()

        assert config.backend == "in_memory"
        assert config.uri is None
        assert config.pool_size == 10
        assert config.auth_env_var is None

    def test_accepts_external_backend_configuration(self) -> None:
        config = GraphDbConfig(
            backend="neo4j",
            uri="bolt://graph.example:7687",
            pool_size=15,
            auth_env_var="NEO4J_AUTH",
        )

        assert config.backend == "neo4j"
        assert config.uri == "bolt://graph.example:7687"
        assert config.pool_size == 15
        assert config.auth_env_var == "NEO4J_AUTH"

    def test_rejects_unimplemented_memgraph_backend(self) -> None:
        with pytest.raises(ValidationError):
            GraphDbConfig(backend="memgraph")  # type: ignore[arg-type]


class TestVectorStoreConfig:
    def test_defaults(self) -> None:
        config = VectorStoreConfig()

        assert config.backend == "in_memory"
        assert config.uri is None
        assert config.dimensions == 384
        assert config.distance_metric == "cosine"

    def test_accepts_external_backend_configuration(self) -> None:
        config = VectorStoreConfig(
            backend="qdrant",
            uri="http://qdrant.example:6333",
            dimensions=1024,
            distance_metric="euclidean",
        )

        assert config.backend == "qdrant"
        assert config.uri == "http://qdrant.example:6333"
        assert config.dimensions == 1024
        assert config.distance_metric == "euclidean"

    def test_rejects_unimplemented_pgvector_backend(self) -> None:
        with pytest.raises(ValidationError):
            VectorStoreConfig(backend="pgvector")  # type: ignore[arg-type]

    def test_dimensions_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="dimensions"):
            VectorStoreConfig(dimensions=0)


class TestLlmConfig:
    def test_defaults(self) -> None:
        config = LlmConfig()

        assert config.provider == "local"
        assert config.model == "local-default"
        assert config.api_key_env_var is None
        assert config.temperature == 0.7
        assert config.max_tokens == 4096


class TestEmbeddingsConfig:
    def test_defaults(self) -> None:
        config = EmbeddingsConfig()

        assert config.provider == "sentence_transformers"
        assert config.model == "all-MiniLM-L6-v2"
        assert config.dimensions == 384
        assert config.batch_size == 32
        assert config.api_key_env_var is None
        assert config.cache_enabled is True
        assert config.cache_max_entries == 4096

    def test_dimensions_and_batch_size_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="dimensions"):
            EmbeddingsConfig(dimensions=0)
        with pytest.raises(ValidationError, match="batch_size"):
            EmbeddingsConfig(batch_size=0)

    def test_cache_max_entries_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="cache_max_entries"):
            EmbeddingsConfig(cache_max_entries=0)


class TestObjectStoreConfig:
    def test_defaults(self) -> None:
        config = ObjectStoreConfig()

        assert config.backend == "local"
        assert config.endpoint_url is None
        assert config.bucket is None
        assert config.base_path is None
        assert config.credentials_env_var is None

    def test_accepts_s3_endpoint_configuration(self) -> None:
        config = ObjectStoreConfig(
            backend="minio",
            endpoint_url="http://minio:9000",
            bucket="chili-docs",
            base_path="knowledgebases",
            credentials_env_var="MINIO_CREDENTIALS",
        )

        assert config.backend == "minio"
        assert config.endpoint_url == "http://minio:9000"
        assert config.bucket == "chili-docs"
        assert config.base_path == "knowledgebases"
        assert config.credentials_env_var == "MINIO_CREDENTIALS"

    def test_rejects_unimplemented_gcs_backend(self) -> None:
        with pytest.raises(ValidationError):
            ObjectStoreConfig(backend="gcs")  # type: ignore[arg-type]


class TestEventBusConfig:
    def test_defaults(self) -> None:
        config = EventBusConfig()

        assert config.backend == "in_memory"
        assert config.uri is None
        assert config.stream_prefix == "chili"
        assert config.consumer_group == "chili-workers"
        assert config.stream_maxlen is None
        assert config.reclaim_min_idle_ms is None

    def test_accepts_redis_recovery_and_trim_settings(self) -> None:
        config = EventBusConfig(
            backend="redis",
            stream_maxlen=5000,
            reclaim_min_idle_ms=45_000,
        )

        assert config.stream_maxlen == 5000
        assert config.reclaim_min_idle_ms == 45_000


class TestMonitoringConfig:
    def test_defaults(self) -> None:
        config = MonitoringConfig()

        assert config.evaluation_interval_seconds == 300
        assert config.dedup_window_seconds == 3600
        assert config.max_alerts_per_entity == 10

    def test_severity_threshold_defaults(self) -> None:
        config = MonitoringConfig()

        assert config.medium_threshold == 0.6
        assert config.high_threshold == 0.85

    def test_high_threshold_must_exceed_medium(self) -> None:
        with pytest.raises(ValidationError):
            MonitoringConfig(medium_threshold=0.8, high_threshold=0.8)

    def test_severity_thresholds_must_be_in_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            MonitoringConfig(medium_threshold=-0.1, high_threshold=0.5)
        with pytest.raises(ValidationError):
            MonitoringConfig(medium_threshold=0.5, high_threshold=1.5)


class TestRagConfig:
    def test_defaults(self) -> None:
        config = RagConfig()

        assert config.top_k == 5
        assert config.expansion_depth == 2
        assert config.reranking_enabled is False
        assert config.system_prompt_template is None


# ---------------------------------------------------------------------------
# AuthConfig
# ---------------------------------------------------------------------------


class TestAuthConfig:
    def test_auth_config_extended_oidc_fields_default(self) -> None:
        cfg = AuthConfig()

        assert cfg.enabled is False
        assert cfg.client_id is None
        assert cfg.client_secret_env_var is None
        assert cfg.authorize_endpoint is None
        assert cfg.token_endpoint is None
        assert cfg.end_session_endpoint is None
        assert cfg.scopes == ["openid", "email", "profile"]
        assert cfg.cookie_secure is True
        assert cfg.cookie_domain is None
        assert cfg.session_ttl_seconds == 3600
        assert cfg.redirect_uri is None

    def test_auth_config_accepts_oidc_fields(self) -> None:
        cfg = AuthConfig(
            enabled=True,
            issuer_url="https://idp.example.com",
            audience="chili-api",
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
            client_id="chili-spa",
            client_secret_env_var="OIDC_CLIENT_SECRET",
            authorize_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/oauth/token",
            end_session_endpoint="https://idp.example.com/logout",
            scopes=["openid", "email", "profile", "offline_access"],
            cookie_secure=True,
            cookie_domain=".example.com",
            session_ttl_seconds=1800,
            redirect_uri="https://app.example.com/auth/callback",
        )

        assert cfg.enabled is True
        assert cfg.issuer_url == "https://idp.example.com"
        assert cfg.audience == "chili-api"
        assert cfg.jwks_uri == "https://idp.example.com/.well-known/jwks.json"
        assert cfg.client_id == "chili-spa"
        assert cfg.client_secret_env_var == "OIDC_CLIENT_SECRET"
        assert cfg.authorize_endpoint == "https://idp.example.com/authorize"
        assert cfg.token_endpoint == "https://idp.example.com/oauth/token"
        assert cfg.end_session_endpoint == "https://idp.example.com/logout"
        assert cfg.scopes == ["openid", "email", "profile", "offline_access"]
        assert cfg.cookie_secure is True
        assert cfg.cookie_domain == ".example.com"
        assert cfg.session_ttl_seconds == 1800
        assert cfg.redirect_uri == "https://app.example.com/auth/callback"

    def test_session_ttl_seconds_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            AuthConfig(session_ttl_seconds=0)


# ---------------------------------------------------------------------------
# Each PropertyType value
# ---------------------------------------------------------------------------


class TestPropertyTypeValues:
    @pytest.mark.parametrize(
        "ptype",
        [pt for pt in PropertyType],
        ids=[pt.value for pt in PropertyType],
    )
    def test_each_property_type_in_entity(self, ptype: PropertyType) -> None:
        if ptype is PropertyType.ENUM:
            prop = PropertyDefinition(
                type=ptype,
                display="Test",
                enum_values=["a", "b"],
            )
        else:
            prop = PropertyDefinition(type=ptype, display="Test")
        entity = EntityDefinition(
            name="test_entity",
            display_label="Test",
            icon="box",
            properties={"field": prop},
        )
        cfg = _make_config(entities=[entity])
        assert cfg.entities[0].properties["field"].type is ptype


# ---------------------------------------------------------------------------
# AnalyticsConfig
# ---------------------------------------------------------------------------


def test_analytics_config_defaults() -> None:
    config = AnalyticsConfig()
    assert config.metrics_recompute_min_interval_seconds == 300


def test_analytics_config_rejects_non_positive_interval() -> None:
    with pytest.raises(ValidationError):
        AnalyticsConfig(metrics_recompute_min_interval_seconds=0)


def test_analytics_config_risk_threshold_defaults() -> None:
    config = AnalyticsConfig()
    assert config.medium_risk_threshold == 0.5
    assert config.high_risk_threshold == 0.8


def test_analytics_config_high_risk_threshold_must_exceed_medium() -> None:
    with pytest.raises(ValidationError):
        AnalyticsConfig(medium_risk_threshold=0.7, high_risk_threshold=0.7)


def test_analytics_config_risk_thresholds_must_be_in_unit_interval() -> None:
    with pytest.raises(ValidationError):
        AnalyticsConfig(medium_risk_threshold=-0.1, high_risk_threshold=0.5)
    with pytest.raises(ValidationError):
        AnalyticsConfig(medium_risk_threshold=0.5, high_risk_threshold=1.5)


def test_domain_config_defaults_analytics_section() -> None:
    """A config that omits `analytics` gets the default AnalyticsConfig."""
    from pathlib import Path

    from config.loader import load_config

    config = load_config(
        Path(__file__).resolve().parents[2]
        / "config" / "defaults" / "medicare_fraud.yaml"
    )
    assert config.analytics is not None
    assert config.analytics.metrics_recompute_min_interval_seconds == 300


class TestAnalyticsExplainabilityBackends:
    def test_defaults_are_deterministic_and_none(self) -> None:
        config = AnalyticsConfig()
        assert config.narrative_backend == "deterministic"
        assert config.attribution_backend == "none"

    def test_accepts_llm_and_shap(self) -> None:
        config = AnalyticsConfig(narrative_backend="llm", attribution_backend="shap")
        assert config.narrative_backend == "llm"
        assert config.attribution_backend == "shap"

    def test_rejects_unknown_backends(self) -> None:
        with pytest.raises(ValidationError):
            AnalyticsConfig(narrative_backend="template")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            AnalyticsConfig(attribution_backend="lime")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# GnnConfig
# ---------------------------------------------------------------------------


def test_gnn_config_defaults() -> None:
    config = GnnConfig()
    assert config.snapshot_max_nodes == 5000


def test_gnn_config_rejects_non_positive_snapshot_max_nodes() -> None:
    with pytest.raises(ValidationError):
        GnnConfig(snapshot_max_nodes=0)
    with pytest.raises(ValidationError):
        GnnConfig(snapshot_max_nodes=-1)


def test_domain_config_defaults_gnn_section() -> None:
    """A config that omits `gnn` gets the default GnnConfig."""
    cfg = _make_config()
    assert cfg.gnn is not None
    assert cfg.gnn.snapshot_max_nodes == 5000


def test_domain_config_gnn_section_explicit_value_round_trips() -> None:
    """An explicitly configured `gnn` section survives dump/reload."""
    cfg = _make_config(gnn=GnnConfig(snapshot_max_nodes=1234))

    data = cfg.model_dump()
    restored = DomainConfig.model_validate(data)

    assert restored == cfg
    assert restored.gnn is not None
    assert restored.gnn.snapshot_max_nodes == 1234


# ---------------------------------------------------------------------------
# default_reference_kb_id
# ---------------------------------------------------------------------------


class TestDefaultReferenceKbId:
    def test_domain_config_default_reference_kb_id_is_none_by_default(self) -> None:
        cfg = _make_config()
        assert cfg.default_reference_kb_id is None

    def test_domain_config_default_reference_kb_id_accepts_string(self) -> None:
        cfg = _make_config(default_reference_kb_id="kb-policy-v1")
        assert cfg.default_reference_kb_id == "kb-policy-v1"


# ---------------------------------------------------------------------------
# TimeseriesMetricSpec and TimeseriesAnalyticsConfig
# ---------------------------------------------------------------------------


def test_timeseries_metric_spec_rejects_min_history_at_or_below_baseline() -> None:
    with pytest.raises(ValidationError):
        TimeseriesMetricSpec(
            name="m",
            record_type="claim_record",
            entity_type="provider",
            entity_id_field="npi",
            value_column="amount",
            aggregation="sum",
            interval="week",
            baseline_window=5,
            min_history=5,
        )


def test_domain_config_rejects_timeseries_spec_with_unknown_record_type() -> None:
    config = _make_config()
    payload = config.model_dump()
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "m",
                "record_type": "no_such_type",
                "entity_type": "provider",
                "entity_id_field": "npi",
                "value_column": "amount",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    with pytest.raises(ValidationError, match="no_such_type"):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_timeseries_value_column_missing_from_schema() -> None:
    config = _make_config()
    payload = config.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "claim_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {
                        "type": "string",
                        "display": "Claim ID",
                        "required": True,
                    },
                    "npi": {"type": "string", "display": "NPI"},
                },
            }
        ]
    }
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "amount_metric",
                "record_type": "claim_record",
                "entity_type": "alpha",
                "entity_id_field": "npi",
                "value_column": "not_a_column",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    with pytest.raises(ValidationError, match="not_a_column"):
        DomainConfig.model_validate(payload)


# Regression tests: Task 1 review flagged these four cross-reference
# validator branches (entity_id_field missing, value_column non-numeric,
# time_column missing, time_column non-date) as untested. The validator
# logic they exercise already existed and required no change here — these
# tests only close the coverage gap.


def test_domain_config_rejects_timeseries_entity_id_field_missing_from_schema() -> None:
    config = _make_config()
    payload = config.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "claim_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {
                        "type": "string",
                        "display": "Claim ID",
                        "required": True,
                    },
                    "amount": {"type": "decimal", "display": "Amount"},
                },
            }
        ]
    }
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "amount_metric",
                "record_type": "claim_record",
                "entity_type": "alpha",
                "entity_id_field": "not_a_field",
                "value_column": "amount",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    with pytest.raises(
        ValidationError, match="entity_id_field 'not_a_field' is not in record_schema"
    ):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_timeseries_value_column_non_numeric() -> None:
    config = _make_config()
    payload = config.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "claim_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {
                        "type": "string",
                        "display": "Claim ID",
                        "required": True,
                    },
                    "npi": {"type": "string", "display": "NPI"},
                },
            }
        ]
    }
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "amount_metric",
                "record_type": "claim_record",
                "entity_type": "alpha",
                "entity_id_field": "npi",
                "value_column": "npi",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    with pytest.raises(
        ValidationError,
        match=r"value_column 'npi' must be numeric \(integer or decimal\), got 'string'",
    ):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_timeseries_time_column_missing_from_schema() -> None:
    config = _make_config()
    payload = config.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "claim_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {
                        "type": "string",
                        "display": "Claim ID",
                        "required": True,
                    },
                    "npi": {"type": "string", "display": "NPI"},
                    "amount": {"type": "decimal", "display": "Amount"},
                },
            }
        ]
    }
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "amount_metric",
                "record_type": "claim_record",
                "entity_type": "alpha",
                "entity_id_field": "npi",
                "value_column": "amount",
                "time_column": "not_a_column",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    with pytest.raises(
        ValidationError, match="time_column 'not_a_column' is not in record_schema"
    ):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_timeseries_time_column_not_date_typed() -> None:
    config = _make_config()
    payload = config.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "claim_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {
                        "type": "string",
                        "display": "Claim ID",
                        "required": True,
                    },
                    "npi": {"type": "string", "display": "NPI"},
                    "amount": {"type": "decimal", "display": "Amount"},
                },
            }
        ]
    }
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "amount_metric",
                "record_type": "claim_record",
                "entity_type": "alpha",
                "entity_id_field": "npi",
                "value_column": "amount",
                "time_column": "npi",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    with pytest.raises(
        ValidationError,
        match="time_column 'npi' must be a date or datetime field, got 'string'",
    ):
        DomainConfig.model_validate(payload)


def test_domain_config_accepts_valid_timeseries_spec() -> None:
    config = _make_config()
    payload = config.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "claim_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {
                        "type": "string",
                        "display": "Claim ID",
                        "required": True,
                    },
                    "npi": {"type": "string", "display": "NPI"},
                    "amount": {"type": "decimal", "display": "Amount"},
                    "service_date": {"type": "date", "display": "Service Date"},
                },
            }
        ]
    }
    payload["timeseries"] = {
        "metrics": [
            {
                "name": "amount_metric",
                "record_type": "claim_record",
                "entity_type": "alpha",
                "entity_id_field": "npi",
                "value_column": "amount",
                "time_column": "service_date",
                "aggregation": "sum",
                "interval": "week",
            }
        ]
    }
    cfg = DomainConfig.model_validate(payload)
    assert cfg.timeseries is not None
    assert len(cfg.timeseries.metrics) == 1
    assert cfg.timeseries.metrics[0].detection_strategy == "z_score"


def _config_payload_with_peer_metric() -> dict[str, object]:
    config = _make_config(entities=[_minimal_entity("provider")])
    payload = config.model_dump()
    payload["records"] = {
        "feeds": [
            {
                "name": "claim_feed",
                "record_type": "claim_record",
                "source": "file_upload",
                "id_field": "claim_id",
                "record_schema": {
                    "claim_id": {
                        "type": "string",
                        "display": "Claim ID",
                        "required": True,
                    },
                    "npi": {"type": "string", "display": "NPI"},
                    "specialty": {"type": "string", "display": "Specialty"},
                    "amount": {"type": "decimal", "display": "Amount"},
                    "service_date": {"type": "date", "display": "Service Date"},
                },
            }
        ]
    }
    payload["peer_stats"] = {
        "metrics": [
            {
                "name": "weekly_billing",
                "record_type": "claim_record",
                "entity_type": "provider",
                "entity_id_field": "npi",
                "value_column": "amount",
                "time_column": "service_date",
                "aggregation": "sum",
                "interval": "week",
            }
        ],
        "cohorts": [
            {
                "id": "provider_specialty_billing",
                "label": "Provider specialty billing",
                "entity_type": "provider",
                "peer_metric": "weekly_billing",
                "group_by": ["specialty"],
                "version": "v1",
            }
        ],
    }
    return payload


def test_domain_config_accepts_valid_peer_cohort_definition() -> None:
    config = DomainConfig.model_validate(_config_payload_with_peer_metric())

    assert config.peer_stats is not None
    cohort = config.peer_stats.cohorts[0]
    assert cohort.id == "provider_specialty_billing"
    assert cohort.peer_metric == "weekly_billing"
    assert cohort.group_by == ["specialty"]


def test_domain_config_rejects_duplicate_peer_cohort_ids() -> None:
    payload = _config_payload_with_peer_metric()
    peer_stats = payload["peer_stats"]
    assert isinstance(peer_stats, dict)
    cohorts = peer_stats["cohorts"]
    assert isinstance(cohorts, list)
    peer_stats["cohorts"] = [cohorts[0], cohorts[0]]

    with pytest.raises(ValidationError, match="Duplicate peer cohort id"):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_peer_cohort_unknown_metric() -> None:
    payload = _config_payload_with_peer_metric()
    peer_stats = payload["peer_stats"]
    assert isinstance(peer_stats, dict)
    cohorts = peer_stats["cohorts"]
    assert isinstance(cohorts, list)
    cohort = cohorts[0]
    assert isinstance(cohort, dict)
    cohort["peer_metric"] = "missing_metric"

    with pytest.raises(ValidationError, match="unknown peer metric 'missing_metric'"):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_peer_cohort_entity_type_mismatch() -> None:
    payload = _config_payload_with_peer_metric()
    peer_stats = payload["peer_stats"]
    assert isinstance(peer_stats, dict)
    cohorts = peer_stats["cohorts"]
    assert isinstance(cohorts, list)
    cohort = cohorts[0]
    assert isinstance(cohort, dict)
    cohort["entity_type"] = "claim"

    with pytest.raises(ValidationError, match="entity_type 'claim' does not match"):
        DomainConfig.model_validate(payload)


def test_domain_config_rejects_peer_cohort_group_field_missing_from_schema() -> None:
    payload = _config_payload_with_peer_metric()
    peer_stats = payload["peer_stats"]
    assert isinstance(peer_stats, dict)
    cohorts = peer_stats["cohorts"]
    assert isinstance(cohorts, list)
    cohort = cohorts[0]
    assert isinstance(cohort, dict)
    cohort["group_by"] = ["missing_field"]

    with pytest.raises(
        ValidationError, match="group_by field 'missing_field' is not in record_schema"
    ):
        DomainConfig.model_validate(payload)


class TestRecordsAnalyticsTriggerConfig:
    def test_defaults_off(self) -> None:
        config = RecordsConfig()
        assert config.analytics_trigger.enabled is False
        assert config.analytics_trigger.max_entities_per_batch == 25
        assert config.analytics_trigger.min_interval_seconds == 600

    def test_rejects_nonpositive_cap(self) -> None:
        with pytest.raises(ValidationError):
            RecordsAnalyticsTriggerConfig(max_entities_per_batch=0)

    def test_rejects_nonpositive_interval(self) -> None:
        with pytest.raises(ValidationError):
            RecordsAnalyticsTriggerConfig(min_interval_seconds=0)


def test_validation_config_default_file_size_is_512_mb() -> None:
    """Spec 2026-07-26: buffered-path default raised 50 -> 512 MB.

    records.04 later re-scopes this to a Content-Length bound at 5120.
    """
    config = ValidationConfig()
    assert config.max_file_size_mb == 512
