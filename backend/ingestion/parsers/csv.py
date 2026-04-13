"""CSV parser."""

from __future__ import annotations

import csv
from io import StringIO

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument, StructuredRecord
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.utils import build_parser_metadata, decode_text_content

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

        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            dialect = csv.excel
            has_header = True

        rows = list(csv.reader(StringIO(text), dialect=dialect))
        if not rows:
            raise ParserError("CSV content does not contain any rows.")

        if has_header:
            headers = [header.strip() or f"column_{index + 1}" for index, header in enumerate(rows[0])]
            data_rows = rows[1:]
        else:
            headers = [f"column_{index + 1}" for index in range(len(rows[0]))]
            data_rows = rows

        records = [
            StructuredRecord(
                id=f"{source.id}-row-{row_index}",
                row_number=row_index,
                fields={headers[index]: value for index, value in enumerate(row)},
            )
            for row_index, row in enumerate(data_rows)
        ]

        if not records:
            raise ParserError("CSV content contains headers but no data rows.")

        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            records=records,
            parser_name=self.name,
            parser_version=self.version,
            parser_metadata=build_parser_metadata(
                encoding=encoding,
                delimiter=getattr(dialect, "delimiter", ","),
                has_header=has_header,
                row_count=len(records),
            ),
        )