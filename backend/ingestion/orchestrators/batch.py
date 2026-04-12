"""Batch parser orchestration helpers."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from ingestion.models import SourceDocument
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.orchestrators.protocols import BatchParseResult, DocumentParseFailure, ParseResult


class BatchParseItem(BaseModel):
    """A single batch parse unit for local or remote orchestration."""

    source_document: SourceDocument
    content: bytes | None = None
    content_type: str | None = None
    filename: str | None = None
    uri: str | None = None

    @model_validator(mode="after")
    def _validate_input(self) -> BatchParseItem:
        has_content = self.content is not None
        has_remote = self.uri is not None or self.source_document.uri is not None
        if has_content or has_remote:
            return self
        raise ValueError("BatchParseItem requires content bytes or a source URI.")


class BatchDocumentParsingOrchestrator:
    """Aggregate single-document parsing with partial-failure support."""

    def __init__(self, orchestrator: DocumentParsingOrchestrator) -> None:
        self._orchestrator = orchestrator

    def parse(self, items: list[BatchParseItem]) -> BatchParseResult:
        result = BatchParseResult()
        for item in items:
            outcome: ParseResult | DocumentParseFailure
            if item.content is not None:
                outcome = self._orchestrator.safe_parse_content(
                    item.source_document,
                    item.content,
                    content_type=item.content_type,
                    filename=item.filename,
                    uri=item.uri,
                )
            else:
                source = item.source_document
                if item.uri is not None:
                    source = source.model_copy(update={"uri": item.uri})
                outcome = self._orchestrator.safe_parse_source(source)

            if isinstance(outcome, ParseResult):
                result.successes.append(outcome)
            else:
                result.failures.append(outcome)
        return result