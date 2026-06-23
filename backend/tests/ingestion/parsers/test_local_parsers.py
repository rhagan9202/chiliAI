"""Unit tests for concrete local document parsers."""

from __future__ import annotations

import csv
from io import BytesIO

import pytest
from docx import Document
from openpyxl import Workbook

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument, SourceType
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


# --- Typed parser warnings (ingestion.24) -------------------------------------


def _codes(parsed: ParsedDocument) -> set[str]:
    return {warning.code for warning in parsed.warnings}


def test_text_parser_warns_on_charset_fallback() -> None:
    parser = TextParser()
    parsed = parser.parse(_source("doc-txt", DocumentFormat.TXT), b"caf\xe9 latte")

    assert parsed.text_content == "café latte"
    assert "text.charset_fallback" in _codes(parsed)
    assert parsed.warnings[0].severity == "info"


def test_text_parser_emits_no_warnings_for_clean_utf8() -> None:
    parser = TextParser()
    parsed = parser.parse(_source("doc-txt", DocumentFormat.TXT), b"plain ascii")

    assert parsed.warnings == []


def test_html_parser_warns_on_charset_fallback() -> None:
    parser = HtmlParser()
    parsed = parser.parse(
        _source("doc-html", DocumentFormat.HTML),
        b"<html><body><p>caf\xe9</p></body></html>",
    )

    assert "html.charset_fallback" in _codes(parsed)


def test_json_parser_warns_on_heterogeneous_array() -> None:
    parser = JsonParser()
    parsed = parser.parse(
        _source("doc-json", DocumentFormat.JSON),
        b'[1, {"claim_id": "1"}]',
    )

    assert parsed.records == []
    assert "json.heterogeneous_array" in _codes(parsed)


def test_json_parser_warns_on_scalar_root() -> None:
    parser = JsonParser()
    parsed = parser.parse(_source("doc-json", DocumentFormat.JSON), b"42")

    assert "json.scalar_root" in _codes(parsed)


def test_csv_parser_warns_on_ragged_row() -> None:
    parser = CsvParser()
    parsed = parser.parse(
        _source("doc-csv", DocumentFormat.CSV),
        b"claim_id,amount\n1,100,extra\n",
    )

    ragged = [w for w in parsed.warnings if w.code == "csv.ragged_row"]
    assert len(ragged) == 1
    assert ragged[0].row_index == 0
    # Extra cell dropped; declared columns preserved.
    assert parsed.records[0].fields == {"claim_id": "1", "amount": "100"}


def test_csv_parser_warns_on_dialect_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_sniff(self: object, sample: str, delimiters: str | None = None) -> csv.Dialect:
        del self, sample, delimiters
        raise csv.Error("cannot sniff")

    monkeypatch.setattr("csv.Sniffer.sniff", fail_sniff)

    parser = CsvParser()
    parsed = parser.parse(_source("doc-csv", DocumentFormat.CSV), b"claim_id,amount\n1,100\n")

    assert "csv.dialect_fallback" in _codes(parsed)


def test_xlsx_parser_warns_on_blank_row_skipped() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Claims"
    sheet.append(["claim_id", "amount"])
    sheet.append(["C-1", 42])
    sheet.append([None, None])
    sheet.append(["C-2", 43])
    output = BytesIO()
    workbook.save(output)

    parser = XlsxParser()
    parsed = parser.parse(_source("doc-xlsx", DocumentFormat.XLSX), output.getvalue())

    assert len(parsed.records) == 2
    blank = [w for w in parsed.warnings if w.code == "xlsx.blank_row_skipped"]
    assert len(blank) == 1
    assert blank[0].row_index == 2


def test_pdf_parser_warns_on_empty_page(monkeypatch: pytest.MonkeyPatch) -> None:
    class _PartiallyEmptyReader:
        def __init__(self, _content: BytesIO) -> None:
            self.is_encrypted = False
            self.pages = [_FakePage("First page"), _FakePage("   ")]

    monkeypatch.setattr("ingestion.parsers.pdf.PdfReader", _PartiallyEmptyReader)

    parser = PdfParser()
    parsed = parser.parse(_source("doc-pdf", DocumentFormat.PDF), b"fake pdf")

    empty = [w for w in parsed.warnings if w.code == "pdf.empty_page"]
    assert len(empty) == 1
    assert empty[0].page_number == 2


def test_docx_parser_warns_on_empty_paragraphs() -> None:
    document = Document()
    document.add_paragraph("   ")
    document.add_paragraph("Real content")
    output = BytesIO()
    document.save(output)

    parser = DocxParser()
    parsed = parser.parse(_source("doc-docx", DocumentFormat.DOCX), output.getvalue())

    assert "docx.empty_paragraph_skipped" in _codes(parsed)


def test_parser_warning_round_trips_through_serialization() -> None:
    parser = PdfParser()  # any parser; reuse the empty-page warning path

    class _Reader:
        def __init__(self, _content: BytesIO) -> None:
            self.is_encrypted = False
            self.pages = [_FakePage("kept"), _FakePage("")]

    import ingestion.parsers.pdf as pdf_module

    original = pdf_module.PdfReader
    pdf_module.PdfReader = _Reader  # type: ignore[assignment]
    try:
        parsed = parser.parse(_source("doc-pdf", DocumentFormat.PDF), b"fake pdf")
    finally:
        pdf_module.PdfReader = original  # type: ignore[assignment]

    restored = ParsedDocument.model_validate_json(parsed.model_dump_json())
    assert len(restored.warnings) == 1
    assert restored.warnings[0].code == "pdf.empty_page"
    assert restored.warnings[0].page_number == 2
    assert restored.warnings[0].severity == "warning"
