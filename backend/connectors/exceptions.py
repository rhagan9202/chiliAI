"""Connector module exceptions."""

from __future__ import annotations

__all__ = ["ConnectorError", "ConnectorSourceError"]


class ConnectorError(Exception):
    """Base class for connector failures."""


class ConnectorSourceError(ConnectorError):
    """A connector source could not be read.

    Raised for operator-facing problems — a path outside the allowed root, a
    missing directory, an unusable cursor. The executor lets this propagate so
    ``run_handler_with_retry`` owns the retry-versus-dead-letter decision,
    rather than swallowing it and marking a run complete with no rows.
    """
