"""Dependency injection wiring for the FastAPI application."""

from __future__ import annotations

from functools import lru_cache

from config.loader import load_config
from config.schema import DomainConfig
from events.adapters.in_memory import InMemoryEventBus
from events.protocols import EventBus
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import ParserRegistry, create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore


@lru_cache(maxsize=1)
def get_domain_config() -> DomainConfig:
    """Load and cache the domain configuration (singleton).

    The config is loaded once on first call and cached for the lifetime
    of the process.  To reload, restart the server.
    """
    return load_config()


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
def get_event_bus() -> EventBus:
    """Return the event bus implementation for API-triggered workflows."""
    return InMemoryEventBus()


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    """Return the object store implementation for raw document content."""
    return InMemoryObjectStore()


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    """Return the ingestion service used by API routes and tests."""
    return IngestionService(
        get_parser_orchestrator(),
        object_store=get_object_store(),
        event_bus=get_event_bus(),
    )
