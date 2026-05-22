"""End-to-end integration tests for the full ingest -> kb.ready pipeline.

These tests exercise the public HTTP surface (``POST /knowledgebases/{id}/documents``)
and drive the worker coordinator in-process via ``drain_ingestion_events``.  All
adapters are in-memory; the assertions verify cross-module integration rather
than internal module behaviour.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import cast

import pytest

from events.types import (
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    GraphUpdatedEvent,
    KnowledgeBaseReadyEvent,
)
from tests.e2e.conftest import E2EHarness


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

_TINY_CARRIER_CLAIMS_PATH = (
    Path(__file__).parent / "fixtures" / "tiny_carrier_claims.csv"
)


@pytest.mark.e2e
def test_records_e2e_populates_graph_and_vectors_and_cascade_deletes(
    medicare_fraud_harness: E2EHarness,
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
    harness = medicare_fraud_harness
    assert harness.raw_record_store is not None, "medicare_fraud_harness must wire raw_record_store"

    # 1. Create KB
    create_resp = harness.client.post(
        "/knowledgebases",
        json={"name": "tn-e2e", "description": "slice test"},
    )
    assert create_resp.status_code == 201, create_resp.text
    kb_id = cast("dict[str, object]", create_resp.json())["id"]
    assert isinstance(kb_id, str)

    # 2. Upload 3-row carrier-claims fixture (form field is "feed", not "feed_name")
    with _TINY_CARRIER_CLAIMS_PATH.open("rb") as fh:
        upload_resp = harness.client.post(
            f"/records/{kb_id}/files",
            files={"file": ("tiny_carrier_claims.csv", fh, "text/csv")},
            data={"feed": "carrier_claims_a"},
        )
    assert upload_resp.status_code == 202, upload_resp.text

    # 3. Drain worker in-process until quiescent
    harness.drain()

    # 4. Assert graph populated:
    #    3 claims (C1, C2, C3) + 2 distinct beneficiaries (B0001, B0002)
    #    + 2 distinct providers (1234567890, 2345678901) = 7 entities
    entity_count = harness.graph_repository.count_entities(kb_id)
    assert entity_count == 7, (
        f"Expected 7 entities (3 claims + 2 beneficiaries + 2 providers), got {entity_count}"
    )

    # 5. Assert relationship count:
    #    3 billed_for (each claim → its beneficiary) + 3 submitted_by (each claim → provider) = 6
    rel_count = harness.graph_repository.count_relationships(kb_id)
    assert rel_count == 6, (
        f"Expected 6 relationships (3 billed_for + 3 submitted_by), got {rel_count}"
    )

    # 6. Assert vector index populated: one point per entity (7 total)
    vector_count = harness.vector_store.count_records(kb_id)
    assert vector_count == 7, (
        f"Expected 7 vector records (one per entity), got {vector_count}"
    )

    # 7. Assert raw records persisted: 3 rows accepted
    raw_count = harness.raw_record_store.count_for_kb(kb_id)
    assert raw_count == 3, f"Expected 3 raw records persisted, got {raw_count}"

    # 8. Cascade delete via KB DELETE endpoint
    delete_resp = harness.client.delete(f"/knowledgebases/{kb_id}")
    assert delete_resp.status_code == 204, delete_resp.text

    # 9. Graph cleared by delete
    assert harness.graph_repository.count_entities(kb_id) == 0
    assert harness.graph_repository.count_relationships(kb_id) == 0
    # Vector-store cascade not yet implemented (Phase 2): records remain in the store.
    # Raw-record cascade not yet implemented (Phase 2): records remain in the store.
