"""CSV parser."""

from __future__ import annotations

import csv
from io import StringIO

from ingestion.models import (
    DocumentFormat,
    ParsedDocument,
    ParserWarning,
    SourceDocument,
    StructuredRecord,
)
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.utils import build_parser_metadata, charset_fallback_warning, decode_text_content

__all__ = ["CsvParser"]


class CsvParser:
    """Parse delimited text into structured records."""

    name = "csv"
    version = "1.0"
    supported_formats = (DocumentFormat.CSV,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        text, encoding = decode_text_content(content)
        if not text.strip():
            raise ParserError("CSV content is empty.")

        warnings: list[ParserWarning] = []
        charset = charset_fallback_warning("csv", encoding)
        if charset is not None:
            warnings.append(charset)

        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            dialect = csv.excel
            has_header = True
            warnings.append(
                ParserWarning(
                    code="csv.dialect_fallback",
                    message="Could not sniff the CSV dialect; fell back to comma-delimited with a header row.",
                    severity="warning",
                )
            )

        rows = list(csv.reader(StringIO(text), dialect=dialect))
        if not rows:
            raise ParserError("CSV content does not contain any rows.")

        if has_header:
            headers = [header.strip() or f"column_{index + 1}" for index, header in enumerate(rows[0])]
            data_rows = rows[1:]
        else:
            headers = [f"column_{index + 1}" for index in range(len(rows[0]))]
            data_rows = rows

        records: list[StructuredRecord] = []
        for row_index, row in enumerate(data_rows):
            if len(row) != len(headers):
                warnings.append(
                    ParserWarning(
                        code="csv.ragged_row",
                        message=(
                            f"Row has {len(row)} field(s) but the header declares {len(headers)}; "
                            "extra fields dropped and missing fields omitted."
                        ),
                        severity="warning",
                        row_index=row_index,
                    )
                )
            fields: dict[str, object] = {
                headers[index]: row[index] for index in range(min(len(headers), len(row)))
            }
            records.append(
                StructuredRecord(
                    id=f"{source.id}-row-{row_index}",
                    row_number=row_index,
                    fields=fields,
                )
            )

        if not records:
            raise ParserError("CSV content contains headers but no data rows.")

        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            records=records,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            parser_metadata=build_parser_metadata(
                encoding=encoding,
                delimiter=getattr(dialect, "delimiter", ","),
                has_header=has_header,
                row_count=len(records),
            ),
        )