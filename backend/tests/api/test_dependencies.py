"""Tests for API dependency factories and config-driven adapter selection."""

from __future__ import annotations

from pathlib import Path

import pytest

import api.dependencies as dependencies
from config.loader import load_config
from config.schema import (
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GraphDbConfig,
    LlmConfig,
    ObjectStoreConfig,
    VectorStoreConfig,
)
from embeddings.service import EmbeddingsService
from events.adapters.in_memory import InMemoryEventBus
from events.adapters.redis_streams import RedisStreamsEventBus
from graph.service import GraphService
from llm.service import LlmService
from monitoring.service import MonitoringService
from shared.exceptions import ConfigurationError
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
            {"graph": GraphDbConfig(backend="memgraph")},
            "Unsupported graph backend 'memgraph'. Available backends: in_memory, neo4j.",
        ),
        (
            "get_vector_store",
            {"vectorstore": VectorStoreConfig(backend="pgvector", dimensions=384)},
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
