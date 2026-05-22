"""Shared fixtures for end-to-end pipeline integration tests.

The fixtures wire FastAPI's TestClient against fully in-memory adapters and
run the worker coordinator in-process via ``drain_ingestion_events``.  No
external services (Redis, Neo4j, Qdrant, real LLM providers) are touched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.coordinator import drain_ingestion_events
from agent.workflow_tracking import WorkflowEventTracker
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
    get_domain_config,
    get_event_bus,
    get_graph_repository,
    get_graph_service,
    get_ingestion_service,
    get_object_store,
    get_raw_record_store,
    get_records_service,
    get_vector_service,
    get_vector_store,
    get_vectorstore_service,
    get_workflow_tracker,
)
from config.loader import load_config
from config.schema import (
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    RecordsConfig,
    ValidationConfig,
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
from monitoring.adapters.in_memory import (
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.service import MonitoringService, create_monitoring_service
from records.adapters.in_memory import InMemoryRawRecordStore
from records.service import RecordsService, create_records_service
from shared.types import EntityDefinition, PropertyDefinition, PropertyType
from storage.adapters.in_memory import InMemoryObjectStore
from storage.protocols import ObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol

_MEDICARE_FRAUD_CONFIG_PATH = (
    Path(__file__).parent.parent.parent
    / "config"
    / "defaults"
    / "medicare_fraud_cms_desynpuf.yaml"
)


def _build_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="Test"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(enabled=False),
        validation=ValidationConfig(
            max_file_size_mb=10,
            allowed_content_types=["text/plain", "application/json"],
        ),
        alerts=AlertsConfig(thresholds={}),
    )


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
    workflow_tracker: WorkflowEventTracker
    # Optional records-path extensions (populated by medicare_fraud_harness)
    raw_record_store: InMemoryRawRecordStore | None = None
    records_service: RecordsService | None = None
    observation_writer: InMemoryObservationWriter | None = None
    records_config: RecordsConfig | None = None
    # Drain configuration (set by factory; defaults match the base harness)
    drain_consumer_group: str = "e2e-workers"
    drain_consumer_name: str = "e2e-worker-1"
    drain_limit: int = 16
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
                    records_config=self.records_config,
                    raw_record_store=self.raw_record_store,
                    observation_writer=self.observation_writer,
                    consumer_group=self.drain_consumer_group,
                    consumer_name=self.drain_consumer_name,
                    limit=self.drain_limit,
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


def _build_harness(
    domain_config: DomainConfig,
    *,
    consumer_group: str = "e2e-workers",
    consumer_name: str = "e2e-worker-1",
    drain_limit: int = 16,
    with_records: bool = False,
) -> Iterator[E2EHarness]:
    """Core harness factory used by all e2e fixtures.

    When ``with_records=True`` the harness additionally wires:
    - ``InMemoryRawRecordStore`` / ``RecordsService`` / ``InMemoryObservationWriter``
    - ``get_raw_record_store`` / ``get_records_service`` dependency overrides
    and propagates ``records_config`` into the ``drain`` closure.
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
    workflow_run_store = InMemoryWorkflowRunStore()
    workflow_tracker = WorkflowEventTracker(workflow_run_store)
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

    entity_defs = domain_config.entities if with_records else _E2E_ENTITY_DEFINITIONS
    rel_defs = domain_config.relationships if with_records else []
    document_chunker = create_document_chunker(
        domain_config.ingestion.chunking if with_records else None
    )
    document_extractor = create_document_extractor(entity_defs, rel_defs)
    extraction_validator = create_extraction_validator(entity_defs, rel_defs)

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

    # Optional records-path wiring
    raw_record_store: InMemoryRawRecordStore | None = None
    records_service: RecordsService | None = None
    observation_writer: InMemoryObservationWriter | None = None
    records_config: RecordsConfig | None = None

    if with_records:
        raw_record_store = InMemoryRawRecordStore()
        observation_writer = InMemoryObservationWriter()
        records_config = domain_config.records or RecordsConfig()
        records_service = create_records_service(
            raw_record_store,
            event_bus=event_bus,
            records_config=records_config,
        )

    from vectorstore.service import create_vector_service as _create_vs

    vector_service = _create_vs(
        vector_store,
        event_bus=event_bus,
        object_store=object_store,
    )

    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: domain_config
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_graph_repository] = lambda: graph_repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_vectorstore_service] = lambda: vector_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_workflow_tracker] = lambda: workflow_tracker
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service

    if with_records and raw_record_store is not None and records_service is not None:
        _rrs = raw_record_store
        _rs = records_service
        app.dependency_overrides[get_raw_record_store] = lambda: _rrs
        app.dependency_overrides[get_records_service] = lambda: _rs

    with TestClient(app) as client:
        yield E2EHarness(
            client=client,
            event_bus=event_bus,
            object_store=object_store,
            graph_repository=graph_repository,
            graph_service=graph_service,
            vector_store=vector_store,
            workflow_tracker=workflow_tracker,
            ingestion_service=ingestion_service,
            document_chunker=document_chunker,
            document_extractor=document_extractor,
            extraction_validator=extraction_validator,
            embeddings_service=embeddings_service,
            gnn_service=gnn_service,
            risk_service=risk_service,
            explainability_service=explainability_service,
            monitoring_service=monitoring_service,
            raw_record_store=raw_record_store,
            records_service=records_service,
            observation_writer=observation_writer,
            records_config=records_config,
            drain_consumer_group=consumer_group,
            drain_consumer_name=consumer_name,
            drain_limit=drain_limit,
        )

    app.dependency_overrides.clear()


@pytest.fixture
def harness() -> Iterator[E2EHarness]:
    """Build a fresh harness with a single shared in-memory event bus.

    All FastAPI dependencies that touch shared state (event bus, object store,
    graph, vector, ingestion service) are overridden so the worker coordinator
    drains the same bus the API publishes to.
    """
    yield from _build_harness(_build_config())


@pytest.fixture
def medicare_fraud_harness() -> Iterator[E2EHarness]:
    """Harness wired for the medicare_fraud_cms_desynpuf domain + records adapters.

    Extends ``E2EHarness`` with ``raw_record_store``, ``records_service``,
    ``observation_writer``, and ``records_config`` populated so the drain loop
    can process records.ingested events.
    """
    domain_config = load_config(_MEDICARE_FRAUD_CONFIG_PATH)
    yield from _build_harness(
        domain_config,
        consumer_group="e2e-records-workers",
        consumer_name="e2e-records-worker-1",
        drain_limit=32,
        with_records=True,
    )
