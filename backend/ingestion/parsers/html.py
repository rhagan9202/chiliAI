"""HTML parser.

Extracts visible text while preserving structural signal that downstream chunking
and extraction can use: headings keep a markdown-style ``#`` marker, anchors keep
their link target as ``[text](url)``, and tables are emitted as markdown pipe
tables (nested tables are flattened into their parent cell). See ``ingestion.02``.
"""

from __future__ import annotations

from html.parser import HTMLParser

from ingestion.models import DocumentFormat, ParsedDocument, ParserWarning, SourceDocument
from ingestion.parsers.exceptions import ParserError
from ingestion.parsers.utils import build_parser_metadata, charset_fallback_warning, decode_text_content

__all__ = ["HtmlParser"]

_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCK_TAGS = {
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
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "ul",
}
_IGNORED_TAGS = {"script", "style", "title"}


def _escape_cell(text: str) -> str:
    """Escape pipe characters so cell content cannot break the markdown table."""
    return text.replace("|", "\\|")


class _TableState:
    """Accumulates rows/cells for one ``<table>`` (one entry per nesting level)."""

    def __init__(self) -> None:
        self.rows: list[tuple[list[str], bool]] = []
        self.current_cells: list[str] | None = None
        self.current_row_is_header: bool = False
        self.current_cell: list[str] | None = None

    def start_row(self) -> None:
        self.current_cells = []
        self.current_row_is_header = False

    def start_cell(self, *, header: bool) -> None:
        self.current_cell = []
        if header:
            self.current_row_is_header = True

    def add_text(self, text: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(text)

    def end_cell(self) -> None:
        if self.current_cell is None:
            return
        if self.current_cells is None:
            self.current_cells = []
        self.current_cells.append(" ".join(self.current_cell).strip())
        self.current_cell = None

    def end_row(self) -> None:
        if self.current_cells is None:
            return
        self.rows.append((self.current_cells, self.current_row_is_header))
        self.current_cells = None
        self.current_row_is_header = False

    def _column_count(self) -> int:
        return max((len(cells) for cells, _ in self.rows), default=0)

    def render_markdown(self) -> str:
        """Render the accumulated rows as a markdown pipe table."""
        if not self.rows:
            return ""
        columns = self._column_count()
        if columns == 0:
            return ""
        header_index = next(
            (index for index, (_, is_header) in enumerate(self.rows) if is_header),
            0,
        )

        def render_row(cells: list[str]) -> str:
            padded = [_escape_cell(cell) for cell in cells] + [""] * (columns - len(cells))
            return "| " + " | ".join(padded) + " |"

        lines = [
            render_row(self.rows[header_index][0]),
            "| " + " | ".join(["---"] * columns) + " |",
        ]
        lines.extend(
            render_row(cells)
            for index, (cells, _) in enumerate(self.rows)
            if index != header_index
        )
        return "\n".join(lines)

    def flatten_text(self) -> str:
        """Flatten all cells to space-joined text (used when nested inside a cell)."""
        return " ".join(cell for cells, _ in self.rows for cell in cells if cell)


class _StructuredHtmlParser(HTMLParser):
    """Collect HTML into markdown-flavored text blocks preserving structure."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocks: list[str] = []
        self._current: list[str] = []
        self._ignored_depth = 0
        self._heading_level: int | None = None
        self._anchor_href: str | None = None
        self._anchor_text: list[str] | None = None
        self._table_stack: list[_TableState] = []
        self.heading_count = 0
        self.link_count = 0
        self.table_count = 0

    # --- text routing ---------------------------------------------------------
    def _route_text(self, text: str) -> None:
        if self._anchor_text is not None:
            self._anchor_text.append(text)
        elif self._table_stack and self._table_stack[-1].current_cell is not None:
            self._table_stack[-1].add_text(text)
        else:
            self._current.append(text)

    def _route_inline(self, token: str) -> None:
        """Route a finished inline token (e.g. a link) — never into an open anchor."""
        if self._table_stack and self._table_stack[-1].current_cell is not None:
            self._table_stack[-1].add_text(token)
        else:
            self._current.append(token)

    def _flush_block(self) -> None:
        if self._current:
            text = " ".join(self._current).strip()
            if text:
                self._blocks.append(text)
            self._current = []

    # --- HTMLParser hooks -----------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth > 0:
            return
        if normalized in _HEADING_LEVELS:
            self._flush_block()
            self._heading_level = _HEADING_LEVELS[normalized]
            self.heading_count += 1
            return
        if normalized == "a":
            self._anchor_href = next((value for key, value in attrs if key.lower() == "href"), None)
            self._anchor_text = []
            return
        if normalized == "table":
            self._flush_block()
            self._table_stack.append(_TableState())
            self.table_count += 1
            return
        if self._table_stack:
            top = self._table_stack[-1]
            if normalized == "tr":
                top.start_row()
                return
            if normalized in ("td", "th"):
                top.start_cell(header=normalized == "th")
                return
        if normalized in _BLOCK_TAGS:
            self._flush_block()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in _IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth > 0:
            return
        if normalized in _HEADING_LEVELS:
            level = self._heading_level or _HEADING_LEVELS[normalized]
            text = " ".join(self._current).strip()
            if text:
                self._blocks.append("#" * level + " " + text)
            self._current = []
            self._heading_level = None
            return
        if normalized == "a":
            text = " ".join(self._anchor_text or []).strip()
            href = self._anchor_href
            self._anchor_text = None
            self._anchor_href = None
            if text and href:
                self.link_count += 1
                self._route_inline(f"[{text}]({href})")
            elif text:
                self._route_inline(text)
            return
        if normalized == "table":
            if self._table_stack:
                state = self._table_stack.pop()
                state.end_cell()
                state.end_row()
                if self._table_stack:
                    flattened = state.flatten_text()
                    if flattened:
                        self._route_inline(flattened)
                else:
                    markdown = state.render_markdown()
                    if markdown:
                        self._blocks.append(markdown)
            return
        if self._table_stack:
            top = self._table_stack[-1]
            if normalized in ("td", "th"):
                top.end_cell()
                return
            if normalized == "tr":
                top.end_row()
                return
        if normalized in _BLOCK_TAGS:
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        text = " ".join(data.split())
        if text:
            self._route_text(text)

    def text(self) -> str:
        self._flush_block()
        return "\n\n".join(block for block in self._blocks if block)


class HtmlParser:
    """Parse HTML into normalized text preserving headings, links, and tables."""

    name = "html"
    version = "2.0"
    supported_formats = (DocumentFormat.HTML,)

    def parse(self, source: SourceDocument, content: bytes) -> ParsedDocument:
        text, encoding = decode_text_content(content)
        html_parser = _StructuredHtmlParser()
        html_parser.feed(text)
        html_parser.close()
        rendered_text = html_parser.text()
        if not rendered_text:
            raise ParserError("HTML content does not contain visible text.")

        warnings: list[ParserWarning] = []
        charset = charset_fallback_warning("html", encoding)
        if charset is not None:
            warnings.append(charset)

        return ParsedDocument(
            id=f"parsed-{source.id}",
            source_document_id=source.id,
            text_content=rendered_text,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            parser_metadata=build_parser_metadata(
                encoding=encoding,
                visible_text_length=len(rendered_text),
                heading_count=html_parser.heading_count,
                link_count=html_parser.link_count,
                table_count=html_parser.table_count,
            ),
        )
