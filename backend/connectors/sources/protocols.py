"""Protocol for pull-based connector sources.

A source knows how to read one page of rows and how to say where the next page
starts. It knows nothing about runs, events, or persistence — that is the
executor's job. Keeping the boundary this narrow is what lets a new source type
(object store, HTTP) be added without touching the executor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

__all__ = ["ConnectorSourceAdapter", "SourcePage"]


@dataclass(frozen=True)
class SourcePage:
    """One page of source rows plus the cursor for the next page.

    ``next_cursor is None`` means "no more pages" — it is the *only* signal
    that a sync run is finished, so a source must never return ``None`` while
    rows remain.
    """

    rows: list[dict[str, object]]
    next_cursor: str | None = None


class ConnectorSourceAdapter(Protocol):
    """Read a pull source one page at a time."""

    def read_page(
        self,
        *,
        config: Mapping[str, object],
        cursor: str | None,
        limit: int,
    ) -> SourcePage:
        """Return up to ``limit`` rows starting at ``cursor``.

        ``cursor`` is opaque to the caller: it is produced by a previous
        ``read_page`` on the same source and must not be parsed or constructed
        by the executor. Implementations raise ``ConnectorSourceError`` for a
        cursor they cannot honour rather than silently restarting from the
        beginning, which would re-ingest rows and make run counters lie.
        """
        ...
