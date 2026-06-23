"""JSON parser."""

from __future__ import annotations

import json
from typing import cast

from ingestion.models import (
    DocumentFormat,
    ParsedDocument,
    ParserWarning,
    SourceDocument,
    StructuredRecord,
)
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.utils import build_parser_metadata, charset_fallback_warning, decode_text_content

__all__ = ["JsonParser"]


class JsonParser:
    """Parse JSON objects and arrays into ParsedDocument structures."""

    name = "json"
    version = "1.0"
    supported_formats = (DocumentFormat.JSON,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        text, encoding = decode_text_content(content)
        try:
            payload = cast(object, json.loads(text))
        except json.JSONDecodeError as exc:
            raise ParserError(f"Invalid JSON content: {exc}") from exc

        records: list[StructuredRecord] = []
        text_content: str | None = None
        root_type = type(payload).__name__
        warnings: list[ParserWarning] = []
        charset = charset_fallback_warning("json", encoding)
        if charset is not None:
            warnings.append(charset)

        if isinstance(payload, dict):
            fields = cast(dict[str, object], payload)
            records = [StructuredRecord(id=f"{source.id}-record-0", fields=fields, row_number=0)]
        elif isinstance(payload, list):
            items = cast(list[object], payload)
            if all(isinstance(item, dict) for item in items):
                object_records = [cast(dict[str, object], item) for item in items]
                records = [
                    StructuredRecord(
                        id=f"{source.id}-record-{index}",
                        fields=record,
                        row_number=index,
                    )
                    for index, record in enumerate(object_records)
                ]
            else:
                text_content = json.dumps(payload, indent=2, sort_keys=True)
                warnings.append(
                    ParserWarning(
                        code="json.heterogeneous_array",
                        message=(
                            "Array contains non-object elements; emitted as text instead "
                            "of structured records."
                        ),
                        severity="warning",
                    )
                )
        else:
            text_content = json.dumps(payload, indent=2, sort_keys=True)
            warnings.append(
                ParserWarning(
                    code="json.scalar_root",
                    message=f"Root JSON value is a scalar ({root_type}); emitted as text.",
                    severity="info",
                )
            )

        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            text_content=text_content,
            records=records,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            parser_metadata=build_parser_metadata(
                encoding=encoding,
                root_type=root_type,
                record_count=len(records),
            ),
        )
