"""Unit tests for concrete local document parsers."""

from __future__ import annotations

import csv
from io import BytesIO

import pytest
from docx import Document
from openpyxl import Workbook

from ingestion.models import DocumentFormat, SourceDocument, SourceType
from ingestion.parsers.csv import CsvParser
from ingestion.parsers.docx import DocxParser
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.html import HtmlParser
from ingestion.parsers.json import JsonParser
from ingestion.parsers.pdf import PdfParser
from ingestion.parsers.txt import TextParser
from ingestion.parsers.xlsx import XlsxParser


def _source(document_id: str, document_format: DocumentFormat) -> SourceDocument:
    return SourceDocument(
        id=document_id,
        source_type=SourceType.FILE_UPLOAD,
        document_format=document_format,
        filename=f"sample.{document_format.value}",
    )


def test_text_parser_decodes_and_normalizes() -> None:
    parser = TextParser()
    parsed = parser.parse(_source("doc-txt", DocumentFormat.TXT), b"hello\r\nworld")

    assert parsed.text_content == "hello\nworld"
    assert parsed.parser_metadata["encoding"] == "utf-8"


def test_json_parser_creates_records_for_array_of_objects() -> None:
    parser = JsonParser()
    parsed = parser.parse(
        _source("doc-json", DocumentFormat.JSON),
        b'[{"claim_id": "1"}, {"claim_id": "2"}]',
    )

    assert len(parsed.records) == 2
    assert parsed.records[1].fields["claim_id"] == "2"


def test_json_parser_rejects_invalid_json() -> None:
    parser = JsonParser()
    with pytest.raises(ParserError, match="Invalid JSON"):
        parser.parse(_source("doc-json", DocumentFormat.JSON), b"{bad json")


def test_csv_parser_creates_structured_records() -> None:
    parser = CsvParser()
    parsed = parser.parse(
        _source("doc-csv", DocumentFormat.CSV),
        b"claim_id,amount\n1,100\n2,250\n",
    )

    assert len(parsed.records) == 2
    assert parsed.records[0].fields["claim_id"] == "1"
    assert parsed.parser_metadata["has_header"] is True


def test_csv_parser_rejects_empty_content() -> None:
    parser = CsvParser()
    with pytest.raises(ParserError, match="empty"):
        parser.parse(_source("doc-csv", DocumentFormat.CSV), b"   ")


def test_csv_parser_falls_back_when_dialect_sniffing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_sniff(
        self: object,
        sample: str,
        delimiters: str | None = None,
    ) -> csv.Dialect:
        raise csv.Error("cannot sniff")

    monkeypatch.setattr("csv.Sniffer.sniff", fail_sniff)

    parser = CsvParser()
    parsed = parser.parse(
        _source("doc-csv", DocumentFormat.CSV),
        b"claim_id,amount\n1,100\n",
    )

    assert parsed.records[0].fields["claim_id"] == "1"
    assert parsed.parser_metadata["delimiter"] == ","


def test_csv_parser_generates_column_names_without_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_header(self: object, sample: str) -> bool:
        del self, sample
        return False

    monkeypatch.setattr("csv.Sniffer.has_header", no_header)

    parser = CsvParser()
    parsed = parser.parse(
        _source("doc-csv", DocumentFormat.CSV),
        b"1,100\n2,250\n",
    )

    assert parsed.records[0].fields == {"column_1": "1", "column_2": "100"}
    assert parsed.parser_metadata["has_header"] is False


def test_csv_parser_rejects_no_rows_after_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    def empty_reader(
        csvfile: object,
        dialect: csv.Dialect | str = "excel",
        **fmtparams: object,
    ) -> list[list[str]]:
        del csvfile, dialect, fmtparams
        return []

    monkeypatch.setattr("csv.reader", empty_reader)

    parser = CsvParser()
    with pytest.raises(ParserError, match="does not contain any rows"):
        parser.parse(_source("doc-csv", DocumentFormat.CSV), b"claim_id\n1\n")


def test_csv_parser_rejects_headers_without_data_rows() -> None:
    parser = CsvParser()
    with pytest.raises(ParserError, match="headers but no data rows"):
        parser.parse(_source("doc-csv", DocumentFormat.CSV), b"claim_id,amount\n")


def test_html_parser_extracts_visible_text() -> None:
    parser = HtmlParser()
    parsed = parser.parse(
        _source("doc-html", DocumentFormat.HTML),
        b"""
        <html>
          <head><title>Ignored</title><script>alert("x")</script></head>
          <body><h1>Claim Summary</h1><p>Claim ID C-1 &amp; amount $42.</p></body>
        </html>
        """,
    )

    assert parsed.text_content == "Claim Summary\n\nClaim ID C-1 & amount $42."
    assert parsed.parser_metadata["encoding"] == "utf-8"


def test_xlsx_parser_creates_records_with_sheet_metadata() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Claims"
    sheet.append(["claim_id", "amount"])
    sheet.append(["C-1", 42])
    output = BytesIO()
    workbook.save(output)

    parser = XlsxParser()
    parsed = parser.parse(_source("doc-xlsx", DocumentFormat.XLSX), output.getvalue())

    assert len(parsed.records) == 1
    assert parsed.records[0].fields["claim_id"] == "C-1"
    assert parsed.records[0].metadata["sheet_name"] == "Claims"


def test_xlsx_parser_rejects_invalid_workbook() -> None:
    parser = XlsxParser()
    with pytest.raises(ParserError, match="Unable to read XLSX"):
        parser.parse(_source("doc-xlsx", DocumentFormat.XLSX), b"not an xlsx file")


def test_docx_parser_extracts_paragraphs_and_tables() -> None:
    document = Document()
    document.add_paragraph("Paragraph text")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "A"
    table.rows[0].cells[1].text = "B"
    output = BytesIO()
    document.save(output)

    parser = DocxParser()
    parsed = parser.parse(_source("doc-docx", DocumentFormat.DOCX), output.getvalue())

    assert "Paragraph text" in (parsed.text_content or "")
    assert "A | B" in (parsed.text_content or "")
    assert parsed.parser_metadata["table_row_count"] == 1


def test_docx_parser_rejects_invalid_docx() -> None:
    parser = DocxParser()
    with pytest.raises(ParserError, match="Unable to read DOCX"):
        parser.parse(_source("doc-docx", DocumentFormat.DOCX), b"bad docx")


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakePdfReader:
    def __init__(self, _content: BytesIO) -> None:
        self.is_encrypted = False
        self.pages = [_FakePage("First page"), _FakePage("Second page")]


def test_pdf_parser_extracts_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingestion.parsers.pdf.PdfReader", _FakePdfReader)

    parser = PdfParser()
    parsed = parser.parse(_source("doc-pdf", DocumentFormat.PDF), b"fake pdf")

    assert parsed.text_content == "First page\n\nSecond page"
    assert parsed.parser_metadata["page_count"] == 2


class _EncryptedPdfReader:
    def __init__(self, _content: BytesIO) -> None:
        self.is_encrypted = True
        self.pages = []


def test_pdf_parser_rejects_encrypted_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingestion.parsers.pdf.PdfReader", _EncryptedPdfReader)

    parser = PdfParser()
    with pytest.raises(ParserError, match="Encrypted PDF"):
        parser.parse(_source("doc-pdf", DocumentFormat.PDF), b"fake pdf")
