"""HTML parser."""

from __future__ import annotations

from html.parser import HTMLParser

from ingestion.models import DocumentFormat, ParsedDocument, SourceDocument
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.utils import build_parser_metadata, decode_text_content

__all__ = ["HtmlParser"]


class _VisibleTextParser(HTMLParser):
    """Collect visible HTML text into paragraph-like blocks."""

    _block_tags = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
    _ignored_tags = {"script", "style", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str | None] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.lower()
        if normalized in self._ignored_tags:
            self._ignored_depth += 1
            return
        if normalized in self._block_tags:
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in self._ignored_tags:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if normalized in self._block_tags:
            self._append_break()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def visible_text(self) -> str:
        paragraphs: list[str] = []
        current: list[str] = []
        for part in self._parts:
            if part is None:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                continue
            current.append(part)
        if current:
            paragraphs.append(" ".join(current))
        return "\n\n".join(paragraphs)

    def _append_break(self) -> None:
        if self._parts and self._parts[-1] is not None:
            self._parts.append(None)


class HtmlParser:
    """Parse HTML into normalized visible text."""

    name = "html"
    version = "1.0"
    supported_formats = (DocumentFormat.HTML,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        text, encoding = decode_text_content(content)
        html_parser = _VisibleTextParser()
        html_parser.feed(text)
        html_parser.close()
        visible_text = html_parser.visible_text()
        if not visible_text:
            raise ParserError("HTML content does not contain visible text.")

        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            text_content=visible_text,
            parser_name=self.name,
            parser_version=self.version,
            parser_metadata=build_parser_metadata(
                encoding=encoding,
                visible_text_length=len(visible_text),
            ),
        )
