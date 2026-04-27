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


@pytest.mark.parametrize(
    ("factory_name", "config_update", "message_fragment"),
    [
        (
            "get_object_store",
            {"storage": ObjectStoreConfig(backend="s3")},
            "Unsupported storage backend 's3'. Available backends: local.",
        ),
        (
            "get_graph_repository",
            {"graph": GraphDbConfig(backend="memgraph")},
            "Unsupported graph backend 'memgraph'. Available backends: in_memory, neo4j.",
        ),
        (
            "get_vector_store",
            {"vectorstore": VectorStoreConfig(backend="qdrant", dimensions=384)},
            "Unsupported vectorstore backend 'qdrant'. Available backends: in_memory.",
        ),
        (
            "get_embedder",
            {"embeddings": EmbeddingsConfig(provider="openai")},
            "Unsupported embeddings backend 'openai'. Available backends: local, sentence_transformers.",
        ),
        (
            "get_llm_client",
            {"llm": LlmConfig(provider="openai")},
            "Unsupported llm backend 'openai'. Available backends: local.",
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