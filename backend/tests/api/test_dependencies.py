"""Tests for API dependency factories and config-driven adapter selection."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

import api.dependencies as dependencies
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.adapters.postgres import PostgresAuditLogRepository
from auditlog.service import AuditLogService
from analytics.explainability.adapters.reviews_postgres import (
    PostgresExplanationReviewRepository,
)
from analytics.explainability.reviews import (
    ExplanationReviewService,
    InMemoryExplanationReviewRepository,
)
from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource
from config.loader import load_config
from config.schema import (
    DatabaseConfig,
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GnnConfig,
    GraphDbConfig,
    LlmConfig,
    MonitoringConfig,
    ObjectStoreConfig,
    VectorStoreConfig,
)
from embeddings.service import EmbeddingsService
from embeddings.service_models import EmbedRequest, EmbedSubmission
from events.adapters.in_memory import InMemoryEventBus
from events.adapters.redis_streams import RedisStreamsEventBus
from graph.service import GraphService
from ingestion.recovery import ObjectStoreIngestionRecoveryStore
from llm.service import LlmService
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter, InMemoryObservationSource
from monitoring.adapters.postgres import PostgresAlertHistoryStore, PostgresObservationSource
from monitoring.models import MonitoringBatch, MonitoringObservation
from monitoring.service import MonitoringService
from monitoring.service_models import MonitoringEvaluationRequest
from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.postgres import PostgresRawRecordStore
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.adapters.postgres import PostgresSourceDocumentStatusStore
from shared.exceptions import ConfigurationError
from shared.types import Entity
from storage.adapters.in_memory import InMemoryObjectStore
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from vectorstore.service import VectorService

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


@pytest.fixture(autouse=True)
def clear_dependency_caches() -> None:
    cacheable_factories = [
        dependencies.get_domain_config,
        dependencies.get_event_bus_settings,
        dependencies.get_event_bus,
        dependencies.get_object_store,
        dependencies.get_graph_repository,
        dependencies.get_graph_service,
        dependencies.get_vector_store,
        dependencies.get_vectorstore_service,
        dependencies.get_embedder,
        dependencies.get_embeddings_service,
        dependencies.get_llm_client,
        dependencies.get_llm_service,
        dependencies.get_monitoring_source,
        dependencies.get_monitoring_service,
        dependencies.get_ingestion_service,
        dependencies.get_session_store,
        dependencies.get_connection_provider,
        dependencies.get_raw_record_store,
        dependencies.get_document_status_store,
        dependencies.get_alert_feed_store,
        dependencies.get_knowledge_base_repository,
        dependencies.get_parser_registry,
        dependencies.get_remote_fetcher,
        dependencies.get_parser_orchestrator,
        dependencies.get_ingestion_recovery_store,
        dependencies.get_graph_snapshot_source,
        dependencies.get_gnn_service,
    ]
    for factory in cacheable_factories:
        factory.cache_clear()


@pytest.fixture()
def base_config() -> DomainConfig:
    return load_config(MEDICARE_YAML)


def _install_config(monkeypatch: pytest.MonkeyPatch, config: DomainConfig) -> None:
    monkeypatch.setattr(dependencies, "load_config", lambda: config)


def test_default_factories_return_in_memory_services(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    monkeypatch.delenv("CHILI_EVENT_BUS_BACKEND", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    _install_config(monkeypatch, base_config)

    assert isinstance(dependencies.get_object_store(), InMemoryObjectStore)
    assert isinstance(dependencies.get_event_bus(), InMemoryEventBus)
    assert isinstance(dependencies.get_graph_service(), GraphService)
    assert isinstance(dependencies.get_vectorstore_service(), VectorService)
    assert isinstance(dependencies.get_embeddings_service(), EmbeddingsService)
    assert isinstance(dependencies.get_llm_service(), LlmService)
    assert isinstance(dependencies.get_monitoring_service(), MonitoringService)


def test_factories_are_cached_for_same_config(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)

    assert dependencies.get_object_store() is dependencies.get_object_store()
    assert dependencies.get_graph_service() is dependencies.get_graph_service()
    assert dependencies.get_vectorstore_service() is dependencies.get_vectorstore_service()


def test_get_graph_snapshot_source_returns_repository_backed_source(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    """B1: the API-side factory mirrors the worker's repository-backed source."""
    _install_config(monkeypatch, base_config)

    repository = dependencies.get_graph_repository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e1", type="provider", properties={}),
            Entity(id="e2", type="provider", properties={}),
        ],
    )

    source = dependencies.get_graph_snapshot_source()

    assert isinstance(source, GraphRepositorySnapshotSource)
    snapshot = source.load_snapshot(knowledge_base_id="kb-1")
    assert {node.entity_id for node in snapshot.nodes} == {"e1", "e2"}


def test_get_graph_snapshot_source_is_cached_for_same_config(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)

    assert (
        dependencies.get_graph_snapshot_source()
        is dependencies.get_graph_snapshot_source()
    )


def test_get_graph_snapshot_source_honors_configured_snapshot_max_nodes(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(update={"gnn": GnnConfig(snapshot_max_nodes=1)})
    _install_config(monkeypatch, config)

    repository = dependencies.get_graph_repository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e1", type="provider", properties={}),
            Entity(id="e2", type="provider", properties={}),
        ],
    )

    snapshot = dependencies.get_graph_snapshot_source().load_snapshot(
        knowledge_base_id="kb-1"
    )
    assert len(snapshot.nodes) == 1


def test_monitoring_service_uses_configured_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "monitoring": MonitoringConfig(
                max_alerts_per_evaluation=1,
                dedup_window_seconds=120,
                grouping_window_seconds=60,
            )
        }
    )
    source = InMemoryObservationSource(
        batches=[
            MonitoringBatch(
                knowledge_base_id="kb-1",
                batch_id="batch-1",
                observations=[
                    MonitoringObservation(
                        entity_id="entity-1",
                        entity_type="provider",
                        metric_name="billing_intensity",
                        score=0.95,
                        rationale="High billing intensity.",
                    ),
                    MonitoringObservation(
                        entity_id="entity-2",
                        entity_type="provider",
                        metric_name="billing_intensity",
                        score=0.93,
                        rationale="High billing intensity.",
                    ),
                ],
            )
        ]
    )
    _install_config(monkeypatch, config)
    monkeypatch.setattr(dependencies, "get_monitoring_source", lambda: source)

    service = dependencies.get_monitoring_service()
    response = service.evaluate(
        MonitoringEvaluationRequest(knowledge_base_id="kb-1", batch_id="batch-1")
    )

    assert response.alert_count == 1
    assert response.rate_limited_count == 1


def test_event_bus_falls_back_to_environment_when_config_section_absent(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    monkeypatch.setenv("CHILI_EVENT_BUS_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/9")
    _install_config(monkeypatch, base_config)

    assert isinstance(dependencies.get_event_bus(), RedisStreamsEventBus)


def test_event_bus_uses_explicit_config_when_section_present(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "events": EventBusConfig(
                backend="redis",
                uri="redis://localhost:6379/5",
                stream_prefix="custom",
                consumer_group="custom-workers",
            )
        }
    )
    _install_config(monkeypatch, config)

    assert isinstance(dependencies.get_event_bus(), RedisStreamsEventBus)


def test_event_bus_explicit_config_carries_recovery_and_trim_settings(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "events": EventBusConfig(
                backend="redis",
                uri="redis://localhost:6379/5",
                stream_prefix="custom",
                consumer_group="custom-workers",
                stream_maxlen=5000,
                reclaim_min_idle_ms=45_000,
            )
        }
    )
    _install_config(monkeypatch, config)

    settings = dependencies.resolve_event_bus_settings(config)

    assert settings.stream_maxlen == 5000
    assert settings.reclaim_min_idle_ms == 45_000


def test_event_bus_explicit_config_preserves_env_recovery_and_trim_defaults(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "events": EventBusConfig(
                backend="redis",
                uri="redis://localhost:6379/5",
                stream_prefix="custom",
                consumer_group="custom-workers",
            )
        }
    )
    _install_config(monkeypatch, config)
    monkeypatch.setenv("CHILI_EVENT_STREAM_MAXLEN", "7500")
    monkeypatch.setenv("CHILI_EVENT_RECLAIM_MIN_IDLE_MS", "90_000")

    settings = dependencies.resolve_event_bus_settings(config)

    assert settings.stream_maxlen == 7500
    assert settings.reclaim_min_idle_ms == 90_000


def test_explicit_local_storage_uses_shared_filesystem_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "storage": ObjectStoreConfig(
                backend="local",
                base_path=str(tmp_path / "objects"),
            )
        }
    )
    _install_config(monkeypatch, config)

    object_store = dependencies.get_object_store()

    assert isinstance(object_store, LocalFsObjectStore)


def test_qdrant_vectorstore_config_selects_qdrant_adapter(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    import vectorstore.adapters.qdrant_adapter as qdrant_adapter

    class FakeQdrantVectorStore:
        def __init__(self, config: VectorStoreConfig) -> None:
            self.config = config

    monkeypatch.setattr(qdrant_adapter, "QdrantVectorStore", FakeQdrantVectorStore)
    config = base_config.model_copy(
        update={
            "vectorstore": VectorStoreConfig(
                backend="qdrant",
                uri="http://qdrant:6333",
                dimensions=384,
            )
        }
    )
    _install_config(monkeypatch, config)

    vector_store = dependencies.get_vector_store()

    assert isinstance(vector_store, FakeQdrantVectorStore)
    assert vector_store.config.backend == "qdrant"


@pytest.mark.parametrize("backend", ["s3", "minio"])
def test_s3_compatible_storage_config_selects_s3_adapter(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
    backend: str,
) -> None:
    import storage.adapters.s3_adapter as s3_adapter

    class FakeS3ObjectStore:
        def __init__(self, config: ObjectStoreConfig) -> None:
            self.config = config

    monkeypatch.setattr(s3_adapter, "S3ObjectStore", FakeS3ObjectStore)
    config = base_config.model_copy(
        update={
            "storage": ObjectStoreConfig(
                backend=backend,  # type: ignore[arg-type]
                bucket="chili-objects",
                base_path="tenants/default",
            )
        }
    )
    _install_config(monkeypatch, config)

    object_store = dependencies.get_object_store()

    assert isinstance(object_store, FakeS3ObjectStore)
    assert object_store.config.backend == backend


@pytest.mark.parametrize("provider", ["openai", "sentence_transformers"])
def test_embeddings_config_selects_configured_provider_adapter(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
    provider: str,
) -> None:
    import embeddings.adapters.openai_adapter as openai_adapter
    import embeddings.adapters.sentence_transformers_adapter as sentence_adapter

    class FakeOpenAIEmbedder:
        def __init__(self, config: EmbeddingsConfig) -> None:
            self.config = config

    class FakeSentenceTransformersEmbedder:
        def __init__(self, config: EmbeddingsConfig) -> None:
            self.config = config

    monkeypatch.setattr(openai_adapter, "OpenAIEmbedder", FakeOpenAIEmbedder)
    monkeypatch.setattr(
        sentence_adapter,
        "SentenceTransformersEmbedder",
        FakeSentenceTransformersEmbedder,
    )
    config = base_config.model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider=provider,  # type: ignore[arg-type]
                model="configured-model",
                dimensions=384,
                api_key_env_var="OPENAI_API_KEY" if provider == "openai" else None,
            )
        }
    )
    _install_config(monkeypatch, config)

    embedder = dependencies.get_embedder()

    expected_type = (
        FakeOpenAIEmbedder
        if provider == "openai"
        else FakeSentenceTransformersEmbedder
    )
    assert isinstance(embedder, expected_type)
    assert embedder.config.provider == provider


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_llm_config_selects_configured_provider_adapter(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
    provider: str,
) -> None:
    import llm.adapters.anthropic_adapter as anthropic_adapter
    import llm.adapters.openai_adapter as openai_adapter

    class FakeOpenAILlmClient:
        def __init__(self, config: LlmConfig) -> None:
            self.config = config

    class FakeAnthropicLlmClient:
        def __init__(self, config: LlmConfig) -> None:
            self.config = config

    monkeypatch.setattr(openai_adapter, "OpenAILlmClient", FakeOpenAILlmClient)
    monkeypatch.setattr(anthropic_adapter, "AnthropicLlmClient", FakeAnthropicLlmClient)
    config = base_config.model_copy(
        update={
            "llm": LlmConfig(
                provider=provider,  # type: ignore[arg-type]
                model="configured-model",
                api_key_env_var="LLM_API_KEY",
            )
        }
    )
    _install_config(monkeypatch, config)

    llm_client = dependencies.get_llm_client()

    expected_type = FakeOpenAILlmClient if provider == "openai" else FakeAnthropicLlmClient
    assert isinstance(llm_client, expected_type)
    assert llm_client.config.provider == provider


@pytest.mark.parametrize(
    ("factory_name", "config_update", "message_fragment"),
    [
        (
            "get_graph_repository",
            {"graph": GraphDbConfig.model_construct(backend="memgraph")},
            "Unsupported graph backend 'memgraph'. Available backends: in_memory, neo4j.",
        ),
        (
            "get_vector_store",
            {"vectorstore": VectorStoreConfig.model_construct(backend="pgvector", dimensions=384)},
            "Unsupported vectorstore backend 'pgvector'. Available backends: in_memory, qdrant.",
        ),
    ],
)
def test_unsupported_backends_raise_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
    factory_name: str,
    config_update: dict[str, object],
    message_fragment: str,
) -> None:
    config = base_config.model_copy(update=config_update)
    _install_config(monkeypatch, config)

    factory = getattr(dependencies, factory_name)
    with pytest.raises(ConfigurationError, match=message_fragment):
        factory()


def test_get_session_store_returns_in_memory_when_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from api.middleware.session_store import InMemorySessionStore

    _install_config(monkeypatch, base_config)

    store = dependencies.get_session_store()

    assert isinstance(store, InMemorySessionStore)


def test_get_session_store_returns_redis_when_auth_enabled_and_redis_configured(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from api.middleware.session_store import RedisSessionStore
    from config.schema import AuthConfig

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    config = base_config.model_copy(
        update={"auth": AuthConfig(enabled=True)}
    )
    _install_config(monkeypatch, config)

    store = dependencies.get_session_store()

    assert isinstance(store, RedisSessionStore)


def test_get_session_store_raises_when_auth_enabled_and_redis_url_missing(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from config.schema import AuthConfig

    monkeypatch.delenv("REDIS_URL", raising=False)
    config = base_config.model_copy(
        update={"auth": AuthConfig(enabled=True)}
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="REDIS_URL"):
        dependencies.get_session_store()


# ---------------------------------------------------------------------------
# get_parser_registry / get_remote_fetcher / get_parser_orchestrator
# These are lru_cache'd factories whose bodies were not exercised by any prior
# test (they are only reachable via get_ingestion_service paths).
# ---------------------------------------------------------------------------


def test_get_parser_registry_returns_a_registry(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from ingestion.parsers.registry import ParserRegistry

    _install_config(monkeypatch, base_config)

    registry = dependencies.get_parser_registry()

    assert isinstance(registry, ParserRegistry)


def test_get_remote_fetcher_returns_a_fetcher(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from ingestion.parsers.remote import HttpxRemoteDocumentFetcher

    _install_config(monkeypatch, base_config)

    fetcher = dependencies.get_remote_fetcher()

    assert isinstance(fetcher, HttpxRemoteDocumentFetcher)


def test_get_parser_orchestrator_returns_an_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from ingestion.orchestrators.parser import DocumentParsingOrchestrator

    _install_config(monkeypatch, base_config)

    orchestrator = dependencies.get_parser_orchestrator()

    assert isinstance(orchestrator, DocumentParsingOrchestrator)


def test_get_ingestion_service_returns_an_ingestion_service(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from ingestion.service import IngestionService

    _install_config(monkeypatch, base_config)

    service = dependencies.get_ingestion_service()

    assert isinstance(service, IngestionService)


def test_get_ingestion_service_wires_recovery_store(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)

    service = dependencies.get_ingestion_service()

    assert isinstance(service._recovery_store, ObjectStoreIngestionRecoveryStore)  # pyright: ignore[reportPrivateUsage]
    assert service._recovery_store._object_store is dependencies.get_object_store()  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# resolve_event_bus_settings: explicit EventBusConfig section with defaults
# ---------------------------------------------------------------------------


def test_event_bus_falls_back_to_env_when_explicit_section_equals_defaults(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    # model_copy with an EventBusConfig() that equals the default triggers the
    # ``event_config == EventBusConfig()`` branch on line 383.
    config = base_config.model_copy(update={"events": EventBusConfig()})
    _install_config(monkeypatch, base_config)
    monkeypatch.delenv("CHILI_EVENT_BUS_BACKEND", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    # We need load_config to return the config WITH the events section set
    # so _event_bus_section_is_explicit returns True.
    monkeypatch.setattr(dependencies, "load_config", lambda: config)

    bus = dependencies.get_event_bus()

    assert isinstance(bus, InMemoryEventBus)


# ---------------------------------------------------------------------------
# get_object_store: s3/minio ImportError wrapping
# ---------------------------------------------------------------------------


def test_s3_storage_import_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"storage": ObjectStoreConfig.model_construct(backend="s3")}
    )
    _install_config(monkeypatch, config)

    sentinel = sys.modules.get("storage.adapters.s3_adapter")
    try:
        sys.modules["storage.adapters.s3_adapter"] = None  # type: ignore[assignment]
        with pytest.raises(ConfigurationError):
            dependencies.get_object_store()
    finally:
        if sentinel is None:
            sys.modules.pop("storage.adapters.s3_adapter", None)
        else:
            sys.modules["storage.adapters.s3_adapter"] = sentinel


def test_s3_storage_constructor_value_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    import storage.adapters.s3_adapter as s3_adapter

    def _raising_constructor(config: ObjectStoreConfig) -> None:
        raise ValueError("missing bucket")

    monkeypatch.setattr(s3_adapter, "S3ObjectStore", _raising_constructor)
    config = base_config.model_copy(
        update={"storage": ObjectStoreConfig.model_construct(backend="s3")}
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="missing bucket"):
        dependencies.get_object_store()


def test_unsupported_storage_backend_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"storage": ObjectStoreConfig.model_construct(backend="gcs")}
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="gcs"):
        dependencies.get_object_store()


# ---------------------------------------------------------------------------
# get_graph_repository: neo4j ImportError and ValueError wrapping
# ---------------------------------------------------------------------------


def test_neo4j_import_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"graph": GraphDbConfig.model_construct(backend="neo4j")}
    )
    _install_config(monkeypatch, config)

    sentinel = sys.modules.get("graph.adapters.neo4j_adapter")
    try:
        sys.modules["graph.adapters.neo4j_adapter"] = None  # type: ignore[assignment]
        with pytest.raises(ConfigurationError):
            dependencies.get_graph_repository()
    finally:
        if sentinel is None:
            sys.modules.pop("graph.adapters.neo4j_adapter", None)
        else:
            sys.modules["graph.adapters.neo4j_adapter"] = sentinel


def test_neo4j_constructor_value_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    import graph.adapters.neo4j_adapter as neo4j_adapter

    class _RaisingNeo4jRepository:
        def __init__(self, config: GraphDbConfig, **kwargs: object) -> None:
            raise ValueError("invalid neo4j URI")

    monkeypatch.setattr(neo4j_adapter, "Neo4jGraphRepository", _RaisingNeo4jRepository)
    config = base_config.model_copy(
        update={"graph": GraphDbConfig.model_construct(backend="neo4j")}
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="invalid neo4j URI"):
        dependencies.get_graph_repository()


# ---------------------------------------------------------------------------
# get_vector_store: qdrant ImportError and ValueError wrapping
# ---------------------------------------------------------------------------


def test_qdrant_import_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"vectorstore": VectorStoreConfig.model_construct(backend="qdrant", dimensions=384)}
    )
    _install_config(monkeypatch, config)

    sentinel = sys.modules.get("vectorstore.adapters.qdrant_adapter")
    try:
        sys.modules["vectorstore.adapters.qdrant_adapter"] = None  # type: ignore[assignment]
        with pytest.raises(ConfigurationError):
            dependencies.get_vector_store()
    finally:
        if sentinel is None:
            sys.modules.pop("vectorstore.adapters.qdrant_adapter", None)
        else:
            sys.modules["vectorstore.adapters.qdrant_adapter"] = sentinel


def test_qdrant_constructor_value_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    import vectorstore.adapters.qdrant_adapter as qdrant_adapter

    def _raising_constructor(config: VectorStoreConfig) -> None:
        raise ValueError("cannot connect to qdrant")

    monkeypatch.setattr(qdrant_adapter, "QdrantVectorStore", _raising_constructor)
    config = base_config.model_copy(
        update={"vectorstore": VectorStoreConfig.model_construct(backend="qdrant", dimensions=384)}
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="cannot connect to qdrant"):
        dependencies.get_vector_store()


# ---------------------------------------------------------------------------
# get_embedder: unsupported provider path
# ---------------------------------------------------------------------------


def test_unsupported_embeddings_provider_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"embeddings": EmbeddingsConfig.model_construct(provider="cohere", dimensions=384)}
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="cohere"):
        dependencies.get_embedder()


def test_sentence_transformers_import_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    # Use a non-default model name so the config does NOT equal EmbeddingsConfig()
    # and the sentence_transformers adapter branch is reached.
    config = base_config.model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="sentence_transformers",  # type: ignore[arg-type]
                model="paraphrase-MiniLM-L3-v2",  # differs from default "all-MiniLM-L6-v2"
                dimensions=384,
            )
        }
    )
    _install_config(monkeypatch, config)

    sentinel = sys.modules.get("embeddings.adapters.sentence_transformers_adapter")
    try:
        sys.modules["embeddings.adapters.sentence_transformers_adapter"] = None  # type: ignore[assignment]
        with pytest.raises(ConfigurationError):
            dependencies.get_embedder()
    finally:
        if sentinel is None:
            sys.modules.pop("embeddings.adapters.sentence_transformers_adapter", None)
        else:
            sys.modules["embeddings.adapters.sentence_transformers_adapter"] = sentinel


def test_sentence_transformers_constructor_value_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    import embeddings.adapters.sentence_transformers_adapter as st_adapter

    def _raising_constructor(config: EmbeddingsConfig) -> None:
        raise ValueError("model not found")

    monkeypatch.setattr(st_adapter, "SentenceTransformersEmbedder", _raising_constructor)
    # Use a non-default model name so the config differs from EmbeddingsConfig()
    # and the sentence_transformers adapter branch is actually entered.
    config = base_config.model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="sentence_transformers",  # type: ignore[arg-type]
                model="paraphrase-MiniLM-L3-v2",
                dimensions=384,
            )
        }
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="model not found"):
        dependencies.get_embedder()


def test_openai_embedder_import_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="openai",  # type: ignore[arg-type]
                model="text-embedding-ada-002",
                dimensions=1536,
                api_key_env_var="OPENAI_API_KEY",
            )
        }
    )
    _install_config(monkeypatch, config)

    sentinel = sys.modules.get("embeddings.adapters.openai_adapter")
    try:
        sys.modules["embeddings.adapters.openai_adapter"] = None  # type: ignore[assignment]
        with pytest.raises(ConfigurationError):
            dependencies.get_embedder()
    finally:
        if sentinel is None:
            sys.modules.pop("embeddings.adapters.openai_adapter", None)
        else:
            sys.modules["embeddings.adapters.openai_adapter"] = sentinel


# ---------------------------------------------------------------------------
# get_llm_client: unsupported provider and ImportError wrapping
# ---------------------------------------------------------------------------


def test_unsupported_llm_provider_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"llm": LlmConfig.model_construct(provider="gemini")}
    )
    _install_config(monkeypatch, config)

    with pytest.raises(ConfigurationError, match="gemini"):
        dependencies.get_llm_client()


def test_openai_llm_import_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "llm": LlmConfig(
                provider="openai",  # type: ignore[arg-type]
                model="gpt-4o",
                api_key_env_var="OPENAI_API_KEY",
            )
        }
    )
    _install_config(monkeypatch, config)

    sentinel = sys.modules.get("llm.adapters.openai_adapter")
    try:
        sys.modules["llm.adapters.openai_adapter"] = None  # type: ignore[assignment]
        with pytest.raises(ConfigurationError):
            dependencies.get_llm_client()
    finally:
        if sentinel is None:
            sys.modules.pop("llm.adapters.openai_adapter", None)
        else:
            sys.modules["llm.adapters.openai_adapter"] = sentinel


def test_anthropic_llm_import_error_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "llm": LlmConfig(
                provider="anthropic",  # type: ignore[arg-type]
                model="claude-3-5-sonnet-20241022",
                api_key_env_var="ANTHROPIC_API_KEY",
            )
        }
    )
    _install_config(monkeypatch, config)

    sentinel = sys.modules.get("llm.adapters.anthropic_adapter")
    try:
        sys.modules["llm.adapters.anthropic_adapter"] = None  # type: ignore[assignment]
        with pytest.raises(ConfigurationError):
            dependencies.get_llm_client()
    finally:
        if sentinel is None:
            sys.modules.pop("llm.adapters.anthropic_adapter", None)
        else:
            sys.modules["llm.adapters.anthropic_adapter"] = sentinel


# ---------------------------------------------------------------------------
# get_monitoring_source: postgres path when connection provider is non-None
# ---------------------------------------------------------------------------


def test_get_monitoring_source_uses_postgres_when_provider_is_non_null(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    fake_provider = MagicMock()
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: fake_provider)

    source = dependencies.get_monitoring_source()

    assert isinstance(source, PostgresObservationSource)


# ---------------------------------------------------------------------------
# get_connection_provider / get_raw_record_store: postgres path
# ---------------------------------------------------------------------------


def test_get_connection_provider_returns_none_for_in_memory_backend(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"database": DatabaseConfig(backend="in_memory")}
    )
    _install_config(monkeypatch, config)

    provider = dependencies.get_connection_provider()

    assert provider is None


def test_get_raw_record_store_returns_postgres_store_when_provider_non_null(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    fake_provider = MagicMock()
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: fake_provider)

    store = dependencies.get_raw_record_store()

    assert isinstance(store, PostgresRawRecordStore)


def test_get_raw_record_store_returns_in_memory_when_provider_is_none(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: None)

    store = dependencies.get_raw_record_store()

    assert isinstance(store, InMemoryRawRecordStore)


def test_get_document_status_store_returns_postgres_store_when_provider_non_null(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    fake_provider = MagicMock()
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: fake_provider)

    store = dependencies.get_document_status_store()

    assert isinstance(store, PostgresSourceDocumentStatusStore)


def test_get_document_status_store_returns_in_memory_when_provider_is_none(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: None)

    store = dependencies.get_document_status_store()

    assert isinstance(store, InMemorySourceDocumentStatusStore)


def test_get_audit_log_service_uses_postgres_when_provider_non_null(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    fake_provider = MagicMock()
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: fake_provider)
    request = MagicMock()
    request.app = FastAPI()

    service = dependencies.get_audit_log_service(request)

    assert isinstance(service, AuditLogService)
    assert isinstance(service._repository, PostgresAuditLogRepository)


def test_get_audit_log_service_returns_in_memory_when_provider_is_none(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: None)
    request = MagicMock()
    request.app = FastAPI()

    service = dependencies.get_audit_log_service(request)

    assert isinstance(service, AuditLogService)
    assert isinstance(service._repository, InMemoryAuditLogRepository)


def test_get_explanation_review_service_uses_postgres_when_provider_non_null(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    fake_provider = MagicMock()
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: fake_provider)
    request = MagicMock()
    request.app = FastAPI()

    service = dependencies.get_explanation_review_service(request)

    assert isinstance(service, ExplanationReviewService)
    assert isinstance(service._repository, PostgresExplanationReviewRepository)


def test_get_explanation_review_service_returns_in_memory_when_provider_is_none(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: None)
    request = MagicMock()
    request.app = FastAPI()

    service = dependencies.get_explanation_review_service(request)

    assert isinstance(service, ExplanationReviewService)
    assert isinstance(service._repository, InMemoryExplanationReviewRepository)


# ---------------------------------------------------------------------------
# get_knowledge_base_repository: object_store branch and unsupported backend
# ---------------------------------------------------------------------------


def test_get_knowledge_base_repository_returns_object_store_repo(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository

    monkeypatch.setenv("CHILI_KB_REPOSITORY_BACKEND", "object_store")
    _install_config(monkeypatch, base_config)

    repo = dependencies.get_knowledge_base_repository()

    assert isinstance(repo, ObjectStoreKnowledgeBaseRepository)


@pytest.mark.parametrize("alias", ["object_store", "object-store", "objectstore"])
def test_get_knowledge_base_repository_accepts_all_object_store_aliases(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
    alias: str,
) -> None:
    from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository

    monkeypatch.setenv("CHILI_KB_REPOSITORY_BACKEND", alias)
    _install_config(monkeypatch, base_config)

    repo = dependencies.get_knowledge_base_repository()

    assert isinstance(repo, ObjectStoreKnowledgeBaseRepository)


def test_get_knowledge_base_repository_unsupported_backend_raises(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    monkeypatch.setenv("CHILI_KB_REPOSITORY_BACKEND", "postgres")
    _install_config(monkeypatch, base_config)

    with pytest.raises(ConfigurationError, match="postgres"):
        dependencies.get_knowledge_base_repository()


# ---------------------------------------------------------------------------
# get_alert_feed_store: Postgres vs. in-memory backend selection (alerts.36)
# ---------------------------------------------------------------------------


def test_get_alert_feed_store_returns_postgres_store_when_provider_non_null(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    fake_provider = MagicMock()
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: fake_provider)

    store = dependencies.get_alert_feed_store()

    assert isinstance(store, PostgresAlertHistoryStore)


def test_get_alert_feed_store_returns_in_memory_when_provider_is_none(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    _install_config(monkeypatch, base_config)
    monkeypatch.setattr(dependencies, "get_connection_provider", lambda: None)

    store = dependencies.get_alert_feed_store()

    assert isinstance(store, InMemoryAlertHistoryWriter)


def test_get_embeddings_service_uses_config_driven_cache(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={"embeddings": EmbeddingsConfig(provider="local", model="di-probe")}
    )
    _install_config(monkeypatch, config)
    service = dependencies.get_embeddings_service()
    request = EmbedRequest(
        model_name="di-cache-model",
        submissions=[EmbedSubmission(content_id="content-1", content="DI probe")],
    )
    hit_labels = {
        "provider": "local",
        "model": "di-cache-model",
        "cache_result": "hit",
    }
    before = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0

    service.embed(request)
    service.embed(request)

    after = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0
    assert after - before == 1.0


def test_get_embeddings_service_honors_cache_disabled(
    monkeypatch: pytest.MonkeyPatch,
    base_config: DomainConfig,
) -> None:
    config = base_config.model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="local", model="di-probe", cache_enabled=False
            )
        }
    )
    _install_config(monkeypatch, config)
    service = dependencies.get_embeddings_service()
    request = EmbedRequest(
        model_name="di-nocache-model",
        submissions=[EmbedSubmission(content_id="content-1", content="DI probe")],
    )
    miss_labels = {
        "provider": "local",
        "model": "di-nocache-model",
        "cache_result": "miss",
    }
    hit_labels = {**miss_labels, "cache_result": "hit"}
    misses_before = (
        REGISTRY.get_sample_value("embedding_texts_total", miss_labels) or 0.0
    )
    hits_before = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0

    service.embed(request)
    service.embed(request)

    misses_after = (
        REGISTRY.get_sample_value("embedding_texts_total", miss_labels) or 0.0
    )
    hits_after = REGISTRY.get_sample_value("embedding_texts_total", hit_labels) or 0.0
    assert misses_after - misses_before == 2.0
    assert hits_after - hits_before == 0.0
