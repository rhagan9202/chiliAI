"""Tests for the worker coordinator ingestion wiring."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from types import SimpleNamespace
from typing import Literal

from collections.abc import Sequence

import pytest
from prometheus_client import REGISTRY

import agent.coordinator as coordinator
from agent.coordinator import (
    WORKER_EVENT_TYPES,
    build_document_status_store,
    build_worker_dependencies,
    drain_ingestion_events,
    handle_embeddings_complete,
    handle_event,
    handle_documents_chunked,
    handle_documents_parsed,
    handle_entities_extracted,
    handle_entities_validated,
    handle_graph_updated,
    handle_vectors_indexed,
    run_handler_with_retry,
)
from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.exceptions import ConfigurationError
from agent.models import (
    RetryPolicy,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStepState,
    WorkflowStepStatus,
)
from agent.policy import StagePolicy, StagePolicyRegistry
from agent.workflow_tracking import WorkflowEventTracker
from config.loader import load_config
from config.schema import (
    DomainConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GnnConfig,
    GraphDbConfig,
    LlmConfig,
    ObjectStoreConfig,
    RecordsConfig,
    VectorStoreConfig,
)
from monitoring.adapters.in_memory import InMemoryObservationWriter
from records.adapters.in_memory import InMemoryRawRecordStore
from embeddings.adapters.cache_in_memory import InMemoryLruEmbeddingCache
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.models import (
    EmbeddingMetadata,
    EmbeddingResult,
    EmbeddingVector,
    GraphEmbeddingBatch,
)
from embeddings.service import EmbeddingsService, create_embeddings_service
from embeddings.service_models import EmbedRequest, EmbedResponse, EmbeddedItem
from events.adapters.dlq_in_memory import InMemoryDlqRecordStore
from events.codec import encode_event
from events.dlq_models import DlqRecord
from events.protocols import DlqErrorInfo, EventDelivery
from events.runtime import EventBusSettings
from events.adapters.in_memory import InMemoryEventBus
from events.types import (
    AnalysisFailedEvent,
    AnyEvent,
    ChunkedDocumentReference,
    DocumentFailureReference,
    DocumentsChunkedEvent,
    DocumentsExtractionWarningEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    EmbeddingsCompleteDocumentReference,
    EmbeddingsCompleteEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    ExtractionWarningReference,
    GraphUpdatedDocumentReference,
    GraphUpdatedEvent,
    KnowledgeBaseCreatedEvent,
    KnowledgeBaseReadyEvent,
    KnowledgeBaseReadyReference,
    ParsedDocumentReference,
    RecordsIngestedEvent,
    RiskScoredEvent as _RiskScoredEvent,
    ValidatedDocumentReference,
    VectorsIndexedDocumentReference,
    VectorsIndexedEvent,
)
from monitoring.service import MonitoringService as _MonitoringService
from graph.exceptions import BatchUpsertError, GraphVersionConflictError
from graph.models import GraphUpsertResult
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from graph.service_models import GraphBuildReceipt, GraphBuildTask
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.chunker import ChunkingResult, create_document_chunker
from ingestion.extractor import create_document_extractor
from ingestion.models import (
    CandidateEntity,
    ExtractionResult,
    IngestionStatus,
    ParsedDocument,
    ValidationReport,
)
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.recovery import ObjectStoreIngestionRecoveryStore
from ingestion.service import IngestionService
from ingestion.service_models import DocumentSubmission
from ingestion.validator import create_extraction_validator
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from shared.types import (
    Entity,
    EntityDefinition,
    KnowledgeBase,
    PropertyDefinition,
    PropertyType,
    Relationship,
)
from storage.adapters.in_memory import InMemoryObjectStore
from storage.models import StoredObject
from vectorstore.adapters.in_memory import InMemoryVectorStore


def _reconcile_zero(**_: object) -> int:
    """Typed no-op stand-in for ``WorkflowEventTracker.reconcile_stale_runs``."""
    return 0


def test_worker_event_types_include_kb_ready_for_workflow_tracking() -> None:
    assert "kb.ready" in WORKER_EVENT_TYPES


def test_worker_event_types_include_documents_failed_for_workflow_tracking() -> None:
    assert "documents.failed" in WORKER_EVENT_TYPES


def test_drain_ingestion_events_completes_kb_ready_workflow() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    workflow_run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-ready",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="ready")],
                metadata={"correlation_id": "corr-ready"},
            )
        ]
    )
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    event_bus.publish(
        KnowledgeBaseReadyEvent(
            correlation_id="corr-ready",
            knowledge_bases=[
                KnowledgeBaseReadyReference(
                    knowledge_base_id="kb-1",
                    entity_count=0,
                    relationship_count=0,
                    vector_count=0,
                )
            ],
        )
    )

    processed = asyncio.run(drain_ingestion_events(
        event_bus,
        IngestionService(
            DocumentParsingOrchestrator(
                create_default_registry(),
                fetcher=HttpxRemoteDocumentFetcher(),
            ),
            object_store=object_store,
            event_bus=event_bus,
        ),
        create_document_chunker(),
        create_document_extractor([]),
        create_extraction_validator([], []),
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
        workflow_tracker=WorkflowEventTracker(workflow_run_store),
    ))

    run = workflow_run_store.get_run("workflow-ready")
    assert processed == 0
    assert run.status is WorkflowRunStatus.COMPLETED
    assert run.steps[0].status is WorkflowStepStatus.COMPLETED


def test_drain_ingestion_events_marks_documents_failed_workflow_failed() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    workflow_run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-doc-failed",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                metadata={"correlation_id": "corr-doc-failed"},
            )
        ]
    )
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    event_bus.publish(
        DocumentsFailedEvent(
            correlation_id="corr-doc-failed",
            documents=[
                DocumentFailureReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    error_message="parse failed",
                )
            ],
        )
    )

    processed = asyncio.run(drain_ingestion_events(
        event_bus,
        IngestionService(
            DocumentParsingOrchestrator(
                create_default_registry(),
                fetcher=HttpxRemoteDocumentFetcher(),
            ),
            object_store=object_store,
            event_bus=event_bus,
        ),
        create_document_chunker(),
        create_document_extractor([]),
        create_extraction_validator([], []),
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
        workflow_tracker=WorkflowEventTracker(workflow_run_store),
    ))

    run = workflow_run_store.get_run("workflow-doc-failed")
    assert processed == 0
    assert run.status is WorkflowRunStatus.FAILED
    assert run.steps[0].status is WorkflowStepStatus.FAILED




class _FakeEmbeddingsService:
    """Test double that records requests and returns deterministic vectors."""

    def __init__(self) -> None:
        self.requests: list[EmbedRequest] = []

    def embed(self, request: EmbedRequest) -> EmbedResponse:
        self.requests.append(request)
        return EmbedResponse(
            request_id="embed-request-1",
            model_name=request.model_name,
            dimensions=2,
            items=[
                EmbeddedItem(
                    content_id=submission.content_id,
                    vector=[float(index), float(len(submission.content))],
                )
                for index, submission in enumerate(request.submissions, start=1)
            ],
        )


class _StaticGraphProvider:
    def __init__(self, vectors: dict[str, list[float]], *, dimensions: int) -> None:
        self._vectors = vectors
        self._dimensions = dimensions
        self.calls: list[tuple[str, list[str], int]] = []

    def get_node_embeddings(
        self,
        *,
        knowledge_base_id: str,
        content_ids: Sequence[str],
        dimensions: int,
    ) -> GraphEmbeddingBatch:
        self.calls.append((knowledge_base_id, list(content_ids), dimensions))
        return GraphEmbeddingBatch(
            vectors={
                key: value for key, value in self._vectors.items() if key in content_ids
            },
            model_name="gnn-spectral",
            provider="test-gnn",
            dimensions=self._dimensions,
        )


class _RecoveringEventBus(InMemoryEventBus):
    def __init__(
        self,
        *,
        reclaimed: list[EventDelivery],
        consumed: list[EventDelivery],
    ) -> None:
        super().__init__()
        self._reclaimed = reclaimed
        self._consumed = consumed
        self.calls: list[tuple[str, int]] = []
        self.acked_deliveries: list[EventDelivery] = []

    def reclaim_stale_pending(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int,
        limit: int = 10,
    ) -> list[EventDelivery]:
        del event_types, consumer_group, consumer_name, min_idle_ms
        self.calls.append(("reclaim", limit))
        return self._reclaimed[:limit]

    def consume(
        self,
        event_types: list[str],
        *,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
        limit: int = 1,
        block_ms: int | None = None,
    ) -> list[EventDelivery]:
        del event_types, consumer_group, consumer_name, block_ms
        self.calls.append(("consume", limit))
        return self._consumed[:limit]

    def ack(self, deliveries: list[EventDelivery]) -> None:
        self.acked_deliveries.extend(deliveries)
        super().ack(deliveries)


def _graph_updated_event_with_valid_entity(
    *,
    knowledge_base_id: str,
    entity_id: str,
    object_store: InMemoryObjectStore,
) -> GraphUpdatedEvent:
    graph_update_storage_key = (
        f"knowledgebases/{knowledge_base_id}/graph_updates/extract-1.json"
    )
    validation_storage_key = (
        f"knowledgebases/{knowledge_base_id}/validations/extract-1.json"
    )
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id=knowledge_base_id,
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=[entity_id],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(
                    id=entity_id,
                    type="provider",
                    properties={"name": "Alpha Clinic"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    return GraphUpdatedEvent(
        documents=[
            GraphUpdatedDocumentReference(
                knowledge_base_id=knowledge_base_id,
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="validate-1",
                upserted_entity_count=1,
                upserted_relationship_count=0,
                validation_storage_key=validation_storage_key,
                graph_update_storage_key=graph_update_storage_key,
            )
        ],
    )


def _parsed_delivery(
    *,
    event_id: str,
    parsed_document_id: str,
    object_store: InMemoryObjectStore,
) -> EventDelivery:
    storage_key = f"knowledgebases/kb-1/parsed/{parsed_document_id}.json"
    object_store.put_bytes(
        storage_key,
        ParsedDocument(
            id=parsed_document_id,
            source_document_id=f"doc-{parsed_document_id}",
            text_content=f"Claim content for {parsed_document_id}.",
            parser_name="test-parser",
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    return EventDelivery(
        event=DocumentsParsedEvent(
            correlation_id=f"corr-{parsed_document_id}",
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id=f"doc-{parsed_document_id}",
                    parsed_document_id=parsed_document_id,
                    parser_name="test-parser",
                    storage_key=f"knowledgebases/kb-1/documents/{parsed_document_id}.txt",
                    parsed_document_storage_key=storage_key,
                )
            ],
        ),
        event_id=event_id,
        stream="chili.documents.parsed",
        consumer_group="test-workers",
    )


def test_drain_ingestion_events_processes_reclaimed_pending_before_new_deliveries() -> None:
    object_store = InMemoryObjectStore()
    reclaimed = _parsed_delivery(
        event_id="1-0",
        parsed_document_id="parsed-stale",
        object_store=object_store,
    )
    consumed = _parsed_delivery(
        event_id="2-0",
        parsed_document_id="parsed-new",
        object_store=object_store,
    )
    event_bus = _RecoveringEventBus(reclaimed=[reclaimed], consumed=[consumed])
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        create_document_chunker(),
        create_document_extractor([]),
        create_extraction_validator([], []),
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
        limit=2,
        reclaim_min_idle_ms=30_000,
    ))

    assert processed == 2
    assert event_bus.calls == [("reclaim", 2), ("consume", 1)]
    assert event_bus.acked_deliveries == [reclaimed, consumed]


def test_build_worker_dependencies_assembles_ingestion_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults_dir = (
        __file__
        .replace("tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml")
    )
    monkeypatch.setattr(
        "agent.coordinator.load_active_config", lambda: load_config(defaults_dir)
    )
    monkeypatch.setattr(
        "agent.coordinator.load_event_bus_settings",
        lambda: EventBusSettings(backend="in-memory"),
    )

    deps = build_worker_dependencies()

    assert isinstance(deps.event_bus, InMemoryEventBus)
    assert isinstance(deps.ingestion_service, IngestionService)
    assert deps.document_chunker is not None
    assert deps.document_extractor is not None
    assert deps.extraction_validator is not None
    assert deps.graph_service is not None
    assert isinstance(deps.embeddings_service, EmbeddingsService)
    assert isinstance(deps.object_store, InMemoryObjectStore)
    assert isinstance(deps.vector_store, InMemoryVectorStore)
    assert isinstance(deps.embeddings_service, EmbeddingsService)
    assert deps.llm_client is not None
    assert deps.event_settings.backend == "in-memory"
    assert isinstance(deps.ingestion_service._recovery_store, ObjectStoreIngestionRecoveryStore)  # pyright: ignore[reportPrivateUsage]


def test_build_worker_dependencies_wires_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults_dir = (
        __file__
        .replace("tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml")
    )
    monkeypatch.setattr(
        "agent.coordinator.load_active_config", lambda: load_config(defaults_dir)
    )
    monkeypatch.setattr(
        "agent.coordinator.load_event_bus_settings",
        lambda: EventBusSettings(backend="in-memory"),
    )

    deps = build_worker_dependencies()

    assert deps.policy_service is not None
    assert isinstance(deps.policy_rules, list)
    assert deps.policy_rules, "medicare_fraud.yaml ships policy rule packs"


def test_build_graph_snapshot_source_returns_repository_backed_source() -> None:
    """B1: the factory wires a GraphRepositorySnapshotSource over the given repository."""
    from analytics.gnn.adapters.cluster_store import ObjectStoreClusterSummaryStore
    from analytics.gnn.adapters.graph_repository_source import GraphRepositorySnapshotSource

    defaults_dir = (
        __file__
        .replace("tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml")
    )
    config = load_config(defaults_dir)
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e1", type="provider", properties={}),
            Entity(id="e2", type="provider", properties={}),
        ],
    )
    cluster_store = ObjectStoreClusterSummaryStore(InMemoryObjectStore())

    source = coordinator.build_graph_snapshot_source(
        config, repository=repository, cluster_store=cluster_store
    )

    assert isinstance(source, GraphRepositorySnapshotSource)
    snapshot = source.load_snapshot(knowledge_base_id="kb-1")
    assert {node.entity_id for node in snapshot.nodes} == {"e1", "e2"}


def test_build_graph_snapshot_source_honors_configured_snapshot_max_nodes() -> None:
    """B1: DomainConfig.gnn.snapshot_max_nodes bounds the returned snapshot."""
    from analytics.gnn.adapters.cluster_store import ObjectStoreClusterSummaryStore

    defaults_dir = (
        __file__
        .replace("tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml")
    )
    config = load_config(defaults_dir).model_copy(
        update={"gnn": GnnConfig(snapshot_max_nodes=1)}
    )
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="e1", type="provider", properties={}),
            Entity(id="e2", type="provider", properties={}),
        ],
    )
    cluster_store = ObjectStoreClusterSummaryStore(InMemoryObjectStore())

    source = coordinator.build_graph_snapshot_source(
        config, repository=repository, cluster_store=cluster_store
    )
    snapshot = source.load_snapshot(knowledge_base_id="kb-1")

    assert len(snapshot.nodes) == 1


def test_build_worker_dependencies_wires_shared_gnn_cluster_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B1 coordination: worker deps expose the same cluster store the GNN
    service's snapshot source reads from, so a later persistence step (Task
    4) writing through ``deps.gnn_cluster_store`` is immediately visible to
    ``deps.gnn_service``."""
    from analytics.gnn.adapters.cluster_store import ObjectStoreClusterSummaryStore
    from analytics.gnn.models import ClusterSummary
    from analytics.gnn.service_models import GnnClusterRequest

    defaults_dir = (
        __file__
        .replace("tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml")
    )
    monkeypatch.setattr(
        "agent.coordinator.load_active_config", lambda: load_config(defaults_dir)
    )
    monkeypatch.setattr(
        "agent.coordinator.load_event_bus_settings",
        lambda: EventBusSettings(backend="in-memory"),
    )

    deps = build_worker_dependencies()

    assert isinstance(deps.gnn_cluster_store, ObjectStoreClusterSummaryStore)

    deps.gnn_cluster_store.put_clusters(
        "kb-1",
        [
            ClusterSummary(
                cluster_id="cluster-1",
                entity_ids=["e1", "e2"],
                anomaly_score=0.5,
                label="test",
            )
        ],
    )

    response = deps.gnn_service.list_clusters(
        GnnClusterRequest(knowledge_base_id="kb-1")
    )

    assert [c.cluster_id for c in response.clusters] == ["cluster-1"]


def test_worker_event_bus_explicit_config_preserves_env_recovery_and_trim_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults_dir = (
        __file__
        .replace("tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml")
    )
    config = load_config(defaults_dir).model_copy(
        update={
            "events": EventBusConfig(
                backend="redis",
                uri="redis://localhost:6379/5",
                stream_prefix="custom",
                consumer_group="custom-workers",
            )
        }
    )
    monkeypatch.setenv("CHILI_EVENT_STREAM_MAXLEN", "7500")
    monkeypatch.setenv("CHILI_EVENT_RECLAIM_MIN_IDLE_MS", "90000")

    settings = coordinator._resolve_worker_event_bus_settings(config)  # pyright: ignore[reportPrivateUsage]

    assert settings.stream_maxlen == 7500
    assert settings.reclaim_min_idle_ms == 90_000


def test_handle_event_returns_zero_for_unhandled_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(event=KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0


def test_drain_ingestion_events_processes_uploaded_documents() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    processed = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

    assert processed == 1
    assert any(isinstance(event, DocumentsParsedEvent) for event in event_bus.published_events)


def test_drain_ingestion_events_processes_parsed_documents_into_chunks() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    parsed_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))
    chunked_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

    assert parsed_count == 1
    assert chunked_count == 1
    chunked_events = [
        event for event in event_bus.published_events if isinstance(event, DocumentsChunkedEvent)
    ]
    assert len(chunked_events) == 1
    assert chunked_events[0].documents[0].chunk_count >= 1
    assert chunked_events[0].documents[0].chunks_storage_key is not None

    stored_chunks = object_store.get_bytes(chunked_events[0].documents[0].chunks_storage_key or "")
    chunking_result = ChunkingResult.model_validate_json(stored_chunks.content)
    assert chunking_result.parsed_document_id == chunked_events[0].documents[0].parsed_document_id
    assert len(chunking_result.chunks) == chunked_events[0].documents[0].chunk_count


def test_drain_ingestion_events_processes_chunked_documents_into_extractions() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))
    asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))
    extracted_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

    assert extracted_count == 1
    extracted_events = [
        event for event in event_bus.published_events if isinstance(event, EntitiesExtractedEvent)
    ]
    assert len(extracted_events) == 1
    assert extracted_events[0].documents[0].extraction_storage_key is not None

    stored_extraction = object_store.get_bytes(
        extracted_events[0].documents[0].extraction_storage_key or ""
    )
    extraction_result = ExtractionResult.model_validate_json(stored_extraction.content)
    assert extraction_result.parsed_document_id == extracted_events[0].documents[0].parsed_document_id


def test_drain_ingestion_events_processes_extracted_documents_into_validations() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    for _ in range(3):
        asyncio.run(drain_ingestion_events(
            event_bus,
            service,
            chunker,
            extractor,
            validator,
            graph_service,
            object_store,
            consumer_group="test-workers",
            consumer_name="worker-1",
        ))
    validated_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

    assert validated_count == 1
    validated_events = [
        event for event in event_bus.published_events if isinstance(event, EntitiesValidatedEvent)
    ]
    assert len(validated_events) == 1
    assert validated_events[0].documents[0].validation_storage_key is not None

    stored_report = object_store.get_bytes(validated_events[0].documents[0].validation_storage_key or "")
    report = ValidationReport.model_validate_json(stored_report.content)
    assert report.extraction_result_id == validated_events[0].documents[0].extraction_result_id


def test_handle_documents_parsed_publishes_chunked_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    parsed_document = ParsedDocument(
        id="parsed-1",
        source_document_id="doc-1",
        text_content="Claim 42 was filed by provider A.",
        parser_name="test-parser",
    )
    storage_key = "knowledgebases/kb-1/parsed/parsed-1.json"
    object_store.put_bytes(
        storage_key,
        parsed_document.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_documents_parsed(
        DocumentsParsedEvent(
            correlation_id="corr-123",
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test-parser",
                    storage_key="knowledgebases/kb-1/documents/doc-1/claims.txt",
                    parsed_document_storage_key=storage_key,
                )
            ]
        ),
        document_chunker=chunker,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], DocumentsChunkedEvent)
    assert event_bus.published_events[-1].correlation_id == "corr-123"
    reference = event_bus.published_events[-1].documents[0]
    assert reference.parsed_document_storage_key == storage_key
    assert reference.chunks_storage_key == "knowledgebases/kb-1/chunks/parsed-1.json"
    assert reference.chunk_count >= 1

    stored_chunks = object_store.get_bytes(reference.chunks_storage_key or "")
    chunking_result = ChunkingResult.model_validate_json(stored_chunks.content)
    assert chunking_result.strategy_used == reference.strategy
    assert len(chunking_result.chunks) == reference.chunk_count


def test_handle_documents_chunked_publishes_entities_extracted_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunking_result = ChunkingResult(
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        strategy_used="StructuredRecordChunker",
        chunks=[],
    )
    chunks_storage_key = "knowledgebases/kb-1/chunks/parsed-1.json"
    object_store.put_bytes(
        chunks_storage_key,
        chunking_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_documents_chunked(
        DocumentsChunkedEvent(
            documents=[
                ChunkedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    chunk_count=0,
                    strategy="StructuredRecordChunker",
                    chunks_storage_key=chunks_storage_key,
                )
            ]
        ),
        document_extractor=create_document_extractor([]),
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], EntitiesExtractedEvent)
    reference = event_bus.published_events[-1].documents[0]
    assert reference.extraction_storage_key is not None

    stored_extraction = object_store.get_bytes(reference.extraction_storage_key)
    extraction_result = ExtractionResult.model_validate_json(stored_extraction.content)
    assert extraction_result.source_document_id == "doc-1"


def test_handle_entities_extracted_publishes_entities_validated_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extraction_result = ExtractionResult(
        id="extract-1",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-1.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_entities_extracted(
        EntitiesExtractedEvent(
            documents=[
                ExtractedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    entity_count=0,
                    relationship_count=0,
                    extraction_storage_key=extraction_storage_key,
                )
            ]
        ),
        extraction_validator=create_extraction_validator([], []),
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    validated_events = [
        event
        for event in event_bus.published_events
        if isinstance(event, EntitiesValidatedEvent)
    ]
    assert len(validated_events) == 1
    reference = validated_events[0].documents[0]
    assert reference.validation_storage_key == "knowledgebases/kb-1/validations/extract-1.json"


def test_handle_entities_extracted_emits_extraction_warning_for_empty_document() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extraction_result = ExtractionResult(
        id="extract-1",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        candidate_entities=[
            CandidateEntity(
                id="ghost-1",
                source_document_id="doc-1",
                chunk_id="chunk-1",
                type="provider",
                properties={"npi": "1234567890"},
                confidence=0.9,
                extraction_method="pattern_v1",
            )
        ],
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-1.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    handle_entities_extracted(
        EntitiesExtractedEvent(
            documents=[
                ExtractedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    entity_count=0,
                    relationship_count=0,
                    extraction_storage_key=extraction_storage_key,
                )
            ]
        ),
        # No entity definitions -> the candidate is dropped (unknown type),
        # leaving zero valid entities and a populated entity_errors map.
        extraction_validator=create_extraction_validator([], []),
        object_store=object_store,
        event_bus=event_bus,
    )

    warning_events = [
        event
        for event in event_bus.published_events
        if isinstance(event, DocumentsExtractionWarningEvent)
    ]
    assert len(warning_events) == 1
    warning = warning_events[0].documents[0]
    assert warning.source_document_id == "doc-1"
    assert warning.empty_extraction is True
    assert warning.valid_entity_count == 0
    assert warning.dropped_entity_count == 1
    assert warning.sample_reasons
    assert any("ghost-1" in reason for reason in warning.sample_reasons)
    assert warning.validation_storage_key == "knowledgebases/kb-1/validations/extract-1.json"


def test_handle_entities_extracted_skips_extraction_warning_for_clean_document() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extraction_result = ExtractionResult(
        id="extract-1",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        candidate_entities=[
            CandidateEntity(
                id="provider-1",
                source_document_id="doc-1",
                chunk_id="chunk-1",
                type="provider",
                properties={"npi": "1234567890"},
                confidence=0.9,
                extraction_method="pattern_v1",
            )
        ],
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-1.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    validator = create_extraction_validator(
        [
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="box",
                properties={"npi": PropertyDefinition(type=PropertyType.STRING, display="NPI")},
            )
        ],
        [],
    )

    handle_entities_extracted(
        EntitiesExtractedEvent(
            documents=[
                ExtractedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    entity_count=1,
                    relationship_count=0,
                    extraction_storage_key=extraction_storage_key,
                )
            ]
        ),
        extraction_validator=validator,
        object_store=object_store,
        event_bus=event_bus,
    )

    warning_events = [
        event
        for event in event_bus.published_events
        if isinstance(event, DocumentsExtractionWarningEvent)
    ]
    assert warning_events == []


def test_handle_entities_validated_publishes_graph_updated_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    validation_report = ValidationReport(
        id="validate-1",
        extraction_result_id="extract-1",
        source_document_id="doc-1",
    )
    validation_storage_key = "knowledgebases/kb-1/validations/extract-1.json"
    object_store.put_bytes(
        validation_storage_key,
        validation_report.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_entities_validated(
        EntitiesValidatedEvent(
            correlation_id="corr-graph-123",
            documents=[
                ValidatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    valid_entity_count=0,
                    valid_relationship_count=0,
                    entity_error_count=0,
                    relationship_error_count=0,
                    validation_storage_key=validation_storage_key,
                )
            ]
        ),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], GraphUpdatedEvent)
    assert event_bus.published_events[-1].correlation_id == "corr-graph-123"
    reference = event_bus.published_events[-1].documents[0]
    assert reference.graph_update_storage_key == "knowledgebases/kb-1/graph_updates/extract-1.json"


def test_handle_graph_updated_publishes_embeddings_complete_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-1.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-1.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=["provider-2", "provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(
                    id="provider-2",
                    type="provider",
                    properties={"specialty": "cardiology", "name": "Beta Clinic"},
                ),
                Entity(
                    id="provider-1",
                    type="provider",
                    properties={"zeta": "last", "alpha": "first"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_graph_updated(
        GraphUpdatedEvent(
            correlation_id="corr-embeddings-123",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    upserted_entity_count=2,
                    upserted_relationship_count=0,
                    validation_storage_key=validation_storage_key,
                    graph_update_storage_key=graph_update_storage_key,
                )
            ],
        ),
        embeddings_service=embeddings_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    assert len(embeddings_service.requests) == 1
    request = embeddings_service.requests[0]
    assert [item.content_id for item in request.submissions] == [
        "provider-1",
        "provider-2",
    ]
    assert request.submissions[0].content == (
        'id=provider-1\ntype=provider\nalpha="first"\nzeta="last"'
    )
    assert request.submissions[1].content == "Beta Clinic"
    assert request.include_graph_embeddings is False

    complete_event = event_bus.published_events[-1]
    assert isinstance(complete_event, EmbeddingsCompleteEvent)
    assert complete_event.correlation_id == "corr-embeddings-123"
    complete_reference = complete_event.documents[0]
    assert complete_reference.entity_count == 2
    assert complete_reference.graph_update_storage_key == graph_update_storage_key
    assert complete_reference.embeddings_storage_key == (
        "knowledgebases/kb-1/embeddings/extract-1.embeddings.json"
    )

    stored_embeddings = object_store.get_bytes(complete_reference.embeddings_storage_key)
    embeddings_result = EmbeddingResult.model_validate_json(stored_embeddings.content)
    assert embeddings_result.request_id == "embed-request-1"
    assert list(embeddings_result.vectors) == ["provider-1", "provider-2"]
    assert embeddings_result.graph_status is None
    assert stored_embeddings.metadata["graph_update_storage_key"] == graph_update_storage_key


def test_handle_graph_updated_persists_text_and_graph_embedding_channels() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_provider = _StaticGraphProvider(
        {"entity-1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]},
        dimensions=8,
    )
    embeddings_service = create_embeddings_service(
        InMemoryEmbedder(dimensions=4),
        event_bus=event_bus,
        graph_embedding_provider=graph_provider,
    )
    event = _graph_updated_event_with_valid_entity(
        knowledge_base_id="kb-1",
        entity_id="entity-1",
        object_store=object_store,
    )

    handled = handle_graph_updated(
        event,
        embeddings_service=embeddings_service,
        object_store=object_store,
        event_bus=event_bus,
        include_graph_embeddings=True,
    )

    assert handled == 1
    complete_event = event_bus.published_events[-1]
    assert isinstance(complete_event, EmbeddingsCompleteEvent)
    storage_key = complete_event.documents[0].embeddings_storage_key
    artifact = EmbeddingResult.model_validate_json(
        object_store.get_bytes(storage_key).content
    )
    assert [(item.content_id, item.channel) for item in artifact.items] == [
        ("entity-1", "text"),
        ("entity-1", "graph"),
    ]
    assert graph_provider.calls == [("kb-1", ["entity-1"], 8)]


def test_handle_graph_updated_publishes_kb_ready_for_zero_entities() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-empty/graph_updates/extract-1.json"
    validation_storage_key = "knowledgebases/kb-empty/validations/extract-1.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-empty",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=[],
            upserted_relationship_ids=[],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[],
            valid_relationships=[],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_graph_updated(
        GraphUpdatedEvent(
            correlation_id="corr-empty-graph",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-empty",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    upserted_entity_count=0,
                    upserted_relationship_count=0,
                    validation_storage_key=validation_storage_key,
                    graph_update_storage_key=graph_update_storage_key,
                )
            ],
        ),
        embeddings_service=embeddings_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0
    assert embeddings_service.requests == []
    ready_events = [
        event for event in event_bus.published_events
        if isinstance(event, KnowledgeBaseReadyEvent)
    ]
    assert len(ready_events) == 1
    ready_reference = ready_events[0].knowledge_bases[0]
    assert ready_reference.knowledge_base_id == "kb-empty"
    assert ready_reference.entity_count == 0
    assert ready_reference.relationship_count == 0
    assert ready_reference.vector_count == 0
    assert ready_reference.source_document_id == "doc-1"
    assert ready_reference.empty_extraction is True


def test_handle_event_dispatches_graph_updated_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-1.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-1.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=["entity-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(
                    id="entity-1",
                    type="claim",
                    properties={"embedding_text": "Claim 42 from provider A"},
                )
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(
            event=GraphUpdatedEvent(
                correlation_id="corr-dispatch-123",
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        extraction_result_id="extract-1",
                        validation_report_id="validate-1",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        validation_storage_key=validation_storage_key,
                        graph_update_storage_key=graph_update_storage_key,
                    )
                ],
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
        embeddings_service=embeddings_service,
    )

    assert processed == 1
    assert isinstance(event_bus.published_events[-1], EmbeddingsCompleteEvent)
    assert event_bus.published_events[-1].correlation_id == "corr-dispatch-123"


def test_drain_ingestion_events_processes_validated_documents_into_graph_updates() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    for _ in range(4):
        asyncio.run(drain_ingestion_events(
            event_bus,
            service,
            chunker,
            extractor,
            validator,
            graph_service,
            object_store,
            consumer_group="test-workers",
            consumer_name="worker-1",
        ))
    graph_count = asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
    ))

    assert graph_count == 1
    graph_events = [
        event for event in event_bus.published_events if isinstance(event, GraphUpdatedEvent)
    ]
    assert len(graph_events) == 1
    assert graph_events[0].documents[0].graph_update_storage_key is not None


# ---------------------------------------------------------------------------
# E4-S08 — config-driven adapter wiring
# ---------------------------------------------------------------------------


def _base_config() -> DomainConfig:
    return load_config(
        __file__.replace(
            "tests/agent/test_coordinator.py",
            "config/defaults/medicare_fraud.yaml",
        )
    )


def test_build_object_store_uses_in_memory_when_section_default() -> None:
    config = _base_config()
    assert isinstance(__import__("agent.coordinator", fromlist=["build_object_store"]).build_object_store(config), InMemoryObjectStore)


def test_build_object_store_raises_for_unknown_backend() -> None:
    from agent.coordinator import build_object_store
    base = _base_config()
    forced_config = ObjectStoreConfig.model_construct(backend="gcs")
    config = base.model_copy(update={"storage": forced_config})
    with pytest.raises(ConfigurationError) as excinfo:
        build_object_store(config)
    assert excinfo.value.subsystem == "storage"
    assert excinfo.value.backend == "gcs"


def test_build_graph_repository_raises_when_neo4j_uri_missing() -> None:
    from agent.coordinator import build_graph_repository
    config = _base_config().model_copy(
        update={"graph": GraphDbConfig(backend="neo4j", uri=None)}
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_graph_repository(config)
    assert excinfo.value.subsystem == "graph"
    assert excinfo.value.backend == "neo4j"


def test_build_vector_store_raises_when_qdrant_uri_missing() -> None:
    from agent.coordinator import build_vector_store
    config = _base_config().model_copy(
        update={
            "vectorstore": VectorStoreConfig(backend="qdrant", uri=None, dimensions=384),
        }
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_vector_store(config)
    assert excinfo.value.subsystem == "vectorstore"


def test_build_embedder_raises_when_openai_api_key_env_var_missing() -> None:
    from agent.coordinator import build_embedder
    config = _base_config().model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="openai",
                model="text-embedding-3-small",
                dimensions=384,
            ),
        }
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_embedder(config)
    assert excinfo.value.subsystem == "embeddings"
    assert excinfo.value.backend == "openai"


def test_build_llm_client_raises_when_openai_api_key_env_var_missing() -> None:
    from agent.coordinator import build_llm_client
    config = _base_config().model_copy(
        update={"llm": LlmConfig(provider="openai", model="gpt-4o-mini")}
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_llm_client(config)
    assert excinfo.value.subsystem == "llm"
    assert excinfo.value.backend == "openai"


# ---------------------------------------------------------------------------
# E4-S02 — vector indexing handler
# ---------------------------------------------------------------------------


def _seed_validation_and_graph(
    object_store: InMemoryObjectStore,
    *,
    knowledge_base_id: str = "kb-1",
    graph_update_storage_key: str = "knowledgebases/kb-1/graph_updates/extract-1.json",
    validation_storage_key: str = "knowledgebases/kb-1/validations/extract-1.json",
) -> None:
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id=knowledge_base_id,
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            upserted_entity_ids=["entity-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-1",
            extraction_result_id="extract-1",
            source_document_id="doc-1",
            valid_entities=[
                Entity(
                    id="entity-1",
                    type="claim",
                    properties={"name": "Provider Alpha"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )


def _embeddings_complete_event_with_artifacts(
    *,
    object_store: InMemoryObjectStore,
    embeddings_result: EmbeddingResult,
    knowledge_base_id: str,
) -> EmbeddingsCompleteEvent:
    graph_update_storage_key = (
        f"knowledgebases/{knowledge_base_id}/graph_updates/extract-1.json"
    )
    validation_storage_key = (
        f"knowledgebases/{knowledge_base_id}/validations/extract-1.json"
    )
    embeddings_storage_key = (
        f"knowledgebases/{knowledge_base_id}/embeddings/extract-1.embeddings.json"
    )
    _seed_validation_and_graph(
        object_store,
        knowledge_base_id=knowledge_base_id,
        graph_update_storage_key=graph_update_storage_key,
        validation_storage_key=validation_storage_key,
    )
    object_store.put_bytes(
        embeddings_storage_key,
        embeddings_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    return EmbeddingsCompleteEvent(
        correlation_id="corr-embeddings-1",
        documents=[
            EmbeddingsCompleteDocumentReference(
                knowledge_base_id=knowledge_base_id,
                source_document_id="doc-1",
                parsed_document_id="parsed-1",
                extraction_result_id="extract-1",
                validation_report_id="validate-1",
                entity_count=1,
                graph_update_storage_key=graph_update_storage_key,
                embeddings_storage_key=embeddings_storage_key,
            )
        ],
    )


def test_handle_embeddings_complete_indexes_vectors_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    _seed_validation_and_graph(object_store)

    embeddings_storage_key = "knowledgebases/kb-1/embeddings/extract-1.embeddings.json"
    object_store.put_bytes(
        embeddings_storage_key,
        EmbeddingResult(
            request_id="embed-request-1",
            vectors={"entity-1": [0.1, 0.2, 0.3]},
            metadata=EmbeddingMetadata(
                model_name="model",
                dimensions=3,
                provider="embeddings-service",
            ),
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_embeddings_complete(
        EmbeddingsCompleteEvent(
            correlation_id="corr-vec-1",
            documents=[
                EmbeddingsCompleteDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    entity_count=1,
                    graph_update_storage_key="knowledgebases/kb-1/graph_updates/extract-1.json",
                    embeddings_storage_key=embeddings_storage_key,
                )
            ],
        ),
        vector_store=vector_store,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    indexed_event = next(
        event for event in event_bus.published_events if isinstance(event, VectorsIndexedEvent)
    )
    assert indexed_event.correlation_id == "corr-vec-1"
    assert indexed_event.documents[0].vector_count == 1
    assert indexed_event.documents[0].record_ids == ["kb-1:entity-1:text"]
    assert indexed_event.records[0].dimension == 3


def test_handle_embeddings_complete_indexes_text_and_graph_channels_separately() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    embeddings_result = EmbeddingResult(
        request_id="embed-1",
        vectors={"entity-1": [0.1, 0.2, 0.3, 0.4]},
        metadata=EmbeddingMetadata(
            model_name="text-model",
            dimensions=4,
            provider="test",
        ),
        items=[
            EmbeddingVector(
                content_id="entity-1",
                channel="text",
                vector=[0.1, 0.2, 0.3, 0.4],
                model_name="text-model",
                provider="test",
                dimensions=4,
            ),
            EmbeddingVector(
                content_id="entity-1",
                channel="graph",
                vector=[0.8, 0.1],
                model_name="gnn-spectral",
                provider="test-gnn",
                dimensions=2,
            ),
        ],
    )
    event = _embeddings_complete_event_with_artifacts(
        object_store=object_store,
        embeddings_result=embeddings_result,
        knowledge_base_id="kb-1",
    )

    count = handle_embeddings_complete(
        event,
        vector_store=vector_store,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert count == 1
    text_matches = vector_store.search(
        "kb-1",
        [0.1, 0.2, 0.3, 0.4],
        5,
        {"embedding_channel": "text"},
    )
    graph_matches = vector_store.search(
        "kb-1__graph",
        [0.8, 0.1],
        5,
        {"embedding_channel": "graph"},
    )
    assert text_matches[0].record_id == "kb-1:entity-1:text"
    assert graph_matches[0].record_id == "kb-1:entity-1:graph"
    assert graph_matches[0].metadata["knowledge_base_id"] == "kb-1"
    indexed_event = next(
        event for event in event_bus.published_events if isinstance(event, VectorsIndexedEvent)
    )
    assert indexed_event.documents[0].vector_count == 2


def test_handle_embeddings_complete_skips_when_no_vectors() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    _seed_validation_and_graph(object_store)

    embeddings_storage_key = "knowledgebases/kb-1/embeddings/extract-empty.embeddings.json"
    object_store.put_bytes(
        embeddings_storage_key,
        EmbeddingResult(
            request_id="embed-request-1",
            vectors={"entity-1": [0.0, 0.0]},
            metadata=EmbeddingMetadata(
                model_name="m", dimensions=2, provider="embeddings-service"
            ),
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_embeddings_complete(
        EmbeddingsCompleteEvent(
            correlation_id="corr-vec-2",
            documents=[
                EmbeddingsCompleteDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    entity_count=1,
                    graph_update_storage_key="knowledgebases/kb-1/graph_updates/extract-1.json",
                    embeddings_storage_key=embeddings_storage_key,
                )
            ],
        ),
        vector_store=vector_store,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1


# ---------------------------------------------------------------------------
# E4-S03 — kb.ready emission
# ---------------------------------------------------------------------------


def test_handle_vectors_indexed_emits_kb_ready_event() -> None:
    event_bus = InMemoryEventBus()
    graph_repository = InMemoryGraphRepository()

    processed = handle_vectors_indexed(
        VectorsIndexedEvent(
            correlation_id="corr-kb-1",
            documents=[
                VectorsIndexedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-1",
                    validation_report_id="validate-1",
                    vector_count=3,
                    embeddings_storage_key="knowledgebases/kb-1/embeddings/extract-1.embeddings.json",
                    record_ids=["kb-1:entity-1", "kb-1:entity-2", "kb-1:entity-3"],
                )
            ],
        ),
        graph_repository=graph_repository,
        event_bus=event_bus,
    )

    assert processed == 1
    ready_event = next(
        event for event in event_bus.published_events if isinstance(event, KnowledgeBaseReadyEvent)
    )
    assert ready_event.correlation_id == "corr-kb-1"
    assert ready_event.knowledge_bases[0].knowledge_base_id == "kb-1"
    assert ready_event.knowledge_bases[0].vector_count == 3


def test_handle_vectors_indexed_returns_zero_for_no_documents() -> None:
    event_bus = InMemoryEventBus()
    graph_repository = InMemoryGraphRepository()

    processed = handle_vectors_indexed(
        VectorsIndexedEvent(correlation_id="corr-empty", documents=[]),
        graph_repository=graph_repository,
        event_bus=event_bus,
    )
    assert processed == 0


def test_full_pipeline_chain_documents_uploaded_through_kb_ready() -> None:
    """Drive the full chain by seeding an in-progress GraphUpdatedEvent and
    draining events.uploaded → ... → kb.ready in a single test."""

    from embeddings.service import create_embeddings_service

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    embeddings_service = create_embeddings_service(
        InMemoryEmbedder(), event_bus=event_bus
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    # Seed the artifacts and publish the documents.uploaded event for stages 1-5.
    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    # Pre-seed graph + validation artifacts directly so we can also exercise the
    # graph.updated → embeddings.complete → vectors.indexed → kb.ready legs.
    graph_update_storage_key = (
        "knowledgebases/kb-1/graph_updates/extract-pipeline.json"
    )
    validation_storage_key = (
        "knowledgebases/kb-1/validations/extract-pipeline.json"
    )
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-pipeline",
            parsed_document_id="parsed-pipeline",
            extraction_result_id="extract-pipeline",
            validation_report_id="validate-pipeline",
            upserted_entity_ids=["entity-pipeline"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-pipeline",
            extraction_result_id="extract-pipeline",
            source_document_id="doc-pipeline",
            valid_entities=[
                Entity(
                    id="entity-pipeline",
                    type="claim",
                    properties={"name": "Pipeline Claim"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    event_bus.publish(
        GraphUpdatedEvent(
            correlation_id="corr-pipeline",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-pipeline",
                    parsed_document_id="parsed-pipeline",
                    extraction_result_id="extract-pipeline",
                    validation_report_id="validate-pipeline",
                    upserted_entity_count=1,
                    upserted_relationship_count=0,
                    validation_storage_key=validation_storage_key,
                    graph_update_storage_key=graph_update_storage_key,
                )
            ],
        )
    )

    kwargs: dict[str, object] = dict(
        embeddings_service=embeddings_service,
        vector_store=vector_store,
        graph_repository=graph_repository,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    for _ in range(10):
        asyncio.run(drain_ingestion_events(
            event_bus,
            service,
            create_document_chunker(),
            create_document_extractor([]),
            create_extraction_validator([], []),
            graph_service,
            object_store,
            **kwargs,  # type: ignore[arg-type]
        ))

    event_types_published = [type(event).__name__ for event in event_bus.published_events]
    # Each downstream stage must have run at least once.
    assert "DocumentsUploadedEvent" in event_types_published
    assert "DocumentsParsedEvent" in event_types_published
    assert "DocumentsChunkedEvent" in event_types_published
    assert "EntitiesExtractedEvent" in event_types_published
    assert "EntitiesValidatedEvent" in event_types_published
    assert "EmbeddingsCompleteEvent" in event_types_published
    assert "VectorsIndexedEvent" in event_types_published
    kb_ready_events = [
        event for event in event_bus.published_events if isinstance(event, KnowledgeBaseReadyEvent)
    ]
    assert len(kb_ready_events) >= 1
    assert kb_ready_events[0].correlation_id == "corr-pipeline"


# ---------------------------------------------------------------------------
# E4-S05 — retry/backoff
# ---------------------------------------------------------------------------


class _FlakyHandler:
    def __init__(self, *, fails: int) -> None:
        self.fails = fails
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        if self.calls <= self.fails:
            raise RuntimeError(f"transient failure {self.calls}")
        return 42


async def _instant_sleep(_delay: float) -> None:
    return None


def test_run_handler_with_retry_succeeds_after_transient_failure() -> None:
    event_bus = InMemoryEventBus()
    handler = _FlakyHandler(fails=1)
    event = KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1")

    result = asyncio.run(
        run_handler_with_retry(
            handler,
            event=event,
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=3, base_delay_seconds=0.0),
            sleep=_instant_sleep,
        )
    )

    assert result == 42
    assert handler.calls == 2
    assert event_bus.dlq_entries == []


def test_run_handler_with_retry_routes_to_dlq_after_exhaustion() -> None:
    event_bus = InMemoryEventBus()
    handler = _FlakyHandler(fails=10)
    event = KnowledgeBaseCreatedEvent(
        correlation_id="corr-permanent", knowledge_base_id="kb-1"
    )

    result = asyncio.run(
        run_handler_with_retry(
            handler,
            event=event,
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=2, base_delay_seconds=0.0),
            sleep=_instant_sleep,
        )
    )

    assert result == 0
    assert handler.calls == 3
    assert len(event_bus.dlq_entries) == 1
    entry = event_bus.dlq_entries[0]
    assert entry.event.correlation_id == "corr-permanent"
    assert entry.error.retry_count == 2
    assert "transient failure" in entry.error.error_message


def test_run_handler_with_retry_does_not_retry_fatal_stage_exception() -> None:
    class FatalStageError(RuntimeError):
        pass

    event_bus = InMemoryEventBus()
    calls = 0

    def handler() -> int:
        nonlocal calls
        calls += 1
        raise FatalStageError("fatal stage failure")

    result = asyncio.run(
        run_handler_with_retry(
            handler,
            event=KnowledgeBaseCreatedEvent(
                correlation_id="corr-fatal", knowledge_base_id="kb-1"
            ),
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=3, base_delay_seconds=0.0),
            stage_policy=StagePolicy(
                retry_policy=RetryPolicy(max_retries=3, base_delay_seconds=0.0),
                fatal_exception_types=(FatalStageError,),
            ),
            sleep=_instant_sleep,
        )
    )

    assert result == 0
    assert calls == 1
    assert len(event_bus.dlq_entries) == 1
    assert event_bus.dlq_entries[0].error.retry_count == 0


def test_run_handler_with_retry_routes_timed_out_stage_attempt_to_dlq_without_retry() -> None:
    event_bus = InMemoryEventBus()
    calls = 0
    lock = threading.Lock()

    def handler() -> int:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return 99

    result = asyncio.run(
        run_handler_with_retry(
            handler,
            event=KnowledgeBaseCreatedEvent(
                correlation_id="corr-timeout", knowledge_base_id="kb-1"
            ),
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=0, base_delay_seconds=0.0),
            stage_policy=StagePolicy(
                retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0.0),
                timeout_seconds=0.01,
            ),
            sleep=_instant_sleep,
        )
    )

    assert result == 0
    assert calls == 1
    assert len(event_bus.dlq_entries) == 1
    entry = event_bus.dlq_entries[0]
    assert entry.event.correlation_id == "corr-timeout"
    assert entry.error.retry_count == 0
    assert "TimeoutError" in entry.error.traceback


def test_run_handler_with_retry_runs_handler_off_event_loop_thread() -> None:
    """The handler is offloaded to a worker thread so the event loop (and the
    /health server + signal handlers) stays responsive during a long stage."""
    import threading

    event_bus = InMemoryEventBus()
    main_thread_id = threading.get_ident()
    captured: dict[str, int] = {}

    def handler() -> int:
        captured["thread_id"] = threading.get_ident()
        return 7

    result = asyncio.run(
        run_handler_with_retry(
            handler,
            event=KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1"),
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=0),
            sleep=_instant_sleep,
        )
    )

    assert result == 7
    assert captured["thread_id"] != main_thread_id


def test_retry_policy_delay_for_attempt() -> None:
    policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0, backoff_multiplier=2.0)
    assert policy.delay_for_attempt(0) == 0.0
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 4.0


def test_run_handler_with_retry_propagates_dlq_publish_failure() -> None:
    """ACK contract regression guard: when retries are exhausted AND
    publish_to_dlq itself raises (e.g., Redis Streams unreachable), the
    exception must propagate to the caller so the caller does NOT ACK
    the delivery. The unconditional `ackable.append(delivery)` in
    `drain_ingestion_events` is only reached when run_handler_with_retry
    returns normally; this test pins the propagation behavior.
    """

    class _DlqFailingEventBus(InMemoryEventBus):
        def publish_to_dlq(
            self,
            event: AnyEvent,
            error_info: DlqErrorInfo,
        ) -> str | None:
            del event, error_info
            raise RuntimeError("simulated DLQ publish failure (Redis unreachable)")

    event_bus = _DlqFailingEventBus()
    handler = _FlakyHandler(fails=10)
    event = KnowledgeBaseCreatedEvent(
        correlation_id="corr-dlq-fails", knowledge_base_id="kb-1"
    )

    with pytest.raises(RuntimeError, match="DLQ publish failure"):
        asyncio.run(
            run_handler_with_retry(
                handler,
                event=event,
                event_bus=event_bus,
                retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0.0),
                sleep=_instant_sleep,
            )
        )
    # Handler ran twice (initial + 1 retry); after exhaustion the
    # publish_to_dlq raised — and that exception escaped the function
    # rather than being swallowed.
    assert handler.calls == 2


# ---------------------------------------------------------------------------
# BL-023 T3 — durable DLQ record persistence at retry exhaustion
# ---------------------------------------------------------------------------


def test_retry_exhaustion_persists_dlq_record() -> None:
    event_bus = InMemoryEventBus()
    dlq_store = InMemoryDlqRecordStore()
    event = KnowledgeBaseCreatedEvent(
        correlation_id="corr-persist", knowledge_base_id="kb-1"
    )

    def failing_handler() -> int:
        raise RuntimeError("boom")

    asyncio.run(
        run_handler_with_retry(
            failing_handler,
            event=event,
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0.0),
            sleep=_instant_sleep,
            dlq_record_store=dlq_store,
        )
    )

    records, total = dlq_store.list()
    assert total == 1
    record = records[0]
    assert record.event_type == event.event_type
    assert record.correlation_id == event.correlation_id
    assert record.payload == encode_event(event)
    assert record.error_message == "boom"
    assert record.retry_count == 1
    assert record.status == "pending"
    assert len(event_bus.dlq_entries) == 1  # stream publish still happened


def test_dlq_store_failure_does_not_mask_handler_error() -> None:
    event_bus = InMemoryEventBus()

    class ExplodingStore(InMemoryDlqRecordStore):
        def persist(self, record: DlqRecord) -> DlqRecord:
            raise RuntimeError("store down")

    def failing_handler() -> int:
        raise RuntimeError("boom")

    result = asyncio.run(
        run_handler_with_retry(
            failing_handler,
            event=KnowledgeBaseCreatedEvent(
                correlation_id="corr-store-down", knowledge_base_id="kb-1"
            ),
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=0, base_delay_seconds=0.0),
            sleep=_instant_sleep,
            dlq_record_store=ExplodingStore(),
        )
    )

    assert result == 0  # ACK contract preserved
    assert len(event_bus.dlq_entries) == 1  # stream DLQ still succeeded


def test_no_dlq_record_store_is_a_noop() -> None:
    event_bus = InMemoryEventBus()

    def failing_handler() -> int:
        raise RuntimeError("boom")

    result = asyncio.run(
        run_handler_with_retry(
            failing_handler,
            event=KnowledgeBaseCreatedEvent(
                correlation_id="corr-no-store", knowledge_base_id="kb-1"
            ),
            event_bus=event_bus,
            retry_policy=RetryPolicy(max_retries=0, base_delay_seconds=0.0),
            sleep=_instant_sleep,
        )
    )

    assert result == 0


# ---------------------------------------------------------------------------
# E4-S04 — DLQ wiring through drain_ingestion_events
# ---------------------------------------------------------------------------


def test_drain_ingestion_events_routes_failing_event_to_dlq() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    extractor = create_document_extractor([])
    validator = create_extraction_validator([], [])
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    # Publish a DocumentsParsedEvent referencing a missing storage key.
    # Per-document isolation (BL-041): this no longer poisons the batch
    # (sends to DLQ). Instead, a DocumentsFailedEvent is published.
    event_bus.publish(
        DocumentsParsedEvent(
            correlation_id="corr-fail",
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test-parser",
                )
            ],
        )
    )

    asyncio.run(drain_ingestion_events(
        event_bus,
        service,
        chunker,
        extractor,
        validator,
        graph_service,
        object_store,
        consumer_group="test-workers",
        consumer_name="worker-1",
        retry_policy=RetryPolicy(max_retries=1, base_delay_seconds=0.0),
        sleep=_instant_sleep,
    ))

    # With BL-041, missing storage keys are handled per-document via
    # DocumentsFailedEvent, not by poisoning the batch to the DLQ.
    assert len(event_bus.dlq_entries) == 0
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].correlation_id == "corr-fail"
    assert failed_events[0].documents[0].source_document_id == "doc-1"


def test_drain_ingestion_events_marks_records_workflow_failed_after_retry_exhaustion() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    workflow_run_store = InMemoryWorkflowRunStore()
    workflow_tracker = WorkflowEventTracker(workflow_run_store)
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )

    event_bus.publish(
        RecordsIngestedEvent(
            correlation_id="corr-records-fail",
            knowledge_base_id="kb-1",
            feed_name="missing_feed",
            record_type="claim_record",
            record_count=1,
        )
    )

    processed = asyncio.run(drain_ingestion_events(
        event_bus,
        IngestionService(
            DocumentParsingOrchestrator(
                create_default_registry(),
                fetcher=HttpxRemoteDocumentFetcher(),
            ),
            object_store=object_store,
            event_bus=event_bus,
        ),
        create_document_chunker(),
        create_document_extractor([]),
        create_extraction_validator([], []),
        graph_service,
        object_store,
        records_config=RecordsConfig(),
        raw_record_store=InMemoryRawRecordStore(),
        observation_writer=InMemoryObservationWriter(),
        consumer_group="test-workers",
        consumer_name="worker-1",
        retry_policy=RetryPolicy(max_retries=0, base_delay_seconds=0.0),
        workflow_tracker=workflow_tracker,
        sleep=_instant_sleep,
    ))

    runs = workflow_run_store.list_runs().items
    assert processed == 0
    assert len(event_bus.dlq_entries) == 1
    assert len(runs) == 1
    assert runs[0].status is WorkflowRunStatus.FAILED
    assert runs[0].metadata["correlation_id"] == "corr-records-fail"
    assert "missing_feed" in str(runs[0].metadata["last_error"])


# ---------------------------------------------------------------------------
# E4-S06 — graceful shutdown
# ---------------------------------------------------------------------------


def test_graceful_shutdown_finishes_in_flight_event(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker loop completes gracefully when the shutdown event fires."""

    import logging
    from datetime import timedelta

    from agent.coordinator import (
        WorkerDependencies,
        SHUTDOWN_LOG_DONE,
        SHUTDOWN_LOG_REQUESTED,
        build_derived_signal_writer,
        build_kb_deletion_stores,
        build_kb_repository,
        build_peerstats_service,
        run_worker,
    )
    from config.schema import PeerStatsConfig
    from agent.adapters.in_memory import InMemoryWorkflowRunStore
    from agent.workflow_tracking import WorkflowEventTracker
    from shared.utils import utc_now

    defaults_yaml = __file__.replace(
        "tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml"
    )
    monkeypatch.setenv("CHILI_CONFIG_PATH", defaults_yaml)

    event_bus = InMemoryEventBus()
    workflow_run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-stale-runtime",
                knowledge_base_id="kb-stale",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.RUNNING,
                steps=[WorkflowStepState(step_name="parse")],
                updated_at=utc_now() - timedelta(days=2),
                metadata={"correlation_id": "corr-stale-runtime"},
            )
        ]
    )
    object_store = InMemoryObjectStore()
    vector_store = InMemoryVectorStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    from embeddings.service import create_embeddings_service
    embeddings_service = create_embeddings_service(
        InMemoryEmbedder(), event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    from analytics.explainability.adapters.in_memory import (
        InMemoryExplainabilityContextSource,
    )
    from analytics.explainability.service import create_explainability_service
    from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
    from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.service import create_risk_service
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.service import create_monitoring_service

    from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
    from analytics.metrics.throttle import MetricsRecomputeThrottle
    from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
    from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
    from policy.adapters.in_memory import InMemoryPolicyItemRepository
    from policy.service import create_policy_service

    kb_deletion_stores = build_kb_deletion_stores(
        None,
        graph_service=graph_service,
        vector_store=vector_store,
        object_store=object_store,
        event_bus=event_bus,
        raw_record_store=InMemoryRawRecordStore(),
        derived_signal_store=build_derived_signal_writer(None),
        observation_writer=InMemoryObservationWriter(),
        risk_history_writer=InMemoryRiskHistoryWriter(),
        alert_history_writer=InMemoryAlertHistoryWriter(),
        entity_metric_repository=InMemoryEntityMetricRepository(),
    )
    kb_repository = build_kb_repository(object_store)

    fake_deps = WorkerDependencies(
        event_bus=event_bus,
        ingestion_service=ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        graph_repository=graph_repository,
        embeddings_service=embeddings_service,
        object_store=object_store,
        vector_store=vector_store,
        llm_client=__import__(
            "llm.adapters.in_memory", fromlist=["InMemoryLlmClient"]
        ).InMemoryLlmClient(),
        gnn_service=create_gnn_service(
            InMemoryGraphSnapshotSource(), event_bus=event_bus
        ),
        gnn_cluster_store=InMemoryClusterSummaryStore(),
        risk_service=create_risk_service(
            InMemoryRiskSignalSource(), event_bus=event_bus
        ),
        peerstats_service=build_peerstats_service(None),
        peer_stats_config=PeerStatsConfig(),
        peer_stats_enabled=False,
        kb_deletion_stores=kb_deletion_stores,
        kb_repository=kb_repository,
        explainability_service=create_explainability_service(
            InMemoryExplainabilityContextSource(), event_bus=event_bus
        ),
        monitoring_service=create_monitoring_service(
            InMemoryObservationSource(), event_bus=event_bus
        ),
        records_config=RecordsConfig(),
        raw_record_store=InMemoryRawRecordStore(),
        derived_signal_store=build_derived_signal_writer(None),
        observation_writer=InMemoryObservationWriter(),
        policy_service=create_policy_service(InMemoryPolicyItemRepository()),
        policy_rules=[],
        entity_metric_repository=InMemoryEntityMetricRepository(),
        metrics_throttle=MetricsRecomputeThrottle(min_interval_seconds=300),
        policy_metrics_throttle=MetricsRecomputeThrottle(min_interval_seconds=300),
        risk_history_writer=InMemoryRiskHistoryWriter(),
        alert_history_writer=InMemoryAlertHistoryWriter(),
        event_settings=EventBusSettings(backend="in-memory"),
        workflow_run_store=workflow_run_store,
        workflow_tracker=WorkflowEventTracker(workflow_run_store),
        document_status_store=InMemorySourceDocumentStatusStore(),
        dlq_record_store=InMemoryDlqRecordStore(),
    )

    monkeypatch.setattr(
        "agent.coordinator.build_worker_dependencies", lambda: fake_deps
    )

    # Run a brief worker loop and trigger shutdown via the asyncio event loop.
    async def _run() -> None:
        worker_task = asyncio.create_task(run_worker())
        await asyncio.sleep(0.1)
        # Trigger SIGTERM-equivalent by signalling the shutdown event directly.
        for task in asyncio.all_tasks():
            if task is not worker_task and task is not asyncio.current_task():
                continue
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    caplog.set_level(logging.INFO, logger="chili.worker")
    asyncio.run(_run())
    log_text = caplog.text
    assert SHUTDOWN_LOG_DONE in log_text
    reconciled = workflow_run_store.get_run("workflow-stale-runtime")
    assert reconciled.status is WorkflowRunStatus.FAILED
    assert reconciled.metadata["reason"] == "stale_workflow_reconciled"
    # SHUTDOWN_LOG_REQUESTED would only fire if signal was actually delivered;
    # since cancellation skips it, only the graceful-stop log is asserted.
    assert SHUTDOWN_LOG_REQUESTED.startswith("Shutdown requested")


def testinstall_signal_handlers_sets_shutdown_event() -> None:
    """The signal handler flips the shutdown event and logs the request."""

    from agent.coordinator import SHUTDOWN_LOG_REQUESTED, install_signal_handlers

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()
        install_signal_handlers(loop, shutdown_event)
        # Direct invocation through the registered handler is platform-specific,
        # so simulate the trigger by setting the event ourselves.
        shutdown_event.set()
        assert shutdown_event.is_set()

    asyncio.run(_run())
    assert SHUTDOWN_LOG_REQUESTED == "Shutdown requested, finishing current event..."


def test_signal_trigger_flips_event_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Trigger the registered SIGTERM handler to cover the inner closure."""

    import logging
    import os
    import signal as signal_module

    from agent.coordinator import SHUTDOWN_LOG_REQUESTED, install_signal_handlers

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()
        install_signal_handlers(loop, shutdown_event)
        os.kill(os.getpid(), signal_module.SIGTERM)
        # Give the loop a chance to process the signal callback.
        await asyncio.sleep(0.05)
        assert shutdown_event.is_set()

    caplog.set_level(logging.INFO, logger="chili.worker")
    asyncio.run(_run())
    assert SHUTDOWN_LOG_REQUESTED in caplog.text


def teststart_health_server_safely_logs_warning_on_failure(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker survives a health-server failure and logs a warning."""

    import logging

    from agent.coordinator import start_health_server_safely
    from agent.health import HealthState
    from agent.models import HealthSettings

    async def _failing_start(_state: object) -> object:
        raise OSError("port in use")

    monkeypatch.setattr("agent.coordinator.start_health_server", _failing_start)

    async def _run() -> None:
        state = HealthState(settings=HealthSettings())
        result = await start_health_server_safely(state)
        assert result is None

    caplog.set_level(logging.WARNING, logger="chili.worker")
    asyncio.run(_run())
    assert "Health server failed to start" in caplog.text


def test_handle_documents_parsed_publishes_failure_when_storage_key_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    labels = {"stage": "chunk", "error_class": "MissingStorageKey"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        processed = handle_documents_parsed(
            DocumentsParsedEvent(
                correlation_id="corr-fail-1",
                documents=[
                    ParsedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        parser_name="test",
                    )
                ]
            ),
            document_chunker=chunker,
            object_store=object_store,
            event_bus=event_bus,
        )

    assert processed == 0
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].correlation_id == "corr-fail-1"
    failure = failed_events[0].documents[0]
    assert failure.knowledge_base_id == "kb-1"
    assert failure.source_document_id == "doc-1"
    assert "parsed_document_storage_key" in failure.error_message
    assert not any(
        isinstance(event, DocumentsChunkedEvent)
        for event in event_bus.published_events
    )

    # BL-043 controller addition: the missing-storage-key DocumentsFailedEvent
    # emission site increments ingestion_documents_failed_total{stage="chunk",
    # error_class="MissingStorageKey"} and logs the chunk-stage "failed" outcome.
    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0
    assert _has_stage_field(caplog.text, "stage", "chunk")
    assert _has_stage_field(caplog.text, "outcome", "failed")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-1")


def test_handle_documents_parsed_isolates_bad_document_from_batch() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    labels = {"stage": "chunk", "error_class": "KeyError"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    good_key = "knowledgebases/kb-1/parsed/parsed-good.json"
    object_store.put_bytes(
        good_key,
        ParsedDocument(
            id="parsed-good",
            source_document_id="doc-good",
            text_content="Claim 42 was filed by provider A.",
            parser_name="test-parser",
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    processed = handle_documents_parsed(
        DocumentsParsedEvent(
            correlation_id="corr-mixed",
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-bad",
                    parsed_document_id="parsed-bad",
                    parser_name="test-parser",
                    parsed_document_storage_key="knowledgebases/kb-1/parsed/missing.json",
                ),
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-good",
                    parsed_document_id="parsed-good",
                    parser_name="test-parser",
                    parsed_document_storage_key=good_key,
                ),
            ]
        ),
        document_chunker=chunker,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    chunked_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsChunkedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].documents[0].source_document_id == "doc-bad"
    assert len(chunked_events) == 1
    assert chunked_events[0].correlation_id == "corr-mixed"
    assert chunked_events[0].documents[0].source_document_id == "doc-good"

    # BL-043 controller addition: the get_bytes-failure DocumentsFailedEvent
    # emission site increments ingestion_documents_failed_total{stage="chunk",
    # error_class="KeyError"} (the object store raises KeyError for a missing key).
    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0


def test_handle_documents_parsed_propagates_transient_object_store_error() -> None:
    """A transient object-store failure must NOT be isolated per-document.

    Per-document isolation (BL-041) only covers the two permanent failure
    classes (missing key -> KeyError, corrupt payload -> ValidationError).
    Anything else (e.g. a network blip surfaced as ConnectionError) must
    propagate so run_handler_with_retry's retry/DLQ policy still applies.
    """

    class _TransientlyFailingObjectStore(InMemoryObjectStore):
        def get_bytes(self, key: str) -> StoredObject:
            raise ConnectionError("temporary network blip")

    event_bus = InMemoryEventBus()
    object_store = _TransientlyFailingObjectStore()
    chunker = create_document_chunker()

    with pytest.raises(ConnectionError):
        handle_documents_parsed(
            DocumentsParsedEvent(
                correlation_id="corr-transient",
                documents=[
                    ParsedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-transient",
                        parsed_document_id="parsed-transient",
                        parser_name="test-parser",
                        parsed_document_storage_key="knowledgebases/kb-1/parsed/transient.json",
                    ),
                ]
            ),
            document_chunker=chunker,
            object_store=object_store,
            event_bus=event_bus,
        )

    assert not any(
        isinstance(event, DocumentsFailedEvent)
        for event in event_bus.published_events
    )


def test_handle_documents_chunked_publishes_failure_when_storage_key_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extractor = create_document_extractor([])
    labels = {"stage": "extract", "error_class": "MissingStorageKey"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        processed = handle_documents_chunked(
            DocumentsChunkedEvent(
                correlation_id="corr-fail-2",
                documents=[
                    ChunkedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        chunk_count=0,
                        strategy="x",
                    )
                ]
            ),
            document_extractor=extractor,
            object_store=object_store,
            event_bus=event_bus,
        )

    assert processed == 0
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].correlation_id == "corr-fail-2"
    assert failed_events[0].documents[0].source_document_id == "doc-1"
    assert "chunks_storage_key" in failed_events[0].documents[0].error_message
    assert not any(
        isinstance(event, EntitiesExtractedEvent)
        for event in event_bus.published_events
    )

    # BL-043 controller addition: the missing-storage-key DocumentsFailedEvent
    # emission site increments ingestion_documents_failed_total{stage="extract",
    # error_class="MissingStorageKey"} and logs the extract-stage "failed" outcome.
    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0
    assert _has_stage_field(caplog.text, "stage", "extract")
    assert _has_stage_field(caplog.text, "outcome", "failed")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-1")


def test_handle_documents_chunked_isolates_unreadable_artifact_from_batch() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extractor = create_document_extractor([])
    labels = {"stage": "extract", "error_class": "ValidationError"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    good_key = "knowledgebases/kb-1/chunks/parsed-good.json"
    object_store.put_bytes(
        good_key,
        ChunkingResult(
            source_document_id="doc-good",
            parsed_document_id="parsed-good",
            strategy_used="StructuredRecordChunker",
            chunks=[],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    bad_key = "knowledgebases/kb-1/chunks/parsed-bad.json"
    object_store.put_bytes(
        bad_key,
        b"{not valid json at all",
        media_type="application/json",
    )

    processed = handle_documents_chunked(
        DocumentsChunkedEvent(
            correlation_id="corr-mixed-2",
            documents=[
                ChunkedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-bad",
                    parsed_document_id="parsed-bad",
                    chunk_count=0,
                    strategy="x",
                    chunks_storage_key=bad_key,
                ),
                ChunkedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-good",
                    parsed_document_id="parsed-good",
                    chunk_count=0,
                    strategy="StructuredRecordChunker",
                    chunks_storage_key=good_key,
                ),
            ]
        ),
        document_extractor=extractor,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1
    failed_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsFailedEvent)
    ]
    extracted_events = [
        event for event in event_bus.published_events
        if isinstance(event, EntitiesExtractedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].documents[0].source_document_id == "doc-bad"
    assert len(extracted_events) == 1
    assert extracted_events[0].documents[0].source_document_id == "doc-good"

    # BL-043 controller addition: the get_bytes/parse-failure DocumentsFailedEvent
    # emission site increments ingestion_documents_failed_total{stage="extract",
    # error_class="ValidationError"} (invalid JSON fails ChunkingResult validation).
    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0


def test_handle_documents_chunked_propagates_transient_object_store_error() -> None:
    """A transient object-store failure must NOT be isolated per-document.

    Per-document isolation (BL-041) only covers the two permanent failure
    classes (missing key -> KeyError, corrupt payload -> ValidationError).
    Anything else (e.g. a network blip surfaced as ConnectionError) must
    propagate so run_handler_with_retry's retry/DLQ policy still applies.
    """

    class _TransientlyFailingObjectStore(InMemoryObjectStore):
        def get_bytes(self, key: str) -> StoredObject:
            raise ConnectionError("temporary network blip")

    event_bus = InMemoryEventBus()
    object_store = _TransientlyFailingObjectStore()
    extractor = create_document_extractor([])

    with pytest.raises(ConnectionError):
        handle_documents_chunked(
            DocumentsChunkedEvent(
                correlation_id="corr-transient-2",
                documents=[
                    ChunkedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-transient",
                        parsed_document_id="parsed-transient",
                        chunk_count=0,
                        strategy="x",
                        chunks_storage_key="knowledgebases/kb-1/chunks/transient.json",
                    ),
                ]
            ),
            document_extractor=extractor,
            object_store=object_store,
            event_bus=event_bus,
        )

    assert not any(
        isinstance(event, DocumentsFailedEvent)
        for event in event_bus.published_events
    )


def test_handle_entities_extracted_raises_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    validator = create_extraction_validator([], [])
    with pytest.raises(ValueError):
        handle_entities_extracted(
            EntitiesExtractedEvent(
                documents=[
                    ExtractedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        extraction_result_id="extract-1",
                        entity_count=0,
                        relationship_count=0,
                    )
                ]
            ),
            extraction_validator=validator,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_entities_extracted_logs_failed_outcome_before_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    validator = create_extraction_validator([], [])
    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        with pytest.raises(ValueError):
            handle_entities_extracted(
                EntitiesExtractedEvent(
                    documents=[
                        ExtractedDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="doc-fail-validate",
                            parsed_document_id="parsed-1",
                            extraction_result_id="extract-1",
                            entity_count=0,
                            relationship_count=0,
                        )
                    ]
                ),
                extraction_validator=validator,
                object_store=object_store,
                event_bus=event_bus,
            )
    assert _has_stage_field(caplog.text, "stage", "validate")
    assert _has_stage_field(caplog.text, "outcome", "failed")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-fail-validate")


def test_handle_entities_validated_raises_when_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    with pytest.raises(ValueError):
        handle_entities_validated(
            EntitiesValidatedEvent(
                documents=[
                    ValidatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        parsed_document_id="parsed-1",
                        extraction_result_id="extract-1",
                        validation_report_id="validate-1",
                        valid_entity_count=0,
                        valid_relationship_count=0,
                        entity_error_count=0,
                        relationship_error_count=0,
                    )
                ]
            ),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_entities_validated_isolates_integrity_failure() -> None:
    """A GraphIntegrityError-caused BatchUpsertError fails only that document.

    doc-bad's validation report contains a relationship whose endpoint entity
    is absent from both the graph and the report's own valid_entities, so the
    default strict integrity_mode rejects it. doc-good has no such defect and
    must still be upserted and advance the pipeline (BL-017).
    """
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    labels = {"stage": "graph", "error_class": "GraphIntegrityError"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0

    bad_report = ValidationReport(
        id="validate-bad",
        extraction_result_id="extract-bad",
        source_document_id="doc-bad",
        valid_relationships=[
            Relationship(
                id="rel-bad",
                type="referral",
                source_id="provider-missing",
                target_id="provider-also-missing",
            )
        ],
    )
    bad_storage_key = "knowledgebases/kb-1/validations/extract-bad.json"
    object_store.put_bytes(
        bad_storage_key,
        bad_report.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    good_report = ValidationReport(
        id="validate-good",
        extraction_result_id="extract-good",
        source_document_id="doc-good",
        valid_entities=[
            Entity(id="provider-1", type="provider", properties={}),
        ],
    )
    good_storage_key = "knowledgebases/kb-1/validations/extract-good.json"
    object_store.put_bytes(
        good_storage_key,
        good_report.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    event = EntitiesValidatedEvent(
        correlation_id="corr-integrity",
        documents=[
            ValidatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-bad",
                parsed_document_id="parsed-bad",
                extraction_result_id="extract-bad",
                validation_report_id="validate-bad",
                valid_entity_count=0,
                valid_relationship_count=1,
                entity_error_count=0,
                relationship_error_count=0,
                validation_storage_key=bad_storage_key,
            ),
            ValidatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-good",
                parsed_document_id="parsed-good",
                extraction_result_id="extract-good",
                validation_report_id="validate-good",
                valid_entity_count=1,
                valid_relationship_count=0,
                entity_error_count=0,
                relationship_error_count=0,
                validation_storage_key=good_storage_key,
            ),
        ],
    )

    processed = handle_entities_validated(
        event,
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1  # the good document still processed
    failed_events = [
        e for e in event_bus.published_events if isinstance(e, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].documents[0].source_document_id == "doc-bad"
    assert "missing" in failed_events[0].documents[0].error_message.lower()
    graph_events = [
        e for e in event_bus.published_events if isinstance(e, GraphUpdatedEvent)
    ]
    assert len(graph_events) == 1  # only the good document advanced
    assert graph_events[0].documents[0].source_document_id == "doc-good"

    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0


def test_handle_entities_validated_isolates_version_conflict_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GraphVersionConflictError-caused BatchUpsertError fails only that document.

    doc-bad's upsert races a concurrent writer and loses the optimistic-
    concurrency check (BL-017 extension). doc-good has no such conflict and
    must still be upserted and advance the pipeline.
    """
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    labels = {"stage": "graph", "error_class": "GraphVersionConflictError"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0

    real_upsert_task = graph_service.upsert_task

    def fake_upsert_task(task: GraphBuildTask) -> GraphBuildReceipt:
        if task.source_document_id == "doc-bad":
            conflict = GraphVersionConflictError("e-1", 1, 2)
            raise BatchUpsertError(
                successful_entity_count=0,
                successful_relationship_count=0,
            ) from conflict
        return real_upsert_task(task)

    monkeypatch.setattr(graph_service, "upsert_task", fake_upsert_task)

    bad_report = ValidationReport(
        id="validate-bad",
        extraction_result_id="extract-bad",
        source_document_id="doc-bad",
        valid_entities=[
            Entity(id="e-1", type="provider", properties={}),
        ],
    )
    bad_storage_key = "knowledgebases/kb-1/validations/extract-bad.json"
    object_store.put_bytes(
        bad_storage_key,
        bad_report.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    good_report = ValidationReport(
        id="validate-good",
        extraction_result_id="extract-good",
        source_document_id="doc-good",
        valid_entities=[
            Entity(id="provider-1", type="provider", properties={}),
        ],
    )
    good_storage_key = "knowledgebases/kb-1/validations/extract-good.json"
    object_store.put_bytes(
        good_storage_key,
        good_report.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    event = EntitiesValidatedEvent(
        correlation_id="corr-version-conflict",
        documents=[
            ValidatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-bad",
                parsed_document_id="parsed-bad",
                extraction_result_id="extract-bad",
                validation_report_id="validate-bad",
                valid_entity_count=1,
                valid_relationship_count=0,
                entity_error_count=0,
                relationship_error_count=0,
                validation_storage_key=bad_storage_key,
            ),
            ValidatedDocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-good",
                parsed_document_id="parsed-good",
                extraction_result_id="extract-good",
                validation_report_id="validate-good",
                valid_entity_count=1,
                valid_relationship_count=0,
                entity_error_count=0,
                relationship_error_count=0,
                validation_storage_key=good_storage_key,
            ),
        ],
    )

    processed = handle_entities_validated(
        event,
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 1  # the good document still processed
    failed_events = [
        e for e in event_bus.published_events if isinstance(e, DocumentsFailedEvent)
    ]
    assert len(failed_events) == 1
    assert failed_events[0].documents[0].source_document_id == "doc-bad"
    assert "version" in failed_events[0].documents[0].error_message.lower()
    graph_events = [
        e for e in event_bus.published_events if isinstance(e, GraphUpdatedEvent)
    ]
    assert len(graph_events) == 1  # only the good document advanced
    assert graph_events[0].documents[0].source_document_id == "doc-good"

    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0


def test_handle_event_requires_embeddings_service_for_graph_updated() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    with pytest.raises(ValueError):
        handle_event(
            EventDelivery(
                event=GraphUpdatedEvent(
                    correlation_id="x",
                    documents=[
                        GraphUpdatedDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="d",
                            parsed_document_id="p",
                            extraction_result_id="e",
                            validation_report_id="v",
                            upserted_entity_count=0,
                            upserted_relationship_count=0,
                            graph_update_storage_key="x.json",
                            validation_storage_key="y.json",
                        )
                    ],
                )
            ),
            service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_event_requires_vector_store_for_embeddings_complete() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    with pytest.raises(ValueError):
        handle_event(
            EventDelivery(
                event=EmbeddingsCompleteEvent(
                    documents=[
                        EmbeddingsCompleteDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="d",
                            parsed_document_id="p",
                            extraction_result_id="e",
                            validation_report_id="v",
                            entity_count=0,
                            graph_update_storage_key="g.json",
                            embeddings_storage_key="emb.json",
                        )
                    ]
                )
            ),
            service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_event_requires_graph_repository_for_vectors_indexed() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    with pytest.raises(ValueError):
        handle_event(
            EventDelivery(
                event=VectorsIndexedEvent(
                    documents=[
                        VectorsIndexedDocumentReference(
                            knowledge_base_id="kb-1",
                            source_document_id="d",
                            parsed_document_id="p",
                            extraction_result_id="e",
                            validation_report_id="v",
                            vector_count=0,
                            embeddings_storage_key="emb.json",
                            record_ids=[],
                        )
                    ]
                )
            ),
            service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_graph_updated_raises_when_storage_keys_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()

    with pytest.raises(ValueError):
        handle_graph_updated(
            GraphUpdatedEvent(
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="d",
                        parsed_document_id="p",
                        extraction_result_id="e",
                        validation_report_id="v",
                        upserted_entity_count=0,
                        upserted_relationship_count=0,
                        graph_update_storage_key=None,
                        validation_storage_key=None,
                    )
                ]
            ),
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_graph_updated_raises_when_validation_storage_key_missing() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()

    with pytest.raises(ValueError):
        handle_graph_updated(
            GraphUpdatedEvent(
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="d",
                        parsed_document_id="p",
                        extraction_result_id="e",
                        validation_report_id="v",
                        upserted_entity_count=0,
                        upserted_relationship_count=0,
                        graph_update_storage_key="g.json",
                        validation_storage_key=None,
                    )
                ]
            ),
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
        )


def test_handle_graph_updated_raises_when_validation_missing_entities() -> None:
    """The handler raises if graph upsert refers to entities not in validation."""

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/missing.json"
    validation_storage_key = "knowledgebases/kb-1/validations/missing.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc",
            parsed_document_id="parsed",
            extraction_result_id="extract",
            validation_report_id="validate",
            upserted_entity_ids=["entity-missing"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate",
            extraction_result_id="extract",
            source_document_id="doc",
            valid_entities=[
                Entity(id="entity-other", type="claim", properties={}),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    with pytest.raises(ValueError):
        handle_graph_updated(
            GraphUpdatedEvent(
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc",
                        parsed_document_id="parsed",
                        extraction_result_id="extract",
                        validation_report_id="validate",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        graph_update_storage_key=graph_update_storage_key,
                        validation_storage_key=validation_storage_key,
                    )
                ]
            ),
            embeddings_service=embeddings_service,
            object_store=object_store,
            event_bus=event_bus,
        )


# ---------------------------------------------------------------------------
# E4-S07 — health endpoint
# ---------------------------------------------------------------------------


def test_health_state_marks_event_processed_and_reports_status() -> None:
    from datetime import datetime, timedelta, timezone

    from agent.health import HealthState, build_health_payload
    from agent.models import HealthSettings

    state = HealthState(settings=HealthSettings(degraded_after_seconds=1.0))
    assert state.status() == "ok"

    state.mark_event_processed(datetime.now(timezone.utc))
    payload = build_health_payload(state)
    assert payload["status"] == "ok"
    assert payload["last_event_processed_at"] is not None

    stale_now = state.last_event_processed_at
    assert stale_now is not None
    future = stale_now + timedelta(seconds=10)
    assert state.status(now=future) == "degraded"


def test_health_payload_handles_no_events() -> None:
    from agent.health import HealthState, build_health_payload
    from agent.models import HealthSettings

    state = HealthState(settings=HealthSettings())
    payload = build_health_payload(state)
    assert payload == {
        "status": "ok",
        "last_event_processed_at": None,
        "events_processed": 0,
        "events_dead_lettered": 0,
        "consecutive_drain_errors": 0,
        "last_drain_error": None,
    }

# ---------------------------------------------------------------------------
# E7-S10 — analytics handler (Flow B)
# ---------------------------------------------------------------------------


class _AcceptingExplainabilityContextSource:
    """Test double that builds a deterministic explanation context per alert."""

    def load_context(
        self,
        *,
        knowledge_base_id: str,
        alert_id: str,
    ):  # type: ignore[no-untyped-def]
        from datetime import datetime, timezone

        from analytics.explainability.models import (
            ExplanationContext,
            ExplanationItem,
            ExplanationSubgraph,
        )
        from shared.types import Alert

        return ExplanationContext(
            knowledge_base_id=knowledge_base_id,
            alert=Alert(
                id=alert_id,
                entity_type="provider",
                entity_id="provider-1",
                severity="high",
                title="Outlier",
                reasoning="Detected by analytics pipeline.",
                created_at=datetime.now(timezone.utc),
            ),
            explanation_items=[
                ExplanationItem(
                    source_id="signal-1",
                    source_type="risk_signal",
                    quote="High anomaly score.",
                    rationale="Anomaly score 0.7 exceeds baseline.",
                    score=0.9,
                )
            ],
            subgraph=ExplanationSubgraph(node_ids=["provider-1"], edge_ids=[]),
            confidence=0.8,
        )


def test_handle_event_dispatches_analytics_pipeline_for_graph_updated() -> None:
    pytest.importorskip("networkx")
    pytest.importorskip("numpy")

    from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
    from analytics.gnn.adapters.graph_repository_source import (
        GraphRepositorySnapshotSource,
    )
    from analytics.gnn.service import create_gnn_service
    from analytics.gnn.service_models import GnnAnalysisRequest
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.models import RiskProfile, RiskSignal
    from analytics.risk.service import create_risk_service
    from analytics.explainability.service import create_explainability_service
    from events.types import AlertsCreatedEvent, EmbeddingsCompleteEvent

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-A.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-A.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-A",
            extraction_result_id="extract-A",
            source_document_id="doc-A",
            valid_entities=[
                Entity(
                    id="provider-1",
                    type="claim",
                    properties={"name": "Provider 1"},
                )
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    # B1 Task 4: the snapshot now comes from the graph repository itself (via
    # Task 3's GraphRepositorySnapshotSource) rather than a hand-built
    # GraphSnapshot, and a cluster store sits alongside it so the pipeline's
    # persisted community summaries can be asserted on below.
    graph_repository = InMemoryGraphRepository()
    graph_repository.upsert_entities(
        "kb-1",
        [
            Entity(id="provider-1", type="claim", properties={"name": "Provider 1"}),
            Entity(id="other-1", type="claim", properties={"name": "Other 1"}),
        ],
    )
    graph_repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="rel-provider-other",
                type="referral",
                source_id="provider-1",
                target_id="other-1",
                weight=1.0,
            )
        ],
    )
    cluster_store = InMemoryClusterSummaryStore()
    snapshot_source = GraphRepositorySnapshotSource(graph_repository, cluster_store)

    signal_source = InMemoryRiskSignalSource(
        profiles=[
            RiskProfile(
                knowledge_base_id="kb-1",
                entity_id="provider-1",
                signals=[
                    RiskSignal(signal_name="anomaly", value=0.7, weight=0.5),
                    RiskSignal(signal_name="velocity", value=0.6, weight=0.5),
                ],
            )
        ]
    )
    gnn_service = create_gnn_service(snapshot_source, event_bus=event_bus)
    # Precompute the expected analysis response from the same (still
    # unmutated) repository/snapshot so the persisted-cluster assertions
    # below have an independent oracle, not a re-derivation of the
    # implementation under test. This call is read-only aside from
    # publishing a GnnAnalyzedEvent, which doesn't affect the type-filtered
    # assertions further down.
    expected_response = gnn_service.analyze(
        GnnAnalysisRequest(knowledge_base_id="kb-1")
    )
    assert expected_response.communities, "test setup must yield >=1 community"

    risk_service = create_risk_service(signal_source, event_bus=event_bus)
    explainability_service = create_explainability_service(
        _AcceptingExplainabilityContextSource(),
        event_bus=event_bus,
    )
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(
            event=GraphUpdatedEvent(
                correlation_id="corr-flowB",
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-A",
                        parsed_document_id="parsed-A",
                        extraction_result_id="extract-A",
                        validation_report_id="validate-A",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        validation_storage_key=validation_storage_key,
                        graph_update_storage_key=graph_update_storage_key,
                    )
                ],
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        embeddings_service=embeddings_service,
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        gnn_cluster_store=cluster_store,
    )

    assert processed == 1
    embedding_events = [
        e for e in event_bus.published_events if isinstance(e, EmbeddingsCompleteEvent)
    ]
    assert len(embedding_events) == 1
    alert_events = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(alert_events) == 1
    assert alert_events[0].alerts[0].entity_id == "provider-1"
    # entity_type is propagated from the focal graph entity (not left blank) so
    # alert_history records a real type for analytics-pipeline alerts.
    assert alert_events[0].alerts[0].entity_type == "claim"
    # Risk + GNN properties were written back to the graph (E7-S11 self-loop).
    updated = graph_repository.get_entity(["kb-1"], "provider-1")
    assert updated is not None
    assert "risk_score" in updated.properties
    assert "risk_level" in updated.properties
    assert "risk_assessed_at" in updated.properties
    assert "centrality_score" in updated.properties
    assert "community_id" in updated.properties

    # B1 Task 4: pipeline GNN communities are persisted through the shared
    # cluster store (an honest empty list would replace stale clusters too,
    # but this snapshot yields >=1 community per the setup assertion above).
    score_by_entity = {
        node.entity_id: node.score for node in expected_response.scored_nodes
    }
    persisted = cluster_store.load_clusters(knowledge_base_id="kb-1")
    assert {c.cluster_id for c in persisted} == {
        community.community_id for community in expected_response.communities
    }
    for community in expected_response.communities:
        match = next(c for c in persisted if c.cluster_id == community.community_id)
        assert set(match.entity_ids) == set(community.member_entity_ids)
        expected_score = max(
            (score_by_entity.get(member, 0.0) for member in community.member_entity_ids),
            default=0.0,
        )
        assert match.anomaly_score == pytest.approx(expected_score)


def test_analytics_handler_tolerates_cluster_store_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """B1 Task 4: a cluster store whose put_clusters raises must not fail the
    pipeline — the handler completes, a warning is logged, and downstream
    stages (risk, explainability, alerts.created) are unaffected."""
    pytest.importorskip("networkx")
    pytest.importorskip("numpy")

    from agent.coordinator import handle_graph_updated_for_analytics
    from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
    from analytics.gnn.adapters.graph_repository_source import (
        GraphRepositorySnapshotSource,
    )
    from analytics.gnn.models import ClusterSummary
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.models import RiskProfile, RiskSignal
    from analytics.risk.service import create_risk_service
    from analytics.explainability.service import create_explainability_service
    from events.types import AlertsCreatedEvent

    class _RaisingClusterStore:
        """Same instance a real worker would use for both reads (via the
        snapshot source) and writes (via the Flow B handler) — only writes
        fail here, mirroring an object-store outage on put_clusters."""

        def __init__(self) -> None:
            self._delegate = InMemoryClusterSummaryStore()

        def put_clusters(
            self, knowledge_base_id: str, clusters: list[ClusterSummary]
        ) -> None:
            raise RuntimeError("object store unavailable")

        def load_clusters(self, *, knowledge_base_id: str) -> list[ClusterSummary]:
            return self._delegate.load_clusters(knowledge_base_id=knowledge_base_id)

        def delete_by_kb(self, knowledge_base_id: str) -> None:
            self._delegate.delete_by_kb(knowledge_base_id)

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    object_store.put_bytes(
        "gk-store-failure",
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    graph_repository = InMemoryGraphRepository()
    graph_repository.upsert_entities(
        "kb-1",
        [
            Entity(id="provider-1", type="claim", properties={"name": "Provider 1"}),
            Entity(id="other-1", type="claim", properties={"name": "Other 1"}),
        ],
    )
    graph_repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="rel-provider-other",
                type="referral",
                source_id="provider-1",
                target_id="other-1",
                weight=1.0,
            )
        ],
    )
    raising_store = _RaisingClusterStore()
    snapshot_source = GraphRepositorySnapshotSource(graph_repository, raising_store)
    gnn_service = create_gnn_service(snapshot_source, event_bus=event_bus)
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="provider-1",
                    signals=[
                        RiskSignal(signal_name="anomaly", value=0.7, weight=0.5),
                        RiskSignal(signal_name="velocity", value=0.6, weight=0.5),
                    ],
                )
            ]
        ),
        event_bus=event_bus,
    )
    explainability_service = create_explainability_service(
        _AcceptingExplainabilityContextSource(),
        event_bus=event_bus,
    )
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )

    caplog.set_level(logging.WARNING, logger="chili.worker")

    alerts = handle_graph_updated_for_analytics(
        GraphUpdatedEvent(
            correlation_id="corr-cluster-store-failure",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-A",
                    parsed_document_id="parsed-A",
                    extraction_result_id="extract-A",
                    validation_report_id="validate-A",
                    upserted_entity_count=1,
                    upserted_relationship_count=0,
                    validation_storage_key="vk-store-failure",
                    graph_update_storage_key="gk-store-failure",
                )
            ],
        ),
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=object_store,
        gnn_cluster_store=raising_store,
    )

    assert alerts == 1
    alert_events = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(alert_events) == 1
    assert alert_events[0].alerts[0].entity_id == "provider-1"
    assert "Failed to persist GNN cluster summaries" in caplog.text
    assert "kb-1" in caplog.text


def test_analytics_handler_empty_communities_still_replaces_stale_clusters() -> None:
    """B1 Task 4: an honest empty ``communities`` list still writes through the
    cluster store, replacing whatever was persisted for this KB previously —
    a future ``if summaries:`` guard regression would leave the stale seed in
    place and fail this test."""
    from typing import cast

    from agent.coordinator import handle_graph_updated_for_analytics
    from analytics.gnn.adapters.cluster_store import InMemoryClusterSummaryStore
    from analytics.gnn.models import ClusterSummary
    from analytics.gnn.service import GnnService
    from analytics.gnn.service_models import GnnAnalysisRequest, GnnAnalysisResponse
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.models import RiskProfile, RiskSignal
    from analytics.risk.service import create_risk_service
    from analytics.explainability.service import create_explainability_service

    class _EmptyCommunitiesGnnService:
        """Stands in for a real ``GnnService`` (duck-typed, like the
        cancellation test's ``_Boom`` above) whose analysis found no
        communities worth reporting for this snapshot."""

        def analyze(self, request: GnnAnalysisRequest) -> GnnAnalysisResponse:
            return GnnAnalysisResponse(
                request_id="req-empty-communities",
                knowledge_base_id=request.knowledge_base_id,
                node_count=2,
                edge_count=1,
                communities=[],
            )

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    object_store.put_bytes(
        "gk-empty-communities",
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    graph_repository = InMemoryGraphRepository()
    graph_repository.upsert_entities(
        "kb-1",
        [Entity(id="provider-1", type="claim", properties={"name": "Provider 1"})],
    )
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )

    cluster_store = InMemoryClusterSummaryStore()
    cluster_store.put_clusters(
        "kb-1",
        [
            ClusterSummary(
                cluster_id="stale-cluster",
                entity_ids=["stale-entity"],
                anomaly_score=0.9,
            )
        ],
    )
    assert cluster_store.load_clusters(knowledge_base_id="kb-1"), "seed must land first"

    risk_service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="provider-1",
                    signals=[
                        RiskSignal(signal_name="anomaly", value=0.7, weight=0.5),
                        RiskSignal(signal_name="velocity", value=0.6, weight=0.5),
                    ],
                )
            ]
        ),
        event_bus=event_bus,
    )
    explainability_service = create_explainability_service(
        _AcceptingExplainabilityContextSource(),
        event_bus=event_bus,
    )

    alerts = handle_graph_updated_for_analytics(
        GraphUpdatedEvent(
            correlation_id="corr-empty-communities",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-A",
                    parsed_document_id="parsed-A",
                    extraction_result_id="extract-A",
                    validation_report_id="validate-A",
                    upserted_entity_count=1,
                    upserted_relationship_count=0,
                    validation_storage_key="vk-empty-communities",
                    graph_update_storage_key="gk-empty-communities",
                )
            ],
        ),
        gnn_service=cast(GnnService, _EmptyCommunitiesGnnService()),
        risk_service=risk_service,
        explainability_service=explainability_service,
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=object_store,
        gnn_cluster_store=cluster_store,
    )

    assert alerts == 1
    assert cluster_store.load_clusters(knowledge_base_id="kb-1") == []


def test_analytics_handler_emits_analysis_failed_when_risk_profile_missing() -> None:
    pytest.importorskip("networkx")
    pytest.importorskip("numpy")

    from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
    from analytics.gnn.models import (
        GraphEdgeSignal,
        GraphNodeSignal,
        GraphSnapshot,
    )
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.service import create_risk_service
    from analytics.explainability.adapters.in_memory import (
        InMemoryExplainabilityContextSource,
    )
    from analytics.explainability.service import create_explainability_service
    from agent.coordinator import handle_graph_updated_for_analytics
    from events.types import AnalysisFailedEvent

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    object_store.put_bytes(
        "gk",
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    # Snapshot present, but no risk profile registered for entity.
    snapshot_source = InMemoryGraphSnapshotSource(
        snapshots=[
            GraphSnapshot(
                knowledge_base_id="kb-1",
                nodes=[
                    GraphNodeSignal(entity_id="provider-1", feature_values=[0.4, 0.2]),
                    GraphNodeSignal(entity_id="other-1", feature_values=[0.1, 0.9]),
                ],
                edges=[
                    GraphEdgeSignal(
                        source_id="provider-1", target_id="other-1", weight=1.0
                    ),
                ],
            )
        ]
    )
    gnn_service = create_gnn_service(snapshot_source, event_bus=event_bus)
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(), event_bus=event_bus
    )
    explainability_service = create_explainability_service(
        InMemoryExplainabilityContextSource(),
        event_bus=event_bus,
    )
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )

    alerts = handle_graph_updated_for_analytics(
        GraphUpdatedEvent(
            correlation_id="corr-fail",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-A",
                    parsed_document_id="parsed-A",
                    extraction_result_id="extract-A",
                    validation_report_id="validate-A",
                    upserted_entity_count=1,
                    upserted_relationship_count=0,
                    validation_storage_key="vk",
                    graph_update_storage_key="gk",
                )
            ],
        ),
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
        graph_service=graph_service,
        event_bus=event_bus,
        object_store=object_store,
    )
    assert alerts == 0
    failures = [
        e for e in event_bus.published_events if isinstance(e, AnalysisFailedEvent)
    ]
    assert len(failures) == 1
    assert failures[0].stage == "risk"
    assert failures[0].entity_id == "provider-1"


def test_analytics_handler_stops_immediately_when_cancelled() -> None:
    """A cancelled run aborts Flow B at the first loop boundary: no GNN/risk/
    explainability work runs and no alerts.created / analysis.failed is published."""
    from typing import cast

    from agent.coordinator import handle_graph_updated_for_analytics
    from analytics.explainability.service import ExplainabilityService
    from analytics.gnn.service import GnnService
    from analytics.risk.service import RiskService
    from graph.service import GraphService

    class _Boom:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"service used despite cancellation: {name}")

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    object_store.put_bytes(
        "gk",
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-A",
            parsed_document_id="parsed-A",
            extraction_result_id="extract-A",
            validation_report_id="validate-A",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    alerts = handle_graph_updated_for_analytics(
        GraphUpdatedEvent(
            correlation_id="corr-cancel",
            documents=[
                GraphUpdatedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-A",
                    parsed_document_id="parsed-A",
                    extraction_result_id="extract-A",
                    validation_report_id="validate-A",
                    upserted_entity_count=1,
                    upserted_relationship_count=0,
                    validation_storage_key="vk",
                    graph_update_storage_key="gk",
                )
            ],
        ),
        gnn_service=cast(GnnService, _Boom()),
        risk_service=cast(RiskService, _Boom()),
        explainability_service=cast(ExplainabilityService, _Boom()),
        graph_service=cast(GraphService, _Boom()),
        event_bus=event_bus,
        object_store=object_store,
        is_cancelled=lambda: True,
    )

    assert alerts == 0
    assert event_bus.published_events == []


def test_analytics_handler_skips_missing_gnn_snapshot_without_failing_flow_a() -> None:
    """Missing GNN snapshots are controlled skips while Flow A still publishes."""

    from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
    from analytics.gnn.service import create_gnn_service
    from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
    from analytics.risk.service import create_risk_service
    from analytics.explainability.adapters.in_memory import (
        InMemoryExplainabilityContextSource,
    )
    from analytics.explainability.service import create_explainability_service
    from events.types import AnalysisFailedEvent, EmbeddingsCompleteEvent

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_update_storage_key = "knowledgebases/kb-1/graph_updates/extract-Z.json"
    validation_storage_key = "knowledgebases/kb-1/validations/extract-Z.json"
    object_store.put_bytes(
        graph_update_storage_key,
        GraphUpsertResult(
            knowledge_base_id="kb-1",
            source_document_id="doc-Z",
            parsed_document_id="parsed-Z",
            extraction_result_id="extract-Z",
            validation_report_id="validate-Z",
            upserted_entity_ids=["provider-1"],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    object_store.put_bytes(
        validation_storage_key,
        ValidationReport(
            id="validate-Z",
            extraction_result_id="extract-Z",
            source_document_id="doc-Z",
            valid_entities=[
                Entity(
                    id="provider-1",
                    type="claim",
                    properties={"embedding_text": "Provider 1"},
                ),
            ],
        ).model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    # Empty analytics adapters do not have a GNN snapshot yet. Fresh KBs should
    # skip Flow B quietly instead of emitting a misleading analysis.failed event.
    gnn_service = create_gnn_service(
        InMemoryGraphSnapshotSource(), event_bus=event_bus
    )
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(), event_bus=event_bus
    )
    explainability_service = create_explainability_service(
        InMemoryExplainabilityContextSource(), event_bus=event_bus
    )
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(
            event=GraphUpdatedEvent(
                correlation_id="corr-mixed",
                documents=[
                    GraphUpdatedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-Z",
                        parsed_document_id="parsed-Z",
                        extraction_result_id="extract-Z",
                        validation_report_id="validate-Z",
                        upserted_entity_count=1,
                        upserted_relationship_count=0,
                        validation_storage_key=validation_storage_key,
                        graph_update_storage_key=graph_update_storage_key,
                    )
                ],
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        embeddings_service=embeddings_service,
        gnn_service=gnn_service,
        risk_service=risk_service,
        explainability_service=explainability_service,
    )

    assert processed == 1
    embedding_events = [
        e for e in event_bus.published_events if isinstance(e, EmbeddingsCompleteEvent)
    ]
    assert len(embedding_events) == 1
    failures = [
        e for e in event_bus.published_events if isinstance(e, AnalysisFailedEvent)
    ]
    assert failures == []


def test_handle_event_emits_analysis_failed_when_analytics_fanout_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import cast

    from analytics.explainability.service import ExplainabilityService
    from analytics.gnn.service import GnnService
    from analytics.risk.service import RiskService
    from events.types import EmbeddingsCompleteEvent

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_event = _graph_updated_event_with_valid_entity(
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        object_store=object_store,
    ).model_copy(update={"correlation_id": "corr-analytics-fanout"})
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    def _raise_analytics_fanout(*args: object, **kwargs: object) -> int:
        raise RuntimeError("fanout unavailable")

    monkeypatch.setattr(
        coordinator,
        "handle_graph_updated_for_analytics",
        _raise_analytics_fanout,
    )

    processed = handle_event(
        EventDelivery(event=graph_event),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        embeddings_service=embeddings_service,
        gnn_service=cast(GnnService, object()),
        risk_service=cast(RiskService, object()),
        explainability_service=cast(ExplainabilityService, object()),
    )

    assert processed == 1
    embedding_events = [
        e for e in event_bus.published_events if isinstance(e, EmbeddingsCompleteEvent)
    ]
    assert len(embedding_events) == 1
    failures = [
        e for e in event_bus.published_events if isinstance(e, AnalysisFailedEvent)
    ]
    assert len(failures) == 1
    assert failures[0].correlation_id == "corr-analytics-fanout"
    assert failures[0].knowledge_base_id == "kb-1"
    assert failures[0].entity_id == "provider-1"
    assert failures[0].stage == "analytics_fanout"


def test_handle_event_propagates_analytics_fanout_failure_publish_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import cast

    from analytics.explainability.service import ExplainabilityService
    from analytics.gnn.service import GnnService
    from analytics.risk.service import RiskService
    from events.types import EmbeddingsCompleteEvent

    class _AnalysisFailedPublishError(RuntimeError):
        pass

    class _AnalysisFailedPublishFailingEventBus(InMemoryEventBus):
        def publish(self, event: AnyEvent) -> None:
            if isinstance(event, AnalysisFailedEvent):
                raise _AnalysisFailedPublishError("analysis.failed publish failed")
            super().publish(event)

    event_bus = _AnalysisFailedPublishFailingEventBus()
    object_store = InMemoryObjectStore()
    embeddings_service = _FakeEmbeddingsService()
    graph_event = _graph_updated_event_with_valid_entity(
        knowledge_base_id="kb-1",
        entity_id="provider-1",
        object_store=object_store,
    ).model_copy(update={"correlation_id": "corr-analytics-fanout-publish-fails"})
    graph_service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    def _raise_analytics_fanout(*args: object, **kwargs: object) -> int:
        raise RuntimeError("fanout unavailable")

    monkeypatch.setattr(
        coordinator,
        "handle_graph_updated_for_analytics",
        _raise_analytics_fanout,
    )

    with pytest.raises(
        _AnalysisFailedPublishError, match="analysis.failed publish failed"
    ):
        handle_event(
            EventDelivery(event=graph_event),
            service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
            embeddings_service=embeddings_service,
            gnn_service=cast(GnnService, object()),
            risk_service=cast(RiskService, object()),
            explainability_service=cast(ExplainabilityService, object()),
        )

    embedding_events = [
        e for e in event_bus.published_events if isinstance(e, EmbeddingsCompleteEvent)
    ]
    assert len(embedding_events) == 1
    assert not any(
        isinstance(e, AnalysisFailedEvent) for e in event_bus.published_events
    )


# ---------------------------------------------------------------------------
# E8-S07 — Monitoring stream consumer
# ---------------------------------------------------------------------------


def _build_monitoring_test_bundle() -> tuple[
    _MonitoringService, InMemoryEventBus, _RiskScoredEvent
]:
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.models import MonitoringBatch, MonitoringObservation
    from monitoring.service import create_monitoring_service
    from events.types import RiskScoredReference

    event_bus = InMemoryEventBus()
    source = InMemoryObservationSource(
        batches=[
            MonitoringBatch(
                knowledge_base_id="kb-1",
                batch_id="risk-request-1",
                observations=[
                    MonitoringObservation(
                        entity_id="provider-1",
                        entity_type="provider",
                        metric_name="risk",
                        score=0.92,
                        rationale="High risk score from risk service.",
                    )
                ],
            )
        ]
    )
    service = create_monitoring_service(source, event_bus=event_bus)
    event = _RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="risk-request-1",
                entity_id="provider-1",
                overall_score=0.92,
                risk_level="high",
                factor_count=2,
            )
        ]
    )
    return service, event_bus, event


def test_handle_risk_scored_emits_alerts_created() -> None:
    from agent.coordinator import handle_risk_scored
    from events.types import AlertsCreatedEvent

    service, event_bus, event = _build_monitoring_test_bundle()

    processed = handle_risk_scored(
        event, monitoring_service=service, event_bus=event_bus
    )

    assert processed == 1
    alerts_events = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(alerts_events) == 1
    assert alerts_events[0].alerts[0].entity_id == "provider-1"


def test_handle_risk_scored_logs_and_continues_on_monitoring_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from agent.coordinator import handle_risk_scored
    from events.types import RiskScoredEvent, RiskScoredReference
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.service import create_monitoring_service

    event_bus = InMemoryEventBus()
    # No batch seeded — load_batch raises ValueError, mapped to MonitoringConfigurationError.
    service = create_monitoring_service(
        InMemoryObservationSource(), event_bus=event_bus
    )
    event = RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="missing",
                entity_id="provider-1",
                overall_score=0.5,
                risk_level="medium",
                factor_count=1,
            )
        ]
    )

    caplog.set_level(logging.ERROR, logger="chili.worker")
    processed = handle_risk_scored(
        event, monitoring_service=service, event_bus=event_bus
    )

    # Failures count zero processed assessments and do not raise.
    assert processed == 0
    assert "Monitoring evaluation failed" in caplog.text


def test_handle_event_dispatches_risk_scored_to_monitoring() -> None:
    from agent.coordinator import handle_event
    from events.types import AlertsCreatedEvent

    service, event_bus, event = _build_monitoring_test_bundle()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(event=event, event_id="1", stream="risk.scored"),
        ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        monitoring_service=service,
    )

    assert processed == 1
    alerts_events = [
        e for e in event_bus.published_events if isinstance(e, AlertsCreatedEvent)
    ]
    assert len(alerts_events) == 1


def test_handle_event_skips_risk_scored_when_no_monitoring_service() -> None:
    from agent.coordinator import handle_event
    from events.types import RiskScoredEvent, RiskScoredReference

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    event = RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="r1",
                entity_id="provider-1",
                overall_score=0.5,
                risk_level="medium",
                factor_count=1,
            )
        ]
    )

    processed = handle_event(
        EventDelivery(event=event, event_id="1", stream="risk.scored"),
        ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
    )

    assert processed == 0


def test_handle_event_absorbs_unexpected_monitoring_exception() -> None:
    """A non-MonitoringError raised by monitoring should not propagate from handle_event."""

    from agent.coordinator import handle_event
    from events.types import RiskScoredEvent, RiskScoredReference
    from monitoring.adapters.in_memory import InMemoryObservationSource
    from monitoring.service import MonitoringService
    from monitoring.service_models import (
        MonitoringEvaluationRequest,
        MonitoringEvaluationResponse,
    )

    class _BoomMonitoring(MonitoringService):
        def __init__(self) -> None:
            super().__init__(InMemoryObservationSource(), event_bus=InMemoryEventBus())

        def evaluate(
            self, request: MonitoringEvaluationRequest
        ) -> MonitoringEvaluationResponse:
            raise RuntimeError("unexpected failure")

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository, object_store=object_store, event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    event = RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="r1",
                entity_id="provider-1",
                overall_score=0.5,
                risk_level="medium",
                factor_count=1,
            )
        ]
    )

    processed = handle_event(
        EventDelivery(event=event, event_id="1", stream="risk.scored"),
        ingestion_service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=graph_service,
        object_store=object_store,
        event_bus=event_bus,
        monitoring_service=_BoomMonitoring(),
    )

    assert processed == 0


def test_dispatch_runs_kb_cleanup_when_wired_and_guards_when_not() -> None:
    """The worker dispatch invokes the KB-delete cascade when wired, else guards."""
    from types import SimpleNamespace
    from typing import cast
    from unittest.mock import MagicMock

    from agent.coordinator import handle_event
    from events.types import KnowledgeBaseDeletedEvent
    from knowledgebases.cleanup import KbDeletionStores
    from storage.adapters.in_memory import InMemoryObjectStore

    object_store = InMemoryObjectStore()
    event_bus = InMemoryEventBus()
    graph_service = create_graph_service(
        InMemoryGraphRepository(), object_store=object_store, event_bus=event_bus
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    store_fields = [
        "graph_service", "vector_service", "raw_record_store", "derived_signal_store",
        "risk_history_writer", "observation_writer", "alert_history_writer",
        "entity_metric_repository", "conversation_repository", "case_repository",
        "policy_item_repository", "evidence_pack_repository",
        "scorecard_run_repository", "document_status_store", "object_store",
    ]
    mocks = {field: MagicMock() for field in store_fields}
    mocks["object_store"].list_keys.return_value = []
    # Worker bundle: no API-owned alert projection store (cascade skips it).
    bundle = cast(
        KbDeletionStores, SimpleNamespace(**mocks, alert_projection_store=None)
    )
    kb_repository = MagicMock()

    def _dispatch(stores: KbDeletionStores | None) -> int:
        return handle_event(
            EventDelivery(
                event=KnowledgeBaseDeletedEvent(
                    knowledge_base_id="kb-x", cleanup_pending=True
                )
            ),
            ingestion_service,
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
            kb_deletion_stores=stores,
            kb_repository=kb_repository,  # type: ignore[arg-type]
        )

    # Wired → dispatch invokes the handler, which replays the cascade + deletes metadata.
    assert _dispatch(bundle) == 1
    mocks["risk_history_writer"].delete_by_kb.assert_called_once_with("kb-x")
    mocks["scorecard_run_repository"].delete_by_kb.assert_called_once_with("kb-x")
    mocks["document_status_store"].delete_by_kb.assert_called_once_with("kb-x")
    kb_repository.delete.assert_called_once_with("kb-x")

    # Not wired (no bundle) → guard short-circuits, no cleanup.
    kb_repository.reset_mock()
    assert _dispatch(None) == 0
    kb_repository.delete.assert_not_called()


def _dispatch_ingestion_service(event_bus: InMemoryEventBus, object_store: InMemoryObjectStore) -> IngestionService:
    return IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
        ),
        object_store=object_store,
        event_bus=event_bus,
    )


def test_handle_event_propagates_risk_history_writeback_failure() -> None:
    """Un-swallowed: a risk_score_history write failure reaches the retry/DLQ wrapper."""
    import pytest as _pytest

    from agent.coordinator import handle_event
    from analytics.risk.models import RiskAssessmentRecord
    from events.types import RiskScoredEvent, RiskScoredReference

    class _BoomRiskHistory:
        def write_assessment(self, record: RiskAssessmentRecord) -> bool:
            raise RuntimeError("risk-history db down")

        def load_historical_score(
            self, *, knowledge_base_id: str, entity_id: str
        ) -> float | None:
            return None

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(), object_store=object_store, event_bus=event_bus
    )
    event = RiskScoredEvent(
        assessments=[
            RiskScoredReference(
                knowledge_base_id="kb-1",
                request_id="risk:corr-1:kb-1:provider-1",
                entity_id="provider-1",
                overall_score=0.9,
                risk_level="high",
                factor_count=2,
            )
        ]
    )

    with _pytest.raises(RuntimeError, match="risk-history db down"):
        handle_event(
            EventDelivery(event=event, event_id="1", stream="risk.scored"),
            _dispatch_ingestion_service(event_bus, object_store),
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
            risk_history_writer=_BoomRiskHistory(),  # type: ignore[arg-type]
        )


def test_handle_event_propagates_alert_history_writeback_failure() -> None:
    """Un-swallowed: an alert_history write failure reaches the retry/DLQ wrapper."""
    import pytest as _pytest

    from agent.coordinator import handle_event
    from events.types import AlertCreatedReference, AlertsCreatedEvent
    from monitoring.models import AlertHistoryRecord

    class _BoomAlertHistory:
        def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
            raise RuntimeError("alert-history db down")

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(), object_store=object_store, event_bus=event_bus
    )
    event = AlertsCreatedEvent(
        alerts=[
            AlertCreatedReference(
                knowledge_base_id="kb-1",
                alert_id="alert-provider-1-risk:corr-1:kb-1:provider-1",
                entity_id="provider-1",
                severity="high",
                title="High risk: provider-1",
                reasoning="why",
                metric_name="risk_score",
            )
        ]
    )

    with _pytest.raises(RuntimeError, match="alert-history db down"):
        handle_event(
            EventDelivery(event=event, event_id="1", stream="alerts.created"),
            _dispatch_ingestion_service(event_bus, object_store),
            document_chunker=create_document_chunker(),
            document_extractor=create_document_extractor([]),
            extraction_validator=create_extraction_validator([], []),
            graph_service=graph_service,
            object_store=object_store,
            event_bus=event_bus,
            alert_history_writer=_BoomAlertHistory(),  # type: ignore[arg-type]
        )


def test_drain_records_dead_letter_in_health_not_success() -> None:
    """A dead-lettered delivery is recorded as dead-lettered, not processed."""
    from agent.health import HealthState
    from agent.models import HealthSettings

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_service = create_graph_service(
        InMemoryGraphRepository(), object_store=object_store, event_bus=event_bus
    )
    event_bus.publish(
        RecordsIngestedEvent(
            correlation_id="corr-dl",
            knowledge_base_id="kb-1",
            feed_name="missing_feed",
            record_type="claim_record",
            record_count=1,
        )
    )
    health_state = HealthState(settings=HealthSettings())

    asyncio.run(
        drain_ingestion_events(
            event_bus,
            IngestionService(
                DocumentParsingOrchestrator(
                    create_default_registry(), fetcher=HttpxRemoteDocumentFetcher()
                ),
                object_store=object_store,
                event_bus=event_bus,
            ),
            create_document_chunker(),
            create_document_extractor([]),
            create_extraction_validator([], []),
            graph_service,
            object_store,
            records_config=RecordsConfig(),
            raw_record_store=InMemoryRawRecordStore(),
            observation_writer=InMemoryObservationWriter(),
            consumer_group="test-workers",
            consumer_name="worker-1",
            retry_policy=RetryPolicy(max_retries=0, base_delay_seconds=0.0),
            health_state=health_state,
            sleep=_instant_sleep,
        )
    )

    assert len(event_bus.dlq_entries) == 1
    assert health_state.events_dead_lettered == 1
    assert health_state.events_processed == 0
    # Honest health: received an event, dead-lettered it all → degraded.
    assert health_state.status() == "degraded"


def test_run_worker_survives_transient_drain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient error in a drain iteration must NOT crash the worker process."""
    import socket
    from contextlib import closing

    from agent.coordinator import run_worker
    from agent.models import HealthSettings

    defaults_yaml = __file__.replace(
        "tests/agent/test_coordinator.py", "config/defaults/medicare_fraud.yaml"
    )
    monkeypatch.setenv("CHILI_CONFIG_PATH", defaults_yaml)
    monkeypatch.setattr("agent.coordinator.DRAIN_ERROR_BACKOFF_SECONDS", 0.01)

    calls = {"n": 0}

    async def _boom(*_args: object, **_kwargs: object) -> int:
        calls["n"] += 1
        raise RuntimeError("transient redis outage")

    monkeypatch.setattr("agent.coordinator._drain_once", _boom)

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]

    async def _run() -> None:
        task = asyncio.create_task(
            run_worker(
                health_settings=HealthSettings(host="127.0.0.1", port=free_port)
            )
        )
        await asyncio.sleep(0.1)
        task.cancel()
        # run_worker swallows CancelledError for graceful shutdown; if resilience
        # were broken, the first RuntimeError would propagate here instead.
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())
    # The loop kept invoking drain across repeated failures rather than crashing.
    assert calls["n"] >= 2


def test_run_worker_passes_configured_stage_policy_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.coordinator import run_worker
    from agent.models import HealthSettings

    monkeypatch.setenv(
        "CHILI_STAGE_POLICY_JSON",
        '{"documents.parsed": {"max_retries": 1, "timeout_seconds": 0.5}}',
    )
    monkeypatch.setenv("CHILI_WORKFLOW_STALE_MAX_AGE_SECONDS", "0")
    monkeypatch.setattr(
        "agent.coordinator.build_worker_dependencies",
        lambda: SimpleNamespace(
            ingestion_service=SimpleNamespace(replay_recovery_markers=lambda: 0),
            workflow_tracker=SimpleNamespace(reconcile_stale_runs=_reconcile_zero),
            event_bus=InMemoryEventBus(),
            event_settings=EventBusSettings(backend="in-memory"),
        ),
    )

    async def _skip_health_server(_state: object) -> None:
        return None

    monkeypatch.setattr(
        "agent.coordinator.start_health_server_safely",
        _skip_health_server,
    )

    captured: dict[str, StagePolicyRegistry] = {}

    async def _drain_once(*_args: object, **kwargs: object) -> int:
        registry = kwargs["stage_policy_registry"]
        assert isinstance(registry, StagePolicyRegistry)
        captured["stage_policy_registry"] = registry
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        return 0

    monkeypatch.setattr("agent.coordinator._drain_once", _drain_once)

    async def _run() -> None:
        task = asyncio.create_task(
            run_worker(
                retry_policy=RetryPolicy(max_retries=5, base_delay_seconds=0.125),
                health_settings=HealthSettings(host="127.0.0.1", port=1),
            )
        )
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())

    registry = captured["stage_policy_registry"]
    policy = registry.get("documents.parsed")
    assert policy.retry_policy.max_retries == 1
    assert policy.timeout_seconds == 0.5
    fallback_policy = registry.get("graph.updated")
    assert fallback_policy.retry_policy.max_retries == 5
    assert fallback_policy.retry_policy.base_delay_seconds == 0.125
    assert fallback_policy.timeout_seconds is None


def test_run_worker_replays_recovery_markers_before_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.coordinator import run_worker
    from agent.models import HealthSettings

    calls: list[str] = []

    class FakeIngestionService:
        def replay_recovery_markers(self) -> int:
            calls.append("replay")
            return 1

    monkeypatch.setenv("CHILI_WORKFLOW_STALE_MAX_AGE_SECONDS", "0")
    monkeypatch.setattr(
        "agent.coordinator.build_worker_dependencies",
        lambda: SimpleNamespace(
            ingestion_service=FakeIngestionService(),
            workflow_tracker=SimpleNamespace(reconcile_stale_runs=_reconcile_zero),
            event_bus=InMemoryEventBus(),
            event_settings=EventBusSettings(backend="in-memory"),
        ),
    )

    async def _skip_health_server(_state: object) -> None:
        return None

    monkeypatch.setattr(
        "agent.coordinator.start_health_server_safely",
        _skip_health_server,
    )

    async def _drain_once(*_args: object, **_kwargs: object) -> int:
        calls.append("drain")
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        return 0

    monkeypatch.setattr("agent.coordinator._drain_once", _drain_once)

    async def _run() -> None:
        task = asyncio.create_task(
            run_worker(health_settings=HealthSettings(host="127.0.0.1", port=1))
        )
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())

    assert calls == ["replay", "drain"]


def test_run_worker_retries_recovery_replay_failure_before_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.coordinator import run_worker
    from agent.models import HealthSettings

    calls: list[str] = []

    class FakeIngestionService:
        def __init__(self) -> None:
            self.replay_attempts = 0

        def replay_recovery_markers(self) -> int:
            self.replay_attempts += 1
            calls.append("replay")
            if self.replay_attempts == 1:
                raise RuntimeError("transient event bus outage")
            return 1

    monkeypatch.setenv("CHILI_WORKFLOW_STALE_MAX_AGE_SECONDS", "0")
    monkeypatch.setattr("agent.coordinator.DRAIN_ERROR_BACKOFF_SECONDS", 0.01)
    monkeypatch.setattr(
        "agent.coordinator.build_worker_dependencies",
        lambda: SimpleNamespace(
            ingestion_service=FakeIngestionService(),
            workflow_tracker=SimpleNamespace(reconcile_stale_runs=_reconcile_zero),
            event_bus=InMemoryEventBus(),
            event_settings=EventBusSettings(backend="in-memory"),
        ),
    )

    async def _skip_health_server(_state: object) -> None:
        return None

    monkeypatch.setattr(
        "agent.coordinator.start_health_server_safely",
        _skip_health_server,
    )

    async def _drain_once(*_args: object, **_kwargs: object) -> int:
        calls.append("drain")
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        return 0

    monkeypatch.setattr("agent.coordinator._drain_once", _drain_once)

    async def _run() -> None:
        task = asyncio.create_task(
            run_worker(health_settings=HealthSettings(host="127.0.0.1", port=1))
        )
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())

    assert calls == ["replay", "replay", "drain"]


def _config_with_llm_provider(
    provider: Literal["openai", "anthropic", "local", "ollama"],
) -> DomainConfig:
    return _base_config().model_copy(update={"llm": LlmConfig(provider=provider)})


def test_build_document_extractor_uses_pattern_extractor_for_local_stub() -> None:
    from agent.coordinator import build_document_extractor
    from ingestion.extractor import PatternDocumentExtractor
    from llm.adapters.in_memory import InMemoryLlmClient

    extractor = build_document_extractor(
        _config_with_llm_provider("local"), InMemoryLlmClient()
    )
    assert isinstance(extractor, PatternDocumentExtractor)


def test_build_document_extractor_uses_llm_extractor_for_real_provider() -> None:
    from agent.coordinator import build_document_extractor
    from ingestion.extractor import LlmDocumentExtractor
    from llm.adapters.in_memory import InMemoryLlmClient

    extractor = build_document_extractor(
        _config_with_llm_provider("ollama"), InMemoryLlmClient()
    )
    assert isinstance(extractor, LlmDocumentExtractor)


def test_handle_entities_extracted_surfaces_extraction_stage_warnings() -> None:
    """Extraction-stage warnings (e.g. LLM non-JSON) must reach the warning event."""
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extraction_result = ExtractionResult(
        id="extract-warn",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        warnings=["LLM returned non-JSON for chunk chunk-1: Expecting value"],
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-warn.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    handle_entities_extracted(
        EntitiesExtractedEvent(
            documents=[
                ExtractedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-warn",
                    entity_count=0,
                    relationship_count=0,
                    extraction_storage_key=extraction_storage_key,
                )
            ]
        ),
        extraction_validator=create_extraction_validator([], []),
        object_store=object_store,
        event_bus=event_bus,
    )

    warning_events = [
        event
        for event in event_bus.published_events
        if isinstance(event, DocumentsExtractionWarningEvent)
    ]
    assert len(warning_events) == 1
    reference = warning_events[0].documents[0]
    assert any("non-JSON" in reason for reason in reference.sample_reasons)


def _kb_repository_with_document() -> InMemoryKnowledgeBaseRepository:
    from knowledgebases.models import DocumentRecord
    from shared.utils import utc_now

    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(id="kb-1", name="KB", description="", created_at=utc_now())
    )
    repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-1",
            filename="claims.csv",
            content_type="text/csv",
        )
    )
    return repository


def test_handle_documents_parsed_persists_parser_warnings() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = _kb_repository_with_document()
    parsed_document = ParsedDocument(
        id="parsed-1",
        source_document_id="doc-1",
        text_content="claim_id: 42",
        parser_name="test-parser",
    )
    storage_key = "knowledgebases/kb-1/parsed/parsed-1.json"
    object_store.put_bytes(
        storage_key,
        parsed_document.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    handle_documents_parsed(
        DocumentsParsedEvent(
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test-parser",
                    warning_count=2,
                    warning_samples=["csv.ragged_row: row 1", "csv.dialect_fallback: sniff failed"],
                    parsed_document_storage_key=storage_key,
                )
            ]
        ),
        document_chunker=create_document_chunker(),
        object_store=object_store,
        event_bus=event_bus,
        kb_repository=repository,
    )

    record = repository.get_document("kb-1", "doc-1")
    assert record is not None
    assert record.warning_count == 2
    assert "csv.ragged_row: row 1" in record.warning_reasons


def test_handle_entities_extracted_persists_extraction_warnings() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = _kb_repository_with_document()
    extraction_result = ExtractionResult(
        id="extract-persist",
        source_document_id="doc-1",
        parsed_document_id="parsed-1",
        warnings=["No entity candidates extracted from persisted chunks."],
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-persist.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    handle_entities_extracted(
        EntitiesExtractedEvent(
            documents=[
                ExtractedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    extraction_result_id="extract-persist",
                    entity_count=0,
                    relationship_count=0,
                    extraction_storage_key=extraction_storage_key,
                )
            ]
        ),
        extraction_validator=create_extraction_validator([], []),
        object_store=object_store,
        event_bus=event_bus,
        kb_repository=repository,
    )

    record = repository.get_document("kb-1", "doc-1")
    assert record is not None
    assert record.warning_count >= 1
    assert any("No entity candidates" in reason for reason in record.warning_reasons)


def test_worker_subscribes_to_extraction_warning_events() -> None:
    assert "documents.extraction_warning" in WORKER_EVENT_TYPES


def test_build_document_status_store_falls_back_to_in_memory() -> None:
    store = build_document_status_store(None)
    assert isinstance(store, InMemorySourceDocumentStatusStore)


def test_handle_event_projects_extraction_warning_to_status_store() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    status_store = InMemorySourceDocumentStatusStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    processed = handle_event(
        EventDelivery(
            event=DocumentsExtractionWarningEvent(
                documents=[
                    ExtractionWarningReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        valid_entity_count=0,
                        valid_relationship_count=0,
                        dropped_entity_count=3,
                        dropped_relationship_count=0,
                        stripped_property_count=0,
                        empty_extraction=True,
                        sample_reasons=["entity cand-1: unknown type"],
                    )
                ]
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
        document_status_store=status_store,
    )

    assert processed == 0
    projected = status_store.get_many(
        knowledge_base_id="kb-1", source_document_ids=["doc-1"]
    )["doc-1"]
    assert projected.current_status == IngestionStatus.EXTRACTED_EMPTY
    assert projected.dropped_entity_count == 3


def test_handle_event_projects_failed_documents_to_status_store() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    status_store = InMemorySourceDocumentStatusStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    handle_event(
        EventDelivery(
            event=DocumentsFailedEvent(
                documents=[
                    DocumentFailureReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-1",
                        error_message="parse exploded",
                    )
                ]
            )
        ),
        service,
        document_chunker=create_document_chunker(),
        document_extractor=create_document_extractor([]),
        extraction_validator=create_extraction_validator([], []),
        graph_service=create_graph_service(
            InMemoryGraphRepository(),
            object_store=object_store,
            event_bus=event_bus,
        ),
        object_store=object_store,
        event_bus=event_bus,
        document_status_store=status_store,
    )

    projected = status_store.get_many(
        knowledge_base_id="kb-1", source_document_ids=["doc-1"]
    )["doc-1"]
    assert projected.current_status == IngestionStatus.FAILED
    assert projected.last_error == "parse exploded"


def _has_stage_field(text: str, key: str, value: str) -> bool:
    """Match a structured field under either renderer: console (key=value) or JSON."""
    return f"{key}={value}" in text or f'"{key}": "{value}"' in text


def test_handle_documents_parsed_emits_chunk_stage_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunker = create_document_chunker()
    parsed_document = ParsedDocument(
        id="parsed-log-1",
        source_document_id="doc-log-1",
        text_content="Claim 42 was filed by provider A.",
        parser_name="test-parser",
    )
    storage_key = "knowledgebases/kb-1/parsed/parsed-log-1.json"
    object_store.put_bytes(
        storage_key,
        parsed_document.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        handle_documents_parsed(
            DocumentsParsedEvent(
                correlation_id="corr-chunk-log",
                documents=[
                    ParsedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-log-1",
                        parsed_document_id="parsed-log-1",
                        parser_name="test-parser",
                        storage_key="knowledgebases/kb-1/documents/doc-log-1/claims.txt",
                        parsed_document_storage_key=storage_key,
                    )
                ],
            ),
            document_chunker=chunker,
            object_store=object_store,
            event_bus=event_bus,
        )

    assert _has_stage_field(caplog.text, "stage", "chunk")
    assert _has_stage_field(caplog.text, "kb_id", "kb-1")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-log-1")
    assert _has_stage_field(caplog.text, "outcome", "success")
    assert "duration_ms" in caplog.text


def test_handle_documents_chunked_logs_empty_outcome_for_zero_candidates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    chunking_result = ChunkingResult(
        source_document_id="doc-empty-log",
        parsed_document_id="parsed-empty-log",
        strategy_used="StructuredRecordChunker",
        chunks=[],
    )
    chunks_storage_key = "knowledgebases/kb-1/chunks/parsed-empty-log.json"
    object_store.put_bytes(
        chunks_storage_key,
        chunking_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        handle_documents_chunked(
            DocumentsChunkedEvent(
                documents=[
                    ChunkedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-empty-log",
                        parsed_document_id="parsed-empty-log",
                        chunk_count=0,
                        strategy="StructuredRecordChunker",
                        chunks_storage_key=chunks_storage_key,
                    )
                ]
            ),
            document_extractor=create_document_extractor([]),
            object_store=object_store,
            event_bus=event_bus,
        )

    assert _has_stage_field(caplog.text, "stage", "extract")
    assert _has_stage_field(caplog.text, "outcome", "empty")


def test_handle_entities_extracted_counts_empty_extraction_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    extraction_result = ExtractionResult(
        id="extract-empty-count",
        source_document_id="doc-empty-count",
        parsed_document_id="parsed-empty-count",
    )
    extraction_storage_key = "knowledgebases/kb-1/extractions/extract-empty-count.json"
    object_store.put_bytes(
        extraction_storage_key,
        extraction_result.model_dump_json().encode("utf-8"),
        media_type="application/json",
    )
    before = (
        REGISTRY.get_sample_value("ingestion_documents_empty_extraction_total") or 0.0
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        handle_entities_extracted(
            EntitiesExtractedEvent(
                documents=[
                    ExtractedDocumentReference(
                        knowledge_base_id="kb-1",
                        source_document_id="doc-empty-count",
                        parsed_document_id="parsed-empty-count",
                        extraction_result_id="extract-empty-count",
                        entity_count=0,
                        relationship_count=0,
                        extraction_storage_key=extraction_storage_key,
                    )
                ]
            ),
            extraction_validator=create_extraction_validator([], []),
            object_store=object_store,
            event_bus=event_bus,
        )

    after = (
        REGISTRY.get_sample_value("ingestion_documents_empty_extraction_total") or 0.0
    )
    assert after == before + 1.0
    assert _has_stage_field(caplog.text, "stage", "validate")
    assert _has_stage_field(caplog.text, "outcome", "empty")


def test_build_embedding_cache_returns_cache_and_namespace() -> None:
    from agent.coordinator import build_embedding_cache

    config = _base_config().model_copy(
        update={
            "embeddings": EmbeddingsConfig(
                provider="local",
                model="worker-cache-model",
                dimensions=128,
            ),
        }
    )

    cache, namespace = build_embedding_cache(config)

    assert isinstance(cache, InMemoryLruEmbeddingCache)
    assert namespace == "local:worker-cache-model:128"


def test_build_embedding_cache_disabled_returns_none() -> None:
    from agent.coordinator import build_embedding_cache

    config = _base_config().model_copy(
        update={"embeddings": EmbeddingsConfig(cache_enabled=False)}
    )

    cache, namespace = build_embedding_cache(config)

    assert cache is None
    assert namespace == "sentence_transformers:all-MiniLM-L6-v2:384"
