"""Service entry point for API and worker ingestion flows."""

from __future__ import annotations

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
from shared.utils import generate_id
from storage.protocols import ObjectStore


class IngestionService:
    """Coordinate document registration, parsing, and event publication."""

    def __init__(
        self,
        parser_orchestrator: ParserOrchestrator,
        *,
        object_store: ObjectStore,
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
            source_document = SourceDocument(
                id=generate_id(),
                source_type=source_type,
                document_format=submission.document_format,
                filename=submission.filename,
                uri=submission.uri,
                media_type=submission.content_type,
                size_bytes=len(submission.content) if submission.content is not None else None,
            )

            storage_key: str | None = None
            if submission.content is not None:
                storage_key = self._build_storage_key(
                    knowledge_base_id,
                    source_document.id,
                    submission.filename,
                )
                stored = self._object_store.put_bytes(
                    storage_key,
                    submission.content,
                    media_type=submission.content_type,
                    metadata={
                        "knowledge_base_id": knowledge_base_id,
                        "source_document_id": source_document.id,
                    },
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

        self._event_bus.publish(DocumentsUploadedEvent(documents=document_references))
        return receipts

    def ingest_task(self, task: IngestionTask) -> ParseResult | DocumentParseFailure:
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
                source_type=SourceType.API_PUSH if document.uri else SourceType.FILE_UPLOAD,
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
                    )
                )
            )
        return results

    @staticmethod
    def _build_storage_key(
        knowledge_base_id: str,
        source_document_id: str,
        filename: str | None,
    ) -> str:
        suffix = filename or "document"
        return f"knowledgebases/{knowledge_base_id}/documents/{source_document_id}/{suffix}"

    @staticmethod
    def _build_parsed_storage_key(
        knowledge_base_id: str,
        parsed_document_id: str,
    ) -> str:
        return f"knowledgebases/{knowledge_base_id}/parsed/{parsed_document_id}.json"


__all__ = [
    "IngestionService",
]