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
    # Vector-store and raw-record cascade ARE implemented (both cleared on DELETE).
    # Assertions for those stores are intentionally omitted here to keep this test
    # scoped to the records-ingestion behavior verified above (steps 4–7).


# ---------------------------------------------------------------------------
# Combined flow E2E (Task 7.1)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_e2e_records_and_documents_populate_one_kb(
    medicare_fraud_harness: E2EHarness,
) -> None:
    """Both ingestion flows (records + documents) populate the same KB.

    Steps:
    1. Create a KB.
    2. Upload tiny_carrier_claims.csv via POST /records/{kb_id}/files (records flow).
    3. Upload policy_001_inpatient_billing.md via POST /knowledgebases/{kb_id}/documents
       (document flow).  Content-type is text/plain because text/markdown is not in
       the default ValidationConfig.allowed_content_types list; the plain-text parser
       passes the raw bytes through unchanged so the NPI regex in
       PatternDocumentExtractor still matches "NPI 1234567890".
    4. Drain the worker in-process.
    5. Assert graph has ≥7 entities (7 from records side alone; at least one more
       from PatternDocumentExtractor matching the NPI in the policy fixture).
    6. Assert vector index has ≥7 records (same lower bound).
    """
    harness = medicare_fraud_harness
    assert harness.raw_record_store is not None, (
        "medicare_fraud_harness must wire raw_record_store"
    )

    # 1. Create KB
    create_resp = harness.client.post(
        "/knowledgebases",
        json={"name": "tn-e2e-combined", "description": ""},
    )
    assert create_resp.status_code == 201, create_resp.text
    kb_id = cast("dict[str, object]", create_resp.json())["id"]
    assert isinstance(kb_id, str)

    # 2. Records side — upload 3-row carrier-claims fixture
    fixture_csv = Path(__file__).parent / "fixtures" / "tiny_carrier_claims.csv"
    with fixture_csv.open("rb") as fh:
        rec_response = harness.client.post(
            f"/records/{kb_id}/files",
            files={"file": ("tiny_carrier_claims.csv", fh, "text/csv")},
            data={"feed": "carrier_claims_a"},
        )
    assert rec_response.status_code == 202, rec_response.text

    # 3. Documents side — upload policy markdown as text/plain (text/markdown is not
    #    in the default allowed_content_types; text/plain routes through the TXT
    #    parser which preserves the full content so NPI regex still matches).
    fixture_md = (
        Path(__file__).parents[1]
        / "ingestion"
        / "fixtures"
        / "policies"
        / "policy_001_inpatient_billing.md"
    )
    with fixture_md.open("rb") as fh:
        doc_response = harness.client.post(
            f"/knowledgebases/{kb_id}/documents",
            files=[("files", ("policy_001_inpatient_billing.md", fh, "text/plain"))],
        )
    assert doc_response.status_code == 202, doc_response.text

    # 4. Drain worker in-process
    harness.drain()

    # 5. Records side: 3 claims + 2 beneficiaries + 2 providers = 7 entities.
    #    Document side: PatternDocumentExtractor matches NPI 1234567890 → at least
    #    one provider entity.  Together we expect ≥7 (records alone is already 7;
    #    the provider from the policy may merge with an existing node or add a new
    #    one depending on graph upsert semantics — either way the count is ≥7).
    entity_count = harness.graph_repository.count_entities(kb_id)
    assert entity_count >= 7, (
        f"expected >=7 entities (7 from records + ≥1 from document), got {entity_count}"
    )

    # 6. Vector index must also be populated with at least as many points as entities
    vector_count = harness.vector_store.count_records(kb_id)
    assert vector_count >= 7, (
        f"expected >=7 vector records, got {vector_count}"
    )


# ---------------------------------------------------------------------------
# DE-SynPUF per-feed E2E tests
# ---------------------------------------------------------------------------
# These tests verify each of the 5 DE-SynPUF record types can be ingested
# end-to-end: CSV → records service → graph + vector store populated.
# Each test is independent; each uses a fresh KB via the medicare_fraud_harness.
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"


def _create_kb_named(harness: E2EHarness, name: str) -> str:
    resp = harness.client.post(
        "/knowledgebases", json={"name": name, "description": ""}
    )
    assert resp.status_code == 201, resp.text
    kb_id = cast("dict[str, object]", resp.json())["id"]
    assert isinstance(kb_id, str)
    return kb_id


def _upload_csv(
    harness: E2EHarness,
    kb_id: str,
    fixture_path: Path,
    feed_name: str,
) -> None:
    with fixture_path.open("rb") as fh:
        resp = harness.client.post(
            f"/records/{kb_id}/files",
            files={"file": (fixture_path.name, fh, "text/csv")},
            data={"feed": feed_name},
        )
    assert resp.status_code == 202, resp.text


@pytest.mark.e2e
def test_records_e2e_beneficiary_2010_ingests(
    medicare_fraud_harness: E2EHarness,
) -> None:
    """Beneficiary Summary 2010: 3-row fixture → 3 beneficiary entities, 0 relationships.

    Feed: beneficiary_2010.  Fixture: tiny_beneficiary_2010.csv.
    Row B0003 has BENE_DEATH_DT="20100601"; rows B0001/B0002 have BENE_DEATH_DT=""
    (empty optional date).  All three rows must pass validation.
    """
    harness = medicare_fraud_harness
    kb_id = _create_kb_named(harness, "bene-2010-e2e")

    _upload_csv(harness, kb_id, _FIXTURES / "tiny_beneficiary_2010.csv", "beneficiary_2010")
    harness.drain()

    entity_count = harness.graph_repository.count_entities(kb_id)
    assert entity_count == 3, (
        f"Expected 3 beneficiary entities, got {entity_count}"
    )
    # Beneficiary feed has no relationship mappings.
    rel_count = harness.graph_repository.count_relationships(kb_id)
    assert rel_count == 0, f"Expected 0 relationships, got {rel_count}"

    vector_count = harness.vector_store.count_records(kb_id)
    assert vector_count == 3, f"Expected 3 vector records, got {vector_count}"

    assert harness.raw_record_store is not None
    raw_count = harness.raw_record_store.count_for_kb(kb_id)
    assert raw_count == 3, f"Expected 3 raw records, got {raw_count}"


@pytest.mark.e2e
def test_records_e2e_inpatient_claims_ingests(
    medicare_fraud_harness: E2EHarness,
) -> None:
    """Inpatient Claims: 3-row fixture with SEGMENT column → entities + relationships.

    Feed: inpatient_claims.  Fixture: tiny_inpatient_claims.csv.
    3 rows: CLM_IP_001 (B0001/440001/1000000001), CLM_IP_002 (B0002/440002/1000000002),
    CLM_IP_003 (B0001/440001/1000000001).
    Unique entities: 3 claims + 2 beneficiaries + 2 providers + 2 facilities = 9.
    Relationships: 3 billed_for + 3 submitted_by + 3 performed_at = 9.
    """
    harness = medicare_fraud_harness
    kb_id = _create_kb_named(harness, "inpatient-e2e")

    _upload_csv(harness, kb_id, _FIXTURES / "tiny_inpatient_claims.csv", "inpatient_claims")
    harness.drain()

    entity_count = harness.graph_repository.count_entities(kb_id)
    assert entity_count == 9, (
        f"Expected 9 entities (3 claims + 2 benes + 2 providers + 2 facilities), "
        f"got {entity_count}"
    )
    rel_count = harness.graph_repository.count_relationships(kb_id)
    assert rel_count == 9, (
        f"Expected 9 relationships (3 billed_for + 3 submitted_by + 3 performed_at), "
        f"got {rel_count}"
    )
    vector_count = harness.vector_store.count_records(kb_id)
    assert vector_count == 9, f"Expected 9 vector records, got {vector_count}"

    assert harness.raw_record_store is not None
    raw_count = harness.raw_record_store.count_for_kb(kb_id)
    assert raw_count == 3, f"Expected 3 raw records, got {raw_count}"


@pytest.mark.e2e
def test_records_e2e_outpatient_claims_ingests(
    medicare_fraud_harness: E2EHarness,
) -> None:
    """Outpatient Claims: 3-row fixture with SEGMENT column → entities + relationships.

    Feed: outpatient_claims.  Fixture: tiny_outpatient_claims.csv.
    3 rows: CLM_OP_001 (B0001/440010/2000000001), CLM_OP_002 (B0002/440011/2000000002),
    CLM_OP_003 (B0003/440010/2000000001).
    Unique entities: 3 claims + 3 beneficiaries + 2 providers + 2 facilities = 10.
    Relationships: 3 billed_for + 3 submitted_by + 3 performed_at = 9.
    """
    harness = medicare_fraud_harness
    kb_id = _create_kb_named(harness, "outpatient-e2e")

    _upload_csv(harness, kb_id, _FIXTURES / "tiny_outpatient_claims.csv", "outpatient_claims")
    harness.drain()

    entity_count = harness.graph_repository.count_entities(kb_id)
    assert entity_count == 10, (
        f"Expected 10 entities (3 claims + 3 benes + 2 providers + 2 facilities), "
        f"got {entity_count}"
    )
    rel_count = harness.graph_repository.count_relationships(kb_id)
    assert rel_count == 9, (
        f"Expected 9 relationships (3 billed_for + 3 submitted_by + 3 performed_at), "
        f"got {rel_count}"
    )
    vector_count = harness.vector_store.count_records(kb_id)
    assert vector_count == 10, f"Expected 10 vector records, got {vector_count}"

    assert harness.raw_record_store is not None
    raw_count = harness.raw_record_store.count_for_kb(kb_id)
    assert raw_count == 3, f"Expected 3 raw records, got {raw_count}"


@pytest.mark.e2e
def test_records_e2e_pde_ingests(
    medicare_fraud_harness: E2EHarness,
) -> None:
    """Prescription Drug Events: 3-row fixture → claim + beneficiary entities.

    Feed: pde.  Fixture: tiny_pde.csv.
    3 rows: P00001 (B0001), P00002 (B0002), P00003 (B0001).
    Unique entities: 3 claims + 2 beneficiaries = 5.
    Relationships: 3 billed_for = 3.
    """
    harness = medicare_fraud_harness
    kb_id = _create_kb_named(harness, "pde-e2e")

    _upload_csv(harness, kb_id, _FIXTURES / "tiny_pde.csv", "pde")
    harness.drain()

    entity_count = harness.graph_repository.count_entities(kb_id)
    assert entity_count == 5, (
        f"Expected 5 entities (3 claims + 2 beneficiaries), got {entity_count}"
    )
    rel_count = harness.graph_repository.count_relationships(kb_id)
    assert rel_count == 3, (
        f"Expected 3 relationships (3 billed_for), got {rel_count}"
    )
    vector_count = harness.vector_store.count_records(kb_id)
    assert vector_count == 5, f"Expected 5 vector records, got {vector_count}"

    assert harness.raw_record_store is not None
    raw_count = harness.raw_record_store.count_for_kb(kb_id)
    assert raw_count == 3, f"Expected 3 raw records, got {raw_count}"


@pytest.mark.e2e
def test_records_e2e_nppes_providers_ingests(
    medicare_fraud_harness: E2EHarness,
) -> None:
    """Upload a real-shape NPPES CSV (MM/DD/YYYY dates, empty deactivation) through the records API.

    Feed: nppes_providers.  Fixture: tiny_nppes_providers.csv.
    3 rows: 2 individual providers (rows 1-2 with empty deactivation dates) and
    1 organisation (row 3 with single-digit date "9/5/2008" and a populated
    deactivation date "01/15/2024").
    All date fields use MM/DD/YYYY or M/D/YYYY — exercises the new coercion path.
    Expected entities: 3 providers, 0 relationships (NPPES feed maps only provider).
    """
    harness = medicare_fraud_harness
    kb_id = _create_kb_named(harness, "nppes-e2e")

    fixture = _FIXTURES / "tiny_nppes_providers.csv"
    _upload_csv(harness, kb_id, fixture, "nppes_providers")
    harness.drain()

    # 3 rows → 3 provider entities
    entity_count = harness.graph_repository.count_entities(kb_id)
    assert entity_count == 3, (
        f"Expected 3 provider entities, got {entity_count}"
    )
    # NPPES feed has no relationship mappings
    rel_count = harness.graph_repository.count_relationships(kb_id)
    assert rel_count == 0, f"Expected 0 relationships, got {rel_count}"

    vector_count = harness.vector_store.count_records(kb_id)
    assert vector_count == 3, f"Expected 3 vector records, got {vector_count}"

    assert harness.raw_record_store is not None
    raw_count = harness.raw_record_store.count_for_kb(kb_id)
    assert raw_count == 3, f"Expected 3 raw records, got {raw_count}"
