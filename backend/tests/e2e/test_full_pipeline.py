"""End-to-end integration tests for the full ingest -> kb.ready pipeline.

These tests exercise the public HTTP surface (``POST /knowledgebases/{id}/documents``)
and drive the worker coordinator in-process via ``drain_ingestion_events``.  All
adapters are in-memory; the assertions verify cross-module integration rather
than internal module behaviour.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from agent.coordinator import drain_ingestion_events
from analytics.explainability.adapters.in_memory import (
    InMemoryExplainabilityContextSource,
)
from analytics.gnn.adapters.in_memory import InMemoryGraphSnapshotSource
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
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
    get_vector_store,
    get_vectorstore_service,
)
from analytics.explainability.service import create_explainability_service
from analytics.gnn.service import create_gnn_service
from analytics.risk.service import create_risk_service
from config.loader import load_config
from config.schema import RecordsConfig
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.service import create_embeddings_service
from events.adapters.in_memory import InMemoryEventBus
from events.types import (
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    GraphUpdatedEvent,
    KnowledgeBaseReadyEvent,
)
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from ingestion.chunker import create_document_chunker
from ingestion.extractor import create_document_extractor
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.validator import create_extraction_validator
from monitoring.adapters.in_memory import InMemoryObservationSource, InMemoryObservationWriter
from monitoring.service import create_monitoring_service
from records.adapters.in_memory import InMemoryRawRecordStore
from records.service import create_records_service
from storage.adapters.in_memory import InMemoryObjectStore
from tests.e2e.conftest import E2EHarness
from vectorstore.adapters.in_memory import InMemoryVectorStore


_HAPPY_PATH_BODY = (
    '{"name": "Acme Health Provider", "category": "primary care"}'
)


def _create_kb(harness: E2EHarness, kb_id: str = "kb-e2e-1") -> str:
    response = harness.client.post(
        "/knowledgebases",
        json={"name": f"E2E KB {kb_id}", "description": "fixture"},
    )
    assert response.status_code == 201, response.text
    payload = cast("dict[str, object]", response.json())
    kb_id_value = payload.get("id")
    assert isinstance(kb_id_value, str)
    return kb_id_value


def _upload_document(
    harness: E2EHarness,
    knowledge_base_id: str,
    *,
    filename: str,
    body: bytes,
    content_type: str = "application/json",
) -> dict[str, object]:
    response = harness.client.post(
        f"/knowledgebases/{knowledge_base_id}/documents",
        files={"files": (filename, body, content_type)},
    )
    assert response.status_code == 202, response.text
    payload = cast("dict[str, object]", response.json())
    documents_obj = payload.get("documents")
    assert isinstance(documents_obj, list)
    documents_list = cast("list[dict[str, object]]", documents_obj)
    assert len(documents_list) >= 1
    first = documents_list[0]
    assert isinstance(first, dict)
    return first


@pytest.mark.e2e
def test_happy_path_single_document_reaches_kb_ready(harness: E2EHarness) -> None:
    """Upload a small JSON document and assert kb.ready arrives with full counts."""

    started = time.monotonic()
    knowledge_base_id = _create_kb(harness)
    receipt = _upload_document(
        harness,
        knowledge_base_id,
        filename="provider.json",
        body=_HAPPY_PATH_BODY.encode("utf-8"),
    )
    assert isinstance(receipt["status"], str) and receipt["status"]

    harness.drain()

    kb_ready_events = [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, KnowledgeBaseReadyEvent)
    ]
    assert kb_ready_events, "Expected at least one kb.ready event"
    assert any(
        ref.knowledge_base_id == knowledge_base_id
        for event in kb_ready_events
        for ref in event.knowledge_bases
    )

    # Pipeline stages all fired at least once
    for event_type in (
        DocumentsUploadedEvent,
        DocumentsParsedEvent,
        EntitiesExtractedEvent,
        EntitiesValidatedEvent,
        GraphUpdatedEvent,
    ):
        assert any(
            isinstance(event, event_type)
            for event in harness.event_bus.published_events
        ), f"Expected {event_type.__name__} to be published"

    # Graph populated and entity counts surfaced via kb.ready reference.
    matching_refs = [
        ref
        for event in kb_ready_events
        for ref in event.knowledge_bases
        if ref.knowledge_base_id == knowledge_base_id
    ]
    assert matching_refs, "kb.ready missing knowledge_base reference"
    assert matching_refs[0].entity_count >= 1
    assert matching_refs[0].vector_count >= 1
    assert harness.graph_repository.count_entities(knowledge_base_id) >= 1

    elapsed = time.monotonic() - started
    assert elapsed < 30.0, f"E2E happy path took {elapsed:.2f}s (>30s budget)"


@pytest.mark.e2e
def test_multi_document_batch_reaches_kb_ready(harness: E2EHarness) -> None:
    """Upload three documents in quick succession; each must reach kb.ready."""

    started = time.monotonic()
    knowledge_base_id = _create_kb(harness, "kb-e2e-batch")
    bodies = [
        b'{"name": "Provider Alpha"}',
        b'{"name": "Provider Bravo"}',
        b'{"name": "Provider Charlie"}',
    ]
    for index, body in enumerate(bodies):
        _upload_document(
            harness,
            knowledge_base_id,
            filename=f"provider-{index}.json",
            body=body,
        )

    harness.drain()

    kb_ready_events = [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, KnowledgeBaseReadyEvent)
    ]
    assert kb_ready_events, "Expected at least one kb.ready event"

    # All three sources reached graph upsert.
    graph_updated_events = [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, GraphUpdatedEvent)
    ]
    upserted_doc_ids: set[str] = set()
    for event in graph_updated_events:
        for document in event.documents:
            upserted_doc_ids.add(document.source_document_id)
    assert len(upserted_doc_ids) == len(bodies)

    assert harness.graph_repository.count_entities(knowledge_base_id) >= len(bodies)

    elapsed = time.monotonic() - started
    assert elapsed < 30.0, f"E2E batch path took {elapsed:.2f}s (>30s budget)"


@pytest.mark.e2e
def test_extraction_errors_do_not_crash_pipeline(harness: E2EHarness) -> None:
    """A document that yields no extractable entities must not crash the pipeline.

    The pattern extractor emits a warning when no candidates match. The
    coordinator must continue draining downstream stages without raising and the
    pipeline as a whole must still emit downstream completion events for the
    other documents in the same batch.
    """

    started = time.monotonic()
    knowledge_base_id = _create_kb(harness, "kb-e2e-degraded")
    _upload_document(
        harness,
        knowledge_base_id,
        filename="bad.txt",
        body=b"This document mentions nothing matching any property pattern.",
        content_type="text/plain",
    )
    _upload_document(
        harness,
        knowledge_base_id,
        filename="good.json",
        body=b'{"name": "Provider Delta"}',
    )

    harness.drain()

    # The pipeline did not crash: at least one extraction event fired.
    extracted_events = [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, EntitiesExtractedEvent)
    ]
    assert extracted_events, "Expected entities.extracted to fire even on degraded inputs"

    # A document with no extractable entities still produces a validation event
    # (with zero valid entities); the good document still reaches graph.updated.
    graph_updated_events = [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, GraphUpdatedEvent)
    ]
    upserted_doc_ids: set[str] = set()
    for event in graph_updated_events:
        for document in event.documents:
            if document.upserted_entity_count > 0:
                upserted_doc_ids.add(document.source_document_id)
    assert upserted_doc_ids, "At least the well-formed document should reach graph upsert"

    elapsed = time.monotonic() - started
    assert elapsed < 30.0, f"E2E degraded path took {elapsed:.2f}s (>30s budget)"


# ---------------------------------------------------------------------------
# Records flow E2E (Task 1.5)
# ---------------------------------------------------------------------------

_MEDICARE_FRAUD_CONFIG_PATH = (
    Path(__file__).parent.parent.parent
    / "config"
    / "defaults"
    / "medicare_fraud_cms_desynpuf.yaml"
)

_TINY_CARRIER_CLAIMS_PATH = (
    Path(__file__).parent / "fixtures" / "tiny_carrier_claims.csv"
)


def _build_records_harness_deps() -> tuple[
    InMemoryEventBus,
    InMemoryObjectStore,
    InMemoryGraphRepository,
    InMemoryVectorStore,
    InMemoryRawRecordStore,
    InMemoryObservationWriter,
    IngestionService,
    RecordsConfig,
]:
    """Assemble the shared in-memory adapters for the records-flow harness."""
    medicare_config = load_config(_MEDICARE_FRAUD_CONFIG_PATH)

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_repo = InMemoryGraphRepository()
    vector_store = InMemoryVectorStore()
    raw_record_store = InMemoryRawRecordStore()
    observation_writer = InMemoryObservationWriter()

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

    records_config = medicare_config.records or RecordsConfig()
    return (
        event_bus,
        object_store,
        graph_repo,
        vector_store,
        raw_record_store,
        observation_writer,
        ingestion_service,
        records_config,
    )


@pytest.fixture
def records_harness() -> Iterator[tuple[TestClient, InMemoryGraphRepository, InMemoryVectorStore, InMemoryRawRecordStore, Callable[..., int]]]:
    """Harness wired for records flow: medicare_fraud config + in-memory adapters.

    Yields (client, graph_repo, vector_store, raw_record_store, drain_fn) so the
    test can drive the full records→graph→vector pipeline in-process.
    """
    (
        event_bus,
        object_store,
        graph_repo,
        vector_store,
        raw_record_store,
        observation_writer,
        ingestion_service,
        records_config,
    ) = _build_records_harness_deps()

    medicare_config = load_config(_MEDICARE_FRAUD_CONFIG_PATH)
    embedder = InMemoryEmbedder()
    embeddings_service = create_embeddings_service(embedder, event_bus=event_bus)
    graph_service = create_graph_service(
        graph_repo,
        object_store=object_store,
        event_bus=event_bus,
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
    document_chunker = create_document_chunker(medicare_config.ingestion.chunking)
    document_extractor = create_document_extractor(
        medicare_config.entities, medicare_config.relationships
    )
    extraction_validator = create_extraction_validator(
        medicare_config.entities, medicare_config.relationships
    )

    records_service = create_records_service(
        raw_record_store,
        event_bus=event_bus,
        records_config=records_config,
    )

    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: medicare_config
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_graph_repository] = lambda: graph_repo
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_vectorstore_service] = lambda: graph_service
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service
    app.dependency_overrides[get_raw_record_store] = lambda: raw_record_store
    app.dependency_overrides[get_records_service] = lambda: records_service

    def _drain(max_iterations: int = 64) -> int:
        total = 0
        for _ in range(max_iterations):
            processed = asyncio.run(
                drain_ingestion_events(
                    event_bus,
                    ingestion_service,
                    document_chunker,
                    document_extractor,
                    extraction_validator,
                    graph_service,
                    object_store,
                    embeddings_service=embeddings_service,
                    vector_store=vector_store,
                    graph_repository=graph_repo,
                    gnn_service=gnn_service,
                    risk_service=risk_service,
                    explainability_service=explainability_service,
                    monitoring_service=monitoring_service,
                    records_config=records_config,
                    raw_record_store=raw_record_store,
                    observation_writer=observation_writer,
                    consumer_group="e2e-records-workers",
                    consumer_name="e2e-records-worker-1",
                    limit=32,
                )
            )
            total += processed
            if processed == 0:
                break
        return total

    with TestClient(app) as client:
        yield client, graph_repo, vector_store, raw_record_store, _drain

    app.dependency_overrides.clear()


@pytest.mark.e2e
def test_records_e2e_populates_graph_and_vectors_and_cascade_deletes(
    records_harness: tuple[
        TestClient,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        Callable[..., int],
    ],
) -> None:
    """Records flow: upload 3-row CSV → graph+vectors populated → KB delete clears graph.

    Feed: carrier_claims_a (medicare_fraud config).
    Fixture: tiny_carrier_claims.csv — 3 rows, 2 distinct beneficiaries, 2 distinct providers.
    Expected entities: 3 claims + 2 beneficiaries + 2 providers = 7.
    Expected relationships: 3 billed_for + 3 submitted_by = 6.

    Note: The KB DELETE endpoint (v1) clears the graph but does NOT cascade to the
    vector store.  Vector-store cascade is tracked for Phase 2.  This test asserts
    what the implementation actually does.
    """
    client, graph_repo, vector_store, raw_record_store, drain = records_harness

    # 1. Create KB
    create_resp = client.post(
        "/knowledgebases",
        json={"name": "tn-e2e", "description": "slice test"},
    )
    assert create_resp.status_code == 201, create_resp.text
    kb_id = cast("dict[str, object]", create_resp.json())["id"]
    assert isinstance(kb_id, str)

    # 2. Upload 3-row carrier-claims fixture (form field is "feed", not "feed_name")
    with _TINY_CARRIER_CLAIMS_PATH.open("rb") as fh:
        upload_resp = client.post(
            f"/records/{kb_id}/files",
            files={"file": ("tiny_carrier_claims.csv", fh, "text/csv")},
            data={"feed": "carrier_claims_a"},
        )
    assert upload_resp.status_code == 202, upload_resp.text

    # 3. Drain worker in-process until quiescent
    drain()

    # 4. Assert graph populated:
    #    3 claims (C1, C2, C3) + 2 distinct beneficiaries (B0001, B0002)
    #    + 2 distinct providers (1234567890, 2345678901) = 7 entities
    entity_count = graph_repo.count_entities(kb_id)
    assert entity_count == 7, (
        f"Expected 7 entities (3 claims + 2 beneficiaries + 2 providers), got {entity_count}"
    )

    # 5. Assert relationship count:
    #    3 billed_for (each claim → its beneficiary) + 3 submitted_by (each claim → provider) = 6
    rel_count = graph_repo.count_relationships(kb_id)
    assert rel_count == 6, (
        f"Expected 6 relationships (3 billed_for + 3 submitted_by), got {rel_count}"
    )

    # 6. Assert vector index populated: one point per entity (7 total)
    vector_count = vector_store.count_records(kb_id)
    assert vector_count == 7, (
        f"Expected 7 vector records (one per entity), got {vector_count}"
    )

    # 7. Assert raw records persisted: 3 rows accepted
    raw_count = raw_record_store.count_for_kb(kb_id)
    assert raw_count == 3, f"Expected 3 raw records persisted, got {raw_count}"

    # 8. Cascade delete via KB DELETE endpoint
    delete_resp = client.delete(f"/knowledgebases/{kb_id}")
    assert delete_resp.status_code == 204, delete_resp.text

    # 9. Graph cleared by delete
    assert graph_repo.count_entities(kb_id) == 0
    assert graph_repo.count_relationships(kb_id) == 0
    # Vector-store cascade not yet implemented (Phase 2): records remain in the store.
    # Raw-record cascade not yet implemented (Phase 2): records remain in the store.
