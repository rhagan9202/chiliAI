"""Tests for the ingestion service entry point."""

from __future__ import annotations

import logging
from hashlib import sha256

import httpx
import pytest
from prometheus_client import REGISTRY

from events.adapters.in_memory import InMemoryEventBus
from events.protocols import DlqErrorInfo, EventDelivery
from events.types import AnyEvent
from events.types import DocumentReference, DocumentsFailedEvent, DocumentsParsedEvent, DocumentsUploadedEvent
from ingestion.models import ParsedDocument
from ingestion.recovery import (
    IngestionRecoveryMarker,
    InMemoryIngestionRecoveryStore,
    ObjectStoreIngestionRecoveryStore,
)
from ingestion.models import DocumentFormat, IngestionStatus, SourceDocument, SourceType
from ingestion.orchestrators.protocols import DocumentParseFailure, ParseResult
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.service_models import DocumentSubmission, IngestionTask
from storage.adapters.in_memory import InMemoryObjectStore


def _service() -> tuple[IngestionService, InMemoryEventBus, InMemoryObjectStore]:
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
    return service, event_bus, object_store


class FailingPublishBus:
    def __init__(self) -> None:
        self.events: list[AnyEvent] = []

    def publish(self, event: AnyEvent) -> str | None:
        self.events.append(event)
        raise RuntimeError("redis unavailable")

    def ensure_consumer_group(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
    ) -> None:
        return None

    def consume(
        self,
        event_types: list[str],
        *,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
        limit: int = 1,
        block_ms: int | None = None,
    ) -> list[EventDelivery]:
        return []

    def reclaim_stale_pending(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int,
        limit: int = 10,
    ) -> list[EventDelivery]:
        return []

    def ack(self, deliveries: list[EventDelivery]) -> None:
        return None

    def publish_to_dlq(self, event: AnyEvent, error_info: DlqErrorInfo) -> str | None:
        return None


def test_register_documents_stores_content_and_publishes_event() -> None:
    service, event_bus, object_store = _service()

    receipts = service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    assert len(receipts) == 1
    assert receipts[0].storage_key is not None
    stored = object_store.get_bytes(receipts[0].storage_key or "")
    assert stored.content == b'{"claim_id": "42"}'
    assert isinstance(event_bus.published_events[0], DocumentsUploadedEvent)
    assert event_bus.published_events[0].event_type == "documents.uploaded"


def test_register_documents_deduplicates_repeated_content() -> None:
    service, event_bus, object_store = _service()
    submission = DocumentSubmission(
        filename="claims.json",
        content=b'{"claim_id": "42"}',
        content_type="application/json",
    )

    first = service.register_documents("kb-1", [submission])
    second = service.register_documents("kb-1", [submission])

    assert second[0].source_document_id == first[0].source_document_id
    assert second[0].storage_key == first[0].storage_key
    assert first[0].enqueued is True
    assert second[0].enqueued is False
    assert len(event_bus.published_events) == 1
    assert object_store.list_keys("knowledgebases/kb-1/documents/") == [
        first[0].storage_key
    ]


def test_register_documents_deduplicates_repeated_content_with_different_filename() -> None:
    service, event_bus, object_store = _service()

    first = service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )
    second = service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="renamed-claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    assert second[0].source_document_id == first[0].source_document_id
    assert second[0].storage_key == first[0].storage_key
    assert len(event_bus.published_events) == 1
    assert object_store.list_keys("knowledgebases/kb-1/documents/") == [
        first[0].storage_key
    ]


def test_register_documents_ignores_unrelated_objects_under_document_prefix() -> None:
    service, event_bus, object_store = _service()
    submission = DocumentSubmission(
        filename="claims.json",
        content=b'{"claim_id": "42"}',
        content_type="application/json",
    )
    source_document_id = "doc-sha256-" + sha256(submission.content or b"").hexdigest()
    object_store.put_bytes(
        f"knowledgebases/kb-1/documents/{source_document_id}/parsed.json",
        b"{}",
        media_type="application/json",
    )

    receipts = service.register_documents("kb-1", [submission])

    assert receipts[0].source_document_id == source_document_id
    assert receipts[0].storage_key == (
        f"knowledgebases/kb-1/documents/{source_document_id}/source"
    )
    assert receipts[0].enqueued is True
    assert object_store.get_bytes(receipts[0].storage_key or "").content == (
        b'{"claim_id": "42"}'
    )
    assert len(event_bus.published_events) == 1


def test_register_documents_records_recovery_marker_when_publish_fails() -> None:
    recovery_store = InMemoryIngestionRecoveryStore()
    event_bus = FailingPublishBus()
    object_store = InMemoryObjectStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
        recovery_store=recovery_store,
    )

    with pytest.raises(RuntimeError, match="redis unavailable"):
        service.register_documents(
            "kb-1",
            [
                DocumentSubmission(
                    filename="claim.txt",
                    content=b"claim body",
                    content_type="text/plain",
                    document_format=DocumentFormat.TXT,
                )
            ],
        )

    markers = recovery_store.list_markers()
    assert len(markers) == 1
    marker = markers[0]
    assert marker.knowledge_base_id == "kb-1"
    assert marker.source_document_id.startswith("doc-sha256-")
    assert marker.storage_key == f"knowledgebases/kb-1/documents/{marker.source_document_id}/source"
    assert marker.content_hash == sha256(b"claim body").hexdigest()
    assert marker.correlation_id == event_bus.events[0].correlation_id
    assert marker.event_type == "documents.uploaded"
    assert "redis unavailable" in marker.failure_reason
    assert marker.created_at is not None


def test_register_documents_republishes_duplicate_with_recovery_marker() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    recovery_store = InMemoryIngestionRecoveryStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
        recovery_store=recovery_store,
    )
    submission = DocumentSubmission(
        filename="claim.txt",
        content=b"claim body",
        content_type="text/plain",
        document_format=DocumentFormat.TXT,
    )
    first = service.register_documents("kb-1", [submission])
    recovery_store.add_marker(
        IngestionRecoveryMarker(
            marker_id="marker-1",
            knowledge_base_id="kb-1",
            source_document_id=first[0].source_document_id,
            storage_key=first[0].storage_key,
            content_hash=sha256(b"claim body").hexdigest(),
            correlation_id="corr-retry",
            event_type="documents.uploaded",
            failure_reason="publish failed",
        )
    )

    second = service.register_documents("kb-1", [submission], correlation_id="corr-retry")

    assert second[0].source_document_id == first[0].source_document_id
    assert second[0].storage_key == first[0].storage_key
    assert second[0].enqueued is True
    upload_events = [
        event
        for event in event_bus.published_events
        if isinstance(event, DocumentsUploadedEvent)
    ]
    assert len(upload_events) == 2
    assert upload_events[-1].correlation_id == "corr-retry"
    assert upload_events[-1].documents[0].source_document_id == first[0].source_document_id
    assert recovery_store.find_marker(
        event_type="documents.uploaded",
        knowledge_base_id="kb-1",
        source_document_id=first[0].source_document_id,
        content_hash=sha256(b"claim body").hexdigest(),
    ) is None


def test_object_store_recovery_markers_survive_new_store_instance() -> None:
    object_store = InMemoryObjectStore()
    first_store = ObjectStoreIngestionRecoveryStore(object_store)
    marker = IngestionRecoveryMarker(
        marker_id="marker-1",
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        storage_key="knowledgebases/kb-1/documents/doc-1/source",
        content_hash="hash-1",
        correlation_id="corr-1",
        event_type="documents.uploaded",
        failure_reason="publish failed",
    )

    first_store.add_marker(marker)
    second_store = ObjectStoreIngestionRecoveryStore(object_store)

    assert second_store.list_markers() == [marker]
    assert second_store.find_marker(
        event_type="documents.uploaded",
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        content_hash="hash-1",
    ) == marker


def test_replay_recovery_markers_publishes_uploaded_event_and_removes_marker() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    recovery_store = ObjectStoreIngestionRecoveryStore(object_store)
    storage_key = "knowledgebases/kb-1/documents/doc-1/source"
    object_store.put_bytes(
        storage_key,
        b"claim body",
        media_type="text/plain",
        metadata={
            "knowledge_base_id": "kb-1",
            "source_document_id": "doc-1",
            "checksum": "hash-1",
            "filename": "claim.txt",
            "document_format": DocumentFormat.TXT.value,
            "source_type": SourceType.FILE_UPLOAD.value,
        },
    )
    recovery_store.add_marker(
        IngestionRecoveryMarker(
            marker_id="marker-1",
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            storage_key=storage_key,
            content_hash="hash-1",
            correlation_id="corr-1",
            event_type="documents.uploaded",
            failure_reason="publish failed",
        )
    )
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
        recovery_store=recovery_store,
    )

    replayed = service.replay_recovery_markers()

    assert replayed == 1
    assert recovery_store.list_markers() == []
    published = event_bus.published_events[-1]
    assert isinstance(published, DocumentsUploadedEvent)
    assert published.correlation_id == "corr-1"
    assert published.documents[0].knowledge_base_id == "kb-1"
    assert published.documents[0].source_document_id == "doc-1"
    assert published.documents[0].filename == "claim.txt"
    assert published.documents[0].content_type == "text/plain"
    assert published.documents[0].storage_key == storage_key
    assert published.documents[0].document_format == DocumentFormat.TXT.value
    assert published.documents[0].source_type == SourceType.FILE_UPLOAD.value
    assert published.documents[0].size_bytes == len(b"claim body")


def test_replay_recovery_markers_leaves_marker_when_publish_fails() -> None:
    event_bus = FailingPublishBus()
    object_store = InMemoryObjectStore()
    recovery_store = ObjectStoreIngestionRecoveryStore(object_store)
    storage_key = "knowledgebases/kb-1/documents/doc-1/source"
    object_store.put_bytes(storage_key, b"claim body", media_type="text/plain")
    marker = IngestionRecoveryMarker(
        marker_id="marker-1",
        knowledge_base_id="kb-1",
        source_document_id="doc-1",
        storage_key=storage_key,
        content_hash="hash-1",
        correlation_id="corr-1",
        event_type="documents.uploaded",
        failure_reason="publish failed",
    )
    recovery_store.add_marker(marker)
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
        recovery_store=recovery_store,
    )

    with pytest.raises(RuntimeError, match="redis unavailable"):
        service.replay_recovery_markers()

    assert recovery_store.list_markers() == [marker]


def test_register_documents_uses_full_content_digest_for_id() -> None:
    """Document identity uses the full SHA-256 digest, not a truncated prefix.

    Regression for ingestion.33: a 24-hex (96-bit) prefix could collide and
    silently route a new upload into the dedup path. The id must retain the
    full digest so no identity information is discarded.
    """
    service, _, _ = _service()
    content = b'{"claim_id": "42"}'

    receipts = service.register_documents(
        "kb-1",
        [DocumentSubmission(filename="c.json", content=content, content_type="application/json")],
    )

    assert receipts[0].source_document_id == "doc-sha256-" + sha256(content).hexdigest()


def test_register_documents_uses_full_uri_digest_for_id() -> None:
    """Remote-URI identity also uses the full SHA-256 digest (ingestion.33)."""
    service, _, _ = _service()
    uri = "https://example.test/policy.json"

    receipts = service.register_documents(
        "kb-1",
        [DocumentSubmission(uri=uri, content_type="application/json")],
    )

    assert receipts[0].source_document_id == "doc-uri-" + sha256(uri.encode("utf-8")).hexdigest()


def test_register_documents_distinguishes_contents_sharing_a_digest_prefix() -> None:
    """Contents whose digests share a 24-hex prefix still get distinct ids.

    Real SHA-256 prefix collisions are infeasible to construct, so this guards
    the property directly: identity is the full digest, so any two distinct
    contents map to distinct ids and the dedup path is never falsely entered.
    """
    service, _, _ = _service()
    first = b'{"claim_id": "a"}'
    second = b'{"claim_id": "b"}'

    first_receipts = service.register_documents(
        "kb-1",
        [DocumentSubmission(filename="a.json", content=first, content_type="application/json")],
    )
    second_receipts = service.register_documents(
        "kb-1",
        [DocumentSubmission(filename="b.json", content=second, content_type="application/json")],
    )

    assert first_receipts[0].source_document_id != second_receipts[0].source_document_id
    assert first_receipts[0].source_document_id == "doc-sha256-" + sha256(first).hexdigest()
    assert second_receipts[0].source_document_id == "doc-sha256-" + sha256(second).hexdigest()


def test_register_documents_deduplicates_repeated_remote_uri() -> None:
    service, event_bus, object_store = _service()
    submission = DocumentSubmission(
        uri="https://example.test/policy.json",
        content_type="application/json",
    )

    first = service.register_documents("kb-1", [submission])
    second = service.register_documents("kb-1", [submission])

    assert second[0].source_document_id == first[0].source_document_id
    assert second[0].uri == first[0].uri
    assert len(event_bus.published_events) == 1
    assert len(object_store.list_keys("knowledgebases/kb-1/documents/")) == 1


def test_ingest_task_parses_stored_document_and_publishes_parsed_event() -> None:
    service, event_bus, object_store = _service()
    storage_key = "knowledgebases/kb-1/documents/doc-1/claims.json"
    object_store.put_bytes(storage_key, b'{"claim_id": "42"}', media_type="application/json")

    outcome = service.ingest_task(
        IngestionTask(
            knowledge_base_id="kb-1",
            source_document=SourceDocument(
                id="doc-1",
                source_type=SourceType.FILE_UPLOAD,
                filename="claims.json",
            ),
            storage_key=storage_key,
            content_type="application/json",
        ),
        correlation_id="corr-parse-1",
    )

    assert isinstance(event_bus.published_events[-1], DocumentsParsedEvent)
    assert isinstance(outcome, ParseResult)
    assert outcome.parsed_document.records[0].fields["claim_id"] == "42"
    parsed_event = event_bus.published_events[-1]
    assert parsed_event.correlation_id == "corr-parse-1"
    assert parsed_event.documents[0].parsed_document_storage_key is not None
    assert parsed_event.documents[0].warning_count == len(outcome.parsed_document.warnings) == 0

    stored = object_store.get_bytes(parsed_event.documents[0].parsed_document_storage_key or "")
    parsed_document = ParsedDocument.model_validate_json(stored.content)
    assert parsed_document.id == outcome.parsed_document.id
    assert parsed_document.records[0].fields["claim_id"] == "42"


def test_ingest_task_propagates_parser_warning_count() -> None:
    service, event_bus, object_store = _service()
    storage_key = "knowledgebases/kb-1/documents/doc-csv/claims.csv"
    object_store.put_bytes(storage_key, b"claim_id,amount\n1,100,extra\n", media_type="text/csv")

    outcome = service.ingest_task(
        IngestionTask(
            knowledge_base_id="kb-1",
            source_document=SourceDocument(
                id="doc-csv",
                source_type=SourceType.FILE_UPLOAD,
                filename="claims.csv",
            ),
            storage_key=storage_key,
            content_type="text/csv",
        ),
        correlation_id="corr-warn-1",
    )

    assert isinstance(outcome, ParseResult)
    assert outcome.parsed_document.warnings  # ragged row produced a warning
    parsed_event = event_bus.published_events[-1]
    assert isinstance(parsed_event, DocumentsParsedEvent)
    assert parsed_event.documents[0].warning_count == len(outcome.parsed_document.warnings)
    assert parsed_event.documents[0].warning_count >= 1
    assert parsed_event.documents[0].warning_samples
    assert any(
        sample.startswith("csv.ragged_row")
        for sample in parsed_event.documents[0].warning_samples
    )


def test_process_documents_uploaded_publishes_failure_for_unresolved_format() -> None:
    service, event_bus, _object_store = _service()
    uploaded = DocumentsUploadedEvent(
        correlation_id="corr-failed-1",
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-failed",
                filename=None,
                content_type=None,
                storage_key=None,
                uri=None,
                document_format=None,
                size_bytes=None,
            )
        ]
    )

    outcomes = service.process_documents_uploaded(uploaded)

    assert len(outcomes) == 1
    assert isinstance(event_bus.published_events[-1], DocumentsFailedEvent)
    assert event_bus.published_events[-1].correlation_id == "corr-failed-1"
    assert isinstance(outcomes[0], DocumentParseFailure)
    assert outcomes[0].error_type == "RemoteFetchError"


def test_process_documents_uploaded_publishes_failure_for_malformed_remote_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/csv", "content-length": "invalid"},
            content=b"id,name\n1,Alice\n",
            request=request,
        )

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(
                client=httpx.Client(
                    transport=httpx.MockTransport(handler),
                    follow_redirects=True,
                )
            ),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    uploaded = DocumentsUploadedEvent(
        correlation_id="corr-invalid-length",
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-invalid-length",
                filename="claims.csv",
                content_type=None,
                storage_key=None,
                uri="https://example.com/claims.csv",
                document_format=None,
                size_bytes=None,
            )
        ],
    )

    outcomes = service.process_documents_uploaded(uploaded)

    assert len(outcomes) == 1
    assert isinstance(outcomes[0], DocumentParseFailure)
    assert outcomes[0].error_type == "RemoteFetchError"
    assert "invalid content-length" in outcomes[0].error_message
    assert isinstance(event_bus.published_events[-1], DocumentsFailedEvent)
    assert event_bus.published_events[-1].correlation_id == "corr-invalid-length"


def test_process_documents_uploaded_preserves_event_source_metadata() -> None:
    service, _event_bus, _object_store = _service()
    uploaded = DocumentsUploadedEvent(
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-batch",
                filename="batch.json",
                content_type="application/json",
                storage_key=None,
                uri=None,
                document_format=DocumentFormat.JSON.value,
                source_type=SourceType.BATCH_LOAD.value,
                size_bytes=123,
            )
        ]
    )

    outcomes = service.process_documents_uploaded(uploaded)

    assert outcomes[0].source_document.source_type is SourceType.BATCH_LOAD
    assert outcomes[0].source_document.size_bytes == 123


def test_ingest_task_publishes_failure_when_source_object_missing() -> None:
    service, event_bus, _object_store = _service()

    outcome = service.ingest_task(
        IngestionTask(
            knowledge_base_id="kb-1",
            source_document=SourceDocument(
                id="doc-missing",
                source_type=SourceType.FILE_UPLOAD,
                filename="claims.json",
            ),
            storage_key="knowledgebases/kb-1/documents/doc-missing/source",
            content_type="application/json",
        ),
        correlation_id="corr-missing-1",
    )

    assert isinstance(outcome, DocumentParseFailure)
    assert outcome.source_document.status is IngestionStatus.FAILED
    assert outcome.error_type == "KeyError"
    failed_event = event_bus.published_events[-1]
    assert isinstance(failed_event, DocumentsFailedEvent)
    assert failed_event.correlation_id == "corr-missing-1"
    assert failed_event.documents[0].source_document_id == "doc-missing"


def test_process_documents_uploaded_isolates_missing_object_failure() -> None:
    service, event_bus, object_store = _service()
    good_key = "knowledgebases/kb-1/documents/doc-good/source"
    object_store.put_bytes(good_key, b'{"claim_id": "42"}', media_type="application/json")

    uploaded = DocumentsUploadedEvent(
        correlation_id="corr-mixed-1",
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-missing",
                filename="missing.json",
                content_type="application/json",
                storage_key="knowledgebases/kb-1/documents/doc-missing/source",
                uri=None,
                document_format=DocumentFormat.JSON.value,
                size_bytes=None,
            ),
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-good",
                filename="good.json",
                content_type="application/json",
                storage_key=good_key,
                uri=None,
                document_format=DocumentFormat.JSON.value,
                size_bytes=None,
            ),
        ],
    )

    outcomes = service.process_documents_uploaded(uploaded)

    assert isinstance(outcomes[0], DocumentParseFailure)
    assert isinstance(outcomes[1], ParseResult)
    published_types = [type(event) for event in event_bus.published_events]
    assert DocumentsFailedEvent in published_types
    assert DocumentsParsedEvent in published_types


def _has_stage_field(text: str, key: str, value: str) -> bool:
    """Match a structured field under either renderer: console (key=value) or JSON."""
    return f"{key}={value}" in text or f'"{key}": "{value}"' in text


def test_ingest_task_emits_parse_stage_log_with_success_outcome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, _event_bus, object_store = _service()
    storage_key = "knowledgebases/kb-1/documents/doc-1/claims.json"
    object_store.put_bytes(
        storage_key, b'{"claim_id": "42"}', media_type="application/json"
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        outcome = service.ingest_task(
            IngestionTask(
                knowledge_base_id="kb-1",
                source_document=SourceDocument(
                    id="doc-1",
                    source_type=SourceType.FILE_UPLOAD,
                    filename="claims.json",
                ),
                storage_key=storage_key,
                content_type="application/json",
            ),
            correlation_id="corr-stage-log",
        )

    assert isinstance(outcome, ParseResult)
    assert _has_stage_field(caplog.text, "stage", "parse")
    assert _has_stage_field(caplog.text, "kb_id", "kb-1")
    assert _has_stage_field(caplog.text, "source_document_id", "doc-1")
    assert _has_stage_field(caplog.text, "outcome", "success")
    assert "duration_ms" in caplog.text


def test_ingest_task_failure_increments_failed_counter_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, event_bus, _object_store = _service()
    labels = {"stage": "parse", "error_class": "RemoteFetchError"}
    before = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    uploaded = DocumentsUploadedEvent(
        correlation_id="corr-failed-counter",
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-failed-counter",
                filename=None,
                content_type=None,
                storage_key=None,
                uri=None,
                document_format=None,
                size_bytes=None,
            )
        ],
    )

    with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
        outcomes = service.process_documents_uploaded(uploaded)

    assert isinstance(outcomes[0], DocumentParseFailure)
    assert outcomes[0].error_type == "RemoteFetchError"
    assert isinstance(event_bus.published_events[-1], DocumentsFailedEvent)
    after = REGISTRY.get_sample_value("ingestion_documents_failed_total", labels) or 0.0
    assert after == before + 1.0
    assert _has_stage_field(caplog.text, "stage", "parse")
    assert _has_stage_field(caplog.text, "outcome", "failed")


def test_register_documents_duplicate_increments_dedup_counter() -> None:
    service, _event_bus, _object_store = _service()
    submission = DocumentSubmission(
        filename="claims.json",
        content=b'{"claim_id": "dedup-counter"}',
        content_type="application/json",
    )
    labels = {"kind": "document"}

    first = service.register_documents("kb-dedup", [submission])
    baseline = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    second = service.register_documents("kb-dedup", [submission])

    assert first[0].enqueued is True
    assert second[0].enqueued is False
    after = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    assert after == baseline + 1.0
