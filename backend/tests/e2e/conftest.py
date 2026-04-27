"""Shared fixtures for end-to-end pipeline integration tests.

The fixtures wire FastAPI's TestClient against fully in-memory adapters and
run the worker coordinator in-process via ``drain_ingestion_events``.  No
external services (Redis, Neo4j, Qdrant, real LLM providers) are touched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from agent.coordinator import drain_ingestion_events
from analytics.explainability.adapters.in_memory import (
    InMemoryExplainabilityContextSource,
)
from analytics.explainability.service import (
    ExplainabilityService,
    create_explainability_service,
)
from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.gnn.service import GnnService, create_gnn_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.service import RiskService, create_risk_service
from api.app import create_app
from api.dependencies import (
    get_event_bus,
    get_graph_repository,
    get_graph_service,
    get_ingestion_service,
    get_object_store,
    get_vector_store,
    get_vectorstore_service,
)
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import create_embeddings_service
from events.adapters.in_memory import InMemoryEventBus
from events.types import KnowledgeBaseReadyEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.adapters.protocols import GraphRepository
from graph.service import GraphService, create_graph_service
from ingestion.chunker import DocumentChunker, create_document_chunker
from ingestion.extractor import (
    PatternDocumentExtractor,
    create_document_extractor,
)
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.validator import (
    ExtractionResultValidator,
    create_extraction_validator,
)
from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.service import MonitoringService, create_monitoring_service
from shared.types import EntityDefinition, PropertyDefinition, PropertyType
from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol


_E2E_ENTITY_DEFINITIONS: list[EntityDefinition] = [
    EntityDefinition(
        name="provider",
        display_label="Provider",
        icon="stethoscope",
        properties={
            "name": PropertyDefinition(
                type=PropertyType.STRING,
                display="Name",
                required=True,
            ),
        },
    ),
]


@dataclass(slots=True)
class E2EHarness:
    """Container for the cross-module dependencies driven by the test client."""

    client: TestClient
    event_bus: InMemoryEventBus
    object_store: ObjectStore
    graph_repository: GraphRepository
    graph_service: GraphService
    vector_store: VectorStoreProtocol
    ingestion_service: IngestionService
    document_chunker: DocumentChunker
    document_extractor: PatternDocumentExtractor
    extraction_validator: ExtractionResultValidator
    embeddings_service: EmbeddingsServiceProtocol
    gnn_service: GnnService
    risk_service: RiskService
    explainability_service: ExplainabilityService
    monitoring_service: MonitoringService
    received_kb_ready: list[KnowledgeBaseReadyEvent] = field(
        default_factory=lambda: list[KnowledgeBaseReadyEvent](),
    )

    def drain(self, *, max_iterations: int = 64) -> int:
        """Drive ``drain_ingestion_events`` until quiescent or ``kb.ready`` arrives."""

        total = 0
        for _ in range(max_iterations):
            processed = asyncio.run(
                drain_ingestion_events(
                    self.event_bus,
                    self.ingestion_service,
                    self.document_chunker,
                    self.document_extractor,
                    self.extraction_validator,
                    self.graph_service,
                    self.object_store,
                    embeddings_service=self.embeddings_service,
                    vector_store=self.vector_store,
                    graph_repository=self.graph_repository,
                    gnn_service=self.gnn_service,
                    risk_service=self.risk_service,
                    explainability_service=self.explainability_service,
                    monitoring_service=self.monitoring_service,
                    consumer_group="e2e-workers",
                    consumer_name="e2e-worker-1",
                    limit=16,
                )
            )
            total += processed
            self.received_kb_ready = [
                event
                for event in self.event_bus.published_events
                if isinstance(event, KnowledgeBaseReadyEvent)
            ]
            if processed == 0:
                break
        return total


@pytest.fixture
def harness() -> Iterator[E2EHarness]:
    """Build a fresh harness with a single shared in-memory event bus.

    All FastAPI dependencies that touch shared state (event bus, object store,
    graph, vector, ingestion service) are overridden so the worker coordinator
    drains the same bus the API publishes to.
    """

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    vector_store = InMemoryVectorStore()
    vectorstore_service = create_embeddings_service  # avoid unused import lint
    del vectorstore_service
    embedder = InMemoryEmbedder()
    embeddings_service = create_embeddings_service(embedder, event_bus=event_bus)

    parser_registry = create_default_registry()
    parser_orchestrator = DocumentParsingOrchestrator(
        parser_registry,
        fetcher=HttpxRemoteDocumentFetcher(),
    )
    ingestion_service = IngestionService(
        parser_orchestrator,
        object_store=object_store,
        event_bus=event_bus,
    )
    document_chunker = create_document_chunker()
    document_extractor = create_document_extractor(_E2E_ENTITY_DEFINITIONS)
    extraction_validator = create_extraction_validator(
        _E2E_ENTITY_DEFINITIONS,
        [],
    )

    gnn_service = create_gnn_service(
        InMemoryGraphSnapshotSource(),
        event_bus=event_bus,
    )
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(),
        event_bus=event_bus,
    )
    explainability_service = create_explainability_service(
        InMemoryExplainabilityContextSource(),
        event_bus=event_bus,
    )
    monitoring_service = create_monitoring_service(
        InMemoryObservationSource(),
        event_bus=event_bus,
    )

    app = create_app()
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_graph_repository] = lambda: graph_repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_vectorstore_service] = (
        lambda: graph_service  # noqa: E731 - placeholder; not used by KB router
    )
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service

    with TestClient(app) as client:
        yield E2EHarness(
            client=client,
            event_bus=event_bus,
            object_store=object_store,
            graph_repository=graph_repository,
            graph_service=graph_service,
            vector_store=vector_store,
            ingestion_service=ingestion_service,
            document_chunker=document_chunker,
            document_extractor=document_extractor,
            extraction_validator=extraction_validator,
            embeddings_service=embeddings_service,
            gnn_service=gnn_service,
            risk_service=risk_service,
            explainability_service=explainability_service,
            monitoring_service=monitoring_service,
        )

    app.dependency_overrides.clear()
