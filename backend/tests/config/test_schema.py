"""Tests for config.schema — DomainConfig validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import (
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    ChunkingConfig,
    DomainConfig,
    DomainInfo,
    EmbeddingsConfig,
    EventBusConfig,
    GraphDbConfig,
    IngestionConfig,
    IngestionSourceConfig,
    LlmConfig,
    MonitoringConfig,
    ObjectStoreConfig,
    RagConfig,
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
    schema_version: str = "1.0",
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
        alerts=AlertsConfig(thresholds={}),
    )


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
            backend="memgraph",
            uri="bolt://graph.example:7687",
            pool_size=15,
            auth_env_var="MEMGRAPH_AUTH",
        )

        assert config.backend == "memgraph"
        assert config.uri == "bolt://graph.example:7687"
        assert config.pool_size == 15
        assert config.auth_env_var == "MEMGRAPH_AUTH"


class TestVectorStoreConfig:
    def test_defaults(self) -> None:
        config = VectorStoreConfig()

        assert config.backend == "in_memory"
        assert config.uri is None
        assert config.dimensions == 384
        assert config.distance_metric == "cosine"

    def test_accepts_external_backend_configuration(self) -> None:
        config = VectorStoreConfig(
            backend="pgvector",
            uri="postgresql://vector.example/db",
            dimensions=1024,
            distance_metric="euclidean",
        )

        assert config.backend == "pgvector"
        assert config.uri == "postgresql://vector.example/db"
        assert config.dimensions == 1024
        assert config.distance_metric == "euclidean"

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

    def test_dimensions_and_batch_size_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="dimensions"):
            EmbeddingsConfig(dimensions=0)
        with pytest.raises(ValidationError, match="batch_size"):
            EmbeddingsConfig(batch_size=0)


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


class TestEventBusConfig:
    def test_defaults(self) -> None:
        config = EventBusConfig()

        assert config.backend == "in_memory"
        assert config.uri is None
        assert config.stream_prefix == "chili"
        assert config.consumer_group == "chili-workers"


class TestMonitoringConfig:
    def test_defaults(self) -> None:
        config = MonitoringConfig()

        assert config.evaluation_interval_seconds == 300
        assert config.dedup_window_seconds == 3600
        assert config.max_alerts_per_entity == 10


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
