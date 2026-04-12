"""Exception types for the parser subsystem."""

from __future__ import annotations


class ParserError(Exception):
    """Base parser-layer failure."""


class UnsupportedFormatError(ParserError):
    """Raised when no parser can handle the requested format."""


class RemoteFetchError(ParserError):
    """Raised when remote document retrieval fails."""


class ContentDecodingError(ParserError):
    """Raised when bytes cannot be decoded into text."""