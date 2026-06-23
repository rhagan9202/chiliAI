"""Service entry point for API and worker ingestion flows."""

from __future__ import annotations

import logging
from hashlib import sha256

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.orchestrators.protocols import (
    DocumentParseFailure,
    ParseResult,
    ParserOrchestrator,
)
from ingestion.orchestrators.source_documents import mark_failed, mark_parsing
from ingestion.recovery import IngestionRecoveryMarker, IngestionRecoveryStore
from ingestion.service_models import DocumentReceipt, DocumentSubmission, IngestionTask
from events.protocols import EventBus
from events.types import (
    DocumentFailureReference,
    DocumentReference,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    ParsedDocumentReference,
)
from shared.protocols import ObjectStoreProtocol
from shared.utils import generate_id

logger = logging.getLogger(__name__)


class IngestionService:
    """Coordinate document registration, parsing, and event publication."""

    # TODO(production): Add error recovery: if event publication fails after
    # storage, persist a retry record. Add progress reporting via events or
    # status polling. Make I/O operations async (object store, event bus). Add
    # configurable file size limits and content-type whitelisting at this layer.

    def __init__(
        self,
        parser_orchestrator: ParserOrchestrator,
        *,
        object_store: ObjectStoreProtocol,
        event_bus: EventBus,
        recovery_store: IngestionRecoveryStore | None = None,
    ) -> None:
        self._parser_orchestrator = parser_orchestrator
        self._object_store = object_store
        self._event_bus = event_bus
        self._recovery_store = recovery_store

    def register_documents(
        self,
        knowledge_base_id: str,
        submissions: list[DocumentSubmission],
        *,
        correlation_id: str | None = None,
    ) -> list[DocumentReceipt]:
        """Persist documents and publish ``documents.uploaded``.

        When ``correlation_id`` is provided it is stamped on the published
        event so a workflow run started by the API for the same correlation is
        advanced by the worker's tracker (rather than a fallback run). When
        omitted, a fresh correlation id is generated as before.
        """
        document_references: list[DocumentReference] = []
        content_hashes_by_source_document_id: dict[str, str | None] = {}
        recovery_markers_by_source_document_id: dict[str, IngestionRecoveryMarker] = {}
        receipts: list[DocumentReceipt] = []

        for submission in submissions:
            source_type = submission.source_type or (
                SourceType.API_PUSH if submission.uri is not None else SourceType.FILE_UPLOAD
            )
            source_document_id = self._source_document_id(submission)
            checksum = (
                sha256(submission.content).hexdigest()
                if submission.content is not None
                else None
            )
            content_hashes_by_source_document_id[source_document_id] = checksum
            source_document = SourceDocument(
                id=source_document_id,
                source_type=source_type,
                document_format=submission.document_format,
                filename=submission.filename,
                uri=submission.uri,
                media_type=submission.content_type,
                checksum=checksum,
                size_bytes=len(submission.content) if submission.content is not None else None,
            )

            storage_key: str | None = None
            should_publish = True
            if submission.content is not None:
                storage_key = self._build_storage_key(
                    knowledge_base_id,
                    source_document.id,
                )
                existing_storage_key = self._existing_document_storage_key(
                    knowledge_base_id,
                    source_document.id,
                )
                if existing_storage_key is not None:
                    storage_key = existing_storage_key
                already_registered = existing_storage_key is not None
                recovery_marker = (
                    self._recovery_store.find_marker(
                        event_type="documents.uploaded",
                        knowledge_base_id=knowledge_base_id,
                        source_document_id=source_document.id,
                        content_hash=checksum,
                    )
                    if already_registered and self._recovery_store is not None
                    else None
                )
                if recovery_marker is not None:
                    recovery_markers_by_source_document_id[source_document.id] = (
                        recovery_marker
                    )
                should_publish = not already_registered or recovery_marker is not None
                stored = (
                    self._object_store.get_bytes(storage_key)
                    if already_registered
                    else self._object_store.put_bytes(
                        storage_key,
                        submission.content,
                        media_type=submission.content_type,
                        metadata={
                            "knowledge_base_id": knowledge_base_id,
                            "source_document_id": source_document.id,
                            "checksum": checksum or "",
                            "filename": source_document.filename or "",
                            "document_format": (
                                source_document.document_format.value
                                if source_document.document_format is not None
                                else ""
                            ),
                            "source_type": source_document.source_type.value,
                            "idempotency_strategy": "sha256",
                        },
                    )
                )
                source_document = source_document.model_copy(
                    update={
                        "size_bytes": stored.size_bytes,
                        "metadata": {
                            **source_document.metadata,
                            "storage_key": stored.key,
                        },
                    }
                )
            elif submission.uri is not None:
                marker_key = self._build_remote_marker_key(
                    knowledge_base_id,
                    source_document.id,
                )
                should_publish = not self._object_store.exists(marker_key)
                if should_publish:
                    self._object_store.put_bytes(
                        marker_key,
                        b"",
                        media_type="application/octet-stream",
                        metadata={
                            "knowledge_base_id": knowledge_base_id,
                            "source_document_id": source_document.id,
                            "uri": submission.uri,
                            "idempotency_strategy": "uri_sha256",
                        },
                    )

            if should_publish:
                document_references.append(
                    DocumentReference(
                        knowledge_base_id=knowledge_base_id,
                        source_document_id=source_document.id,
                        filename=source_document.filename,
                        content_type=source_document.media_type,
                        storage_key=storage_key,
                        uri=source_document.uri,
                        document_format=(
                            source_document.document_format.value
                            if source_document.document_format is not None
                            else None
                        ),
                        source_type=source_document.source_type.value,
                        size_bytes=source_document.size_bytes,
                    )
                )
            receipts.append(
                DocumentReceipt(
                    knowledge_base_id=knowledge_base_id,
                    source_document_id=source_document.id,
                    filename=source_document.filename,
                    status=source_document.status,
                    storage_key=storage_key,
                    uri=source_document.uri,
                    document_format=source_document.document_format,
                )
            )

        if document_references:
            event = DocumentsUploadedEvent(
                correlation_id=correlation_id or generate_id(),
                documents=document_references,
            )
            try:
                self._event_bus.publish(event)
            except Exception as exc:
                if self._recovery_store is not None:
                    for reference in document_references:
                        self._recovery_store.add_marker(
                            IngestionRecoveryMarker(
                                knowledge_base_id=reference.knowledge_base_id,
                                source_document_id=reference.source_document_id,
                                storage_key=reference.storage_key,
                                content_hash=content_hashes_by_source_document_id.get(
                                    reference.source_document_id
                                ),
                                correlation_id=event.correlation_id,
                                event_type=event.event_type,
                                failure_reason=str(exc),
                            )
                        )
                raise
            enqueued_source_document_ids = {
                reference.source_document_id for reference in document_references
            }
            receipts = [
                receipt.model_copy(update={"enqueued": True})
                if receipt.source_document_id in enqueued_source_document_ids
                else receipt
                for receipt in receipts
            ]
            if self._recovery_store is not None:
                for marker in recovery_markers_by_source_document_id.values():
                    self._recovery_store.remove_marker(marker.marker_id)
        return receipts

    def replay_recovery_markers(self) -> int:
        """Republish durable ``documents.uploaded`` markers.

        Markers are removed only after the event bus accepts the reconstructed
        event. If the source object is missing, the marker stays in place for
        operator inspection or a later repair.
        """

        if self._recovery_store is None:
            return 0

        replayed = 0
        for marker in self._recovery_store.list_markers(event_type="documents.uploaded"):
            if marker.storage_key is None:
                continue
            try:
                stored = self._object_store.get_bytes(marker.storage_key)
            except KeyError:
                continue

            event = DocumentsUploadedEvent(
                correlation_id=marker.correlation_id,
                documents=[
                    DocumentReference(
                        knowledge_base_id=marker.knowledge_base_id,
                        source_document_id=marker.source_document_id,
                        filename=_metadata_string(stored.metadata.get("filename")),
                        content_type=stored.media_type,
                        storage_key=marker.storage_key,
                        uri=_metadata_string(stored.metadata.get("uri")),
                        document_format=_metadata_string(
                            stored.metadata.get("document_format")
                        ),
                        source_type=(
                            _metadata_string(stored.metadata.get("source_type"))
                            or SourceType.FILE_UPLOAD.value
                        ),
                        size_bytes=stored.size_bytes,
                    )
                ],
            )
            self._event_bus.publish(event)
            self._recovery_store.remove_marker(marker.marker_id)
            replayed += 1
        return replayed

    def ingest_task(
        self,
        task: IngestionTask,
        *,
        correlation_id: str | None = None,
    ) -> ParseResult | DocumentParseFailure:
        outcome: ParseResult | DocumentParseFailure
        if task.storage_key is not None:
            try:
                stored = self._object_store.get_bytes(task.storage_key)
            except Exception as exc:  # noqa: BLE001 - read failure becomes a typed failure
                logger.error(
                    "Failed to read source object for source_document_id=%s "
                    "storage_key=%s error_class=%s: %s",
                    task.source_document.id,
                    task.storage_key,
                    type(exc).__name__,
                    exc,
                )
                outcome = DocumentParseFailure(
                    source_document=mark_failed(mark_parsing(task.source_document), str(exc)),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            else:
                outcome = self._parser_orchestrator.safe_parse_content(
                    task.source_document,
                    stored.content,
                    content_type=stored.media_type or task.content_type,
                    filename=task.source_document.filename,
                    uri=task.source_document.uri,
                )
        else:
            outcome = self._parser_orchestrator.safe_parse_source(task.source_document)

        if isinstance(outcome, ParseResult):
            parsed_document_storage_key = self._build_parsed_storage_key(
                task.knowledge_base_id,
                outcome.parsed_document.id,
            )
            self._object_store.put_bytes(
                parsed_document_storage_key,
                outcome.parsed_document.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": task.knowledge_base_id,
                    "source_document_id": outcome.source_document.id,
                    "parsed_document_id": outcome.parsed_document.id,
                },
            )
            self._event_bus.publish(
                DocumentsParsedEvent(
                    correlation_id=correlation_id or generate_id(),
                    documents=[
                        ParsedDocumentReference(
                            knowledge_base_id=task.knowledge_base_id,
                            source_document_id=outcome.source_document.id,
                            parsed_document_id=outcome.parsed_document.id,
                            parser_name=outcome.parsed_document.parser_name,
                            parser_version=outcome.parsed_document.parser_version,
                            document_format=(
                                outcome.source_document.document_format.value
                                if outcome.source_document.document_format is not None
                                else None
                            ),
                            storage_key=task.storage_key,
                            parsed_document_storage_key=parsed_document_storage_key,
                        )
                    ]
                )
            )
            return outcome

        self._event_bus.publish(
            DocumentsFailedEvent(
                correlation_id=correlation_id or generate_id(),
                documents=[
                    DocumentFailureReference(
                        knowledge_base_id=task.knowledge_base_id,
                        source_document_id=outcome.source_document.id,
                        error_message=outcome.error_message,
                        storage_key=task.storage_key,
                    )
                ]
            )
        )
        return outcome

    def process_documents_uploaded(
        self,
        event: DocumentsUploadedEvent,
    ) -> list[ParseResult | DocumentParseFailure]:
        results: list[ParseResult | DocumentParseFailure] = []
        for document in event.documents:
            source_document = SourceDocument(
                id=document.source_document_id,
                source_type=(
                    SourceType(document.source_type)
                    if document.source_type is not None
                    else SourceType.API_PUSH
                    if document.uri
                    else SourceType.FILE_UPLOAD
                ),
                document_format=(
                    DocumentFormat(document.document_format)
                    if document.document_format is not None
                    else None
                ),
                filename=document.filename,
                uri=document.uri,
                media_type=document.content_type,
                size_bytes=document.size_bytes,
            )
            results.append(
                self.ingest_task(
                    IngestionTask(
                        knowledge_base_id=document.knowledge_base_id,
                        source_document=source_document,
                        storage_key=document.storage_key,
                        content_type=document.content_type,
                    ),
                    correlation_id=event.correlation_id,
                )
            )
        return results

    @staticmethod
    def _build_storage_key(
        knowledge_base_id: str,
        source_document_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/documents/{source_document_id}/source"

    def _existing_document_storage_key(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> str | None:
        storage_key = self._build_storage_key(knowledge_base_id, source_document_id)
        return storage_key if self._object_store.exists(storage_key) else None

    @staticmethod
    def _build_remote_marker_key(
        knowledge_base_id: str,
        source_document_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/documents/{source_document_id}/remote.marker"

    @staticmethod
    def _source_document_id(submission: DocumentSubmission) -> str:
        # Identity uses the full 64-char SHA-256 hex digest. A truncated prefix
        # (formerly 24 hex / 96 bits) could collide and silently route a new
        # upload into the dedup path, returning another document's bytes
        # (ingestion.33).
        if submission.content is not None:
            return f"doc-sha256-{sha256(submission.content).hexdigest()}"
        if submission.uri is not None:
            uri_hash = sha256(submission.uri.encode("utf-8")).hexdigest()
            return f"doc-uri-{uri_hash}"
        return generate_id()

    @staticmethod
    def _build_parsed_storage_key(
        knowledge_base_id: str,
        parsed_document_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/parsed/{parsed_document_id}.json"


def _metadata_string(value: object) -> str | None:
    if not isinstance(value, str) or value == "":
        return None
    return value


__all__ = [
    "IngestionService",
]
