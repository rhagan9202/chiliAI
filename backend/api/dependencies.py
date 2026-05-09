"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

from functools import lru_cache
from typing import cast

from fastapi import Depends

from config.loader import load_config
from config.schema import DomainConfig
from events.protocols import EventBus
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import ParserRegistry, create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore

__all__ = [
    "get_domain_config",
    "get_domain_config_features_payload",
    "get_domain_config_payload",
    "get_domain_config_schema_payload",
    "get_event_bus",
    "get_event_bus_settings",
    "get_ingestion_service",
    "get_object_store",
    "get_parser_orchestrator",
    "get_parser_registry",
    "get_remote_fetcher",
]


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


def get_domain_config_features_payload(
    config: DomainConfig = Depends(get_domain_config),
) -> dict[str, object]:
    """Return frontend-oriented feature flags derived from the domain config."""
    enabled_pages = [
        page.id
        for page in (config.ui.navigation.pages if config.ui and config.ui.navigation else [])
        if page.capability is None or bool(getattr(config.capabilities, page.capability, False))
    ]
    return {
        "capabilities": config.capabilities.model_dump(),
        "default_entity_type": config.ui.default_entity_type if config.ui else None,
        "enabled_pages": enabled_pages,
        "roles": config.ui.roles if config.ui else {},
    }


def get_domain_config_schema_payload(
    config: DomainConfig = Depends(get_domain_config),
) -> dict[str, object]:
    """Return the JSON schema for the active domain configuration model."""
    return cast(dict[str, object], config.__class__.model_json_schema())


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


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    """Return the event bus implementation for API-triggered workflows."""
    return create_event_bus(get_event_bus_settings())


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    """Return the object store implementation for raw document content."""
    # TODO(production): Select object store adapter from config/env (S3, GCS, MinIO)
    # instead of hardcoding InMemoryObjectStore. Add connection health verification.
    return InMemoryObjectStore()


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    """Return the ingestion service used by API routes and tests."""
    # TODO(production): Add dependency factories for all remaining services:
    # get_graph_service, get_vectorstore_service, get_embeddings_service,
    # get_llm_service, get_rag_service, get_agent_service, get_monitoring_service,
    # get_risk_service, get_timeseries_service, get_gnn_service,
    # get_explainability_service. Each should select adapters from config.
    # Add cache invalidation mechanism (LRU_cache cannot be reloaded at runtime).
    return IngestionService(
        get_parser_orchestrator(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
    )
