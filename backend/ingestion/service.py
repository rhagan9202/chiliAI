"""Service entry point for API and worker ingestion flows."""

from __future__ import annotations

from hashlib import sha256

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.orchestrators.protocols import (
    DocumentParseFailure,
    ParseResult,
    ParserOrchestrator,
)
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
    ) -> None:
        self._parser_orchestrator = parser_orchestrator
        self._object_store = object_store
        self._event_bus = event_bus

    def register_documents(
        self,
        knowledge_base_id: str,
        submissions: list[DocumentSubmission],
    ) -> list[DocumentReceipt]:
        document_references: list[DocumentReference] = []
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
                should_publish = not already_registered
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
            self._event_bus.publish(DocumentsUploadedEvent(documents=document_references))
        return receipts

    def ingest_task(
        self,
        task: IngestionTask,
        *,
        correlation_id: str | None = None,
    ) -> ParseResult | DocumentParseFailure:
        if task.storage_key is not None:
            stored = self._object_store.get_bytes(task.storage_key)
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
        prefix = f"knowledgebases/{knowledge_base_id}/documents/{source_document_id}/"
        existing_keys = self._object_store.list_keys(prefix)
        return existing_keys[0] if existing_keys else None

    @staticmethod
    def _build_remote_marker_key(
        knowledge_base_id: str,
        source_document_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/documents/{source_document_id}/remote.marker"

    @staticmethod
    def _source_document_id(submission: DocumentSubmission) -> str:
        if submission.content is not None:
            return f"doc-sha256-{sha256(submission.content).hexdigest()[:24]}"
        if submission.uri is not None:
            uri_hash = sha256(submission.uri.encode("utf-8")).hexdigest()
            return f"doc-uri-{uri_hash[:24]}"
        return generate_id()

    @staticmethod
    def _build_parsed_storage_key(
        knowledge_base_id: str,
        parsed_document_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/parsed/{parsed_document_id}.json"


__all__ = [
    "IngestionService",
]
