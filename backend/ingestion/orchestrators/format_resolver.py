"""Reusable format resolution helpers for parser orchestration."""

from __future__ import annotations

from urllib.parse import urlparse

from ingestion.models import DocumentFormat, SourceDocument
from ingestion.orchestrators.protocols import FormatResolver
from ingestion.parsers.exceptions import UnsupportedFormatError
from ingestion.parsers.utils import infer_format_from_content_type, infer_format_from_filename

__all__ = ["DefaultFormatResolver"]


class DefaultFormatResolver(FormatResolver):
    """Resolve format in a deterministic priority order."""

    def resolve(
        self,
        source: SourceDocument,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        uri: str | None = None,
    ) -> DocumentFormat:
        resolved = (
            source.document_format
            or infer_format_from_content_type(content_type or source.media_type)
            or infer_format_from_filename(filename or source.filename)
            or infer_format_from_filename(_uri_path(uri or source.uri))
        )
        if resolved is None:
            raise UnsupportedFormatError("Unable to resolve document format.")
        return resolved


def _uri_path(uri: str | None) -> str | None:
    if uri is None:
        return None
    return urlparse(uri).path or None