"""Connector module exceptions."""

from __future__ import annotations

__all__ = ["ConnectorError", "ConnectorSourceError", "ConnectorValidationError"]


class ConnectorError(Exception):
    """Base class for connector failures."""


class ConnectorValidationError(ConnectorError):
    """A connector definition or sync request asks for something unsupported.

    Deliberately **not** a ``ValueError`` subclass. ``ConnectorService`` already
    raises ``ValueError`` for definition conflicts, which the router maps to
    HTTP 409; inheriting from it would report an unimplemented source type as a
    conflict instead of as invalid input.
    """


class ConnectorSourceError(ConnectorError):
    """A connector source could not be read.

    Raised for operator-facing problems — a path outside the allowed root, a
    missing directory, an unusable cursor. The executor lets this propagate so
    ``run_handler_with_retry`` owns the retry-versus-dead-letter decision,
    rather than swallowing it and marking a run complete with no rows.
    """
