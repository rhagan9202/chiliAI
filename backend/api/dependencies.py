"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

from functools import lru_cache
from typing import NoReturn, cast

from fastapi import Depends

from config.loader import load_config
from config.schema import DomainConfig, EmbeddingsConfig, EventBusConfig, GraphDbConfig, LlmConfig, MonitoringConfig, ObjectStoreConfig, VectorStoreConfig
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import create_embeddings_service
from events.protocols import EventBus
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository
from graph.protocols import GraphServiceProtocol
from graph.service import create_graph_service
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import ParserRegistry, create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.protocols import LlmClientProtocol
from llm.protocols import LlmServiceProtocol
from llm.service import create_llm_service
from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.adapters.protocols import ObservationSourceProtocol
from monitoring.protocols import MonitoringServiceProtocol
from monitoring.service import create_monitoring_service
from shared.exceptions import ConfigurationError
from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.protocols import VectorServiceProtocol
from vectorstore.service import create_vector_service

__all__ = [
    "get_embedder",
    "get_embeddings_service",
    "get_domain_config",
    "get_domain_config_payload",
    "get_event_bus",
    "get_event_bus_settings",
    "get_graph_repository",
    "get_graph_service",
    "get_ingestion_service",
    "get_llm_client",
    "get_llm_service",
    "get_monitoring_service",
    "get_monitoring_source",
    "get_object_store",
    "get_parser_orchestrator",
    "get_parser_registry",
    "get_remote_fetcher",
    "get_vector_store",
    "get_vectorstore_service",
]


def _raise_unsupported_backend(
    subsystem: str,
    backend: str,
    available_backends: tuple[str, ...],
) -> NoReturn:
    available = ", ".join(available_backends)
    raise ConfigurationError(
        f"Unsupported {subsystem} backend '{backend}'. Available backends: {available}."
    )


@lru_cache(maxsize=1)
def get_domain_config() -> DomainConfig:
    """Load and cache the domain configuration (singleton).

    The config is loaded once on first call and cached for the lifetime
    of the process.  To reload, restart the server.
    """
    return load_config()


def get_domain_config_payload(
    config: DomainConfig = Depends(get_domain_config),
) -> dict[str, object]:
    """Return the active domain configuration as a plain mapping."""
    return cast(dict[str, object], config.model_dump())


@lru_cache(maxsize=1)
def get_parser_registry() -> ParserRegistry:
    """Return the default parser registry."""
    return create_default_registry()


@lru_cache(maxsize=1)
def get_remote_fetcher() -> HttpxRemoteDocumentFetcher:
    """Return the default remote fetcher for HTTPS documents."""
    return HttpxRemoteDocumentFetcher()


@lru_cache(maxsize=1)
def get_parser_orchestrator() -> DocumentParsingOrchestrator:
    """Return the parser orchestrator assembled from default dependencies."""
    return DocumentParsingOrchestrator(
        get_parser_registry(),
        fetcher=get_remote_fetcher(),
    )


@lru_cache(maxsize=1)
def get_event_bus_settings() -> EventBusSettings:
    """Return the runtime event transport settings."""
    return load_event_bus_settings()


def _event_bus_section_is_explicit(config: DomainConfig) -> bool:
    return "events" in config.model_fields_set


def _resolve_event_bus_settings(config: DomainConfig) -> EventBusSettings:
    env_settings = get_event_bus_settings()
    if not _event_bus_section_is_explicit(config):
        return env_settings

    event_config = config.events
    if event_config is None or event_config == EventBusConfig():
        return env_settings

    return EventBusSettings(
        backend="redis" if event_config.backend == "redis" else "in-memory",
        redis_url=event_config.uri or env_settings.redis_url,
        stream_prefix=event_config.stream_prefix,
        consumer_group=event_config.consumer_group,
        consumer_name_prefix=env_settings.consumer_name_prefix,
        batch_size=env_settings.batch_size,
        block_ms=env_settings.block_ms,
    )


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    """Return the event bus implementation for API-triggered workflows."""
    config = get_domain_config()
    settings = _resolve_event_bus_settings(config)
    return create_event_bus(settings)


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    """Return the object store implementation for raw document content."""
    storage_config = get_domain_config().storage or ObjectStoreConfig()
    backend = storage_config.backend
    if backend == "local":
        return InMemoryObjectStore()
    _raise_unsupported_backend("storage", backend, ("local",))


@lru_cache(maxsize=1)
def get_graph_repository() -> GraphRepository:
    """Return the graph repository implementation selected by config."""
    graph_config = get_domain_config().graph or GraphDbConfig()
    backend = graph_config.backend
    if backend == "in_memory":
        return InMemoryGraphRepository()
    _raise_unsupported_backend("graph", backend, ("in_memory",))


@lru_cache(maxsize=1)
def get_graph_service() -> GraphServiceProtocol:
    """Return the graph service assembled from configured dependencies."""
    return create_graph_service(
        get_graph_repository(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
    )


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStoreProtocol:
    """Return the vector store adapter implementation selected by config."""
    vectorstore_config = get_domain_config().vectorstore or VectorStoreConfig()
    backend = vectorstore_config.backend
    if backend == "in_memory":
        return InMemoryVectorStore()
    _raise_unsupported_backend("vectorstore", backend, ("in_memory",))


@lru_cache(maxsize=1)
def get_vectorstore_service() -> VectorServiceProtocol:
    """Return the vectorstore service assembled from configured dependencies."""
    return create_vector_service(get_vector_store(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_embedder() -> EmbedderProtocol:
    """Return the embeddings adapter implementation selected by config."""
    embeddings_config = get_domain_config().embeddings or EmbeddingsConfig()
    provider = embeddings_config.provider
    if provider in {"local", "sentence_transformers"}:
        return InMemoryEmbedder(provider=provider)
    _raise_unsupported_backend("embeddings", provider, ("local", "sentence_transformers"))


@lru_cache(maxsize=1)
def get_embeddings_service() -> EmbeddingsServiceProtocol:
    """Return the embeddings service assembled from configured dependencies."""
    return create_embeddings_service(get_embedder(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClientProtocol:
    """Return the llm client implementation selected by config."""
    llm_config = get_domain_config().llm or LlmConfig()
    provider = llm_config.provider
    if provider == "local":
        return InMemoryLlmClient(provider=provider)
    _raise_unsupported_backend("llm", provider, ("local",))


@lru_cache(maxsize=1)
def get_llm_service() -> LlmServiceProtocol:
    """Return the llm service assembled from configured dependencies."""
    return create_llm_service(get_llm_client(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_monitoring_source() -> ObservationSourceProtocol:
    """Return the monitoring observation source selected by config."""
    _ = get_domain_config().monitoring or MonitoringConfig()
    return InMemoryObservationSource()


@lru_cache(maxsize=1)
def get_monitoring_service() -> MonitoringServiceProtocol:
    """Return the monitoring service assembled from configured dependencies."""
    return create_monitoring_service(get_monitoring_source(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    """Return the ingestion service used by API routes and tests."""
    return IngestionService(
        get_parser_orchestrator(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
    )
