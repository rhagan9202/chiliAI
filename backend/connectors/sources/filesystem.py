"""Filesystem connector source.

Reads CSV files under an operator-configured directory, one page at a time,
resuming from an opaque ``"<filename>:<row_offset>"`` cursor.

The path in a connector's config is operator-supplied, so every read is
confined to an ``allowed_root`` that must be given at construction. There is
deliberately no default: an adapter that reads the whole filesystem unless
someone remembers to bound it is one forgotten config away from serving
``/etc`` to an ingestion pipeline.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from connectors.exceptions import ConnectorSourceError
from connectors.sources.protocols import SourcePage

__all__ = ["FilesystemSourceAdapter"]

_SUFFIX = ".csv"


class FilesystemSourceAdapter:
    """Page CSV rows out of a directory tree, bounded by ``allowed_root``."""

    def __init__(self, *, allowed_root: Path) -> None:
        # Resolve the root too, not just the requested path: on hosts where the
        # import directory is itself a symlink (macOS /tmp, container mounts),
        # comparing a resolved path against an unresolved root rejects every
        # legitimate read.
        self._allowed_root = Path(allowed_root).resolve()

    def read_page(
        self,
        *,
        config: Mapping[str, object],
        cursor: str | None,
        limit: int,
    ) -> SourcePage:
        if limit <= 0:
            raise ConnectorSourceError("limit must be greater than 0.")
        target = self._resolve_target(config)
        files = _csv_files(target)
        start_index, start_offset = self._start_position(files, cursor)

        rows: list[dict[str, object]] = []
        for index in range(start_index, len(files)):
            offset = start_offset if index == start_index else 0
            file_rows = _read_rows(files[index])
            for row_number in range(offset, len(file_rows)):
                if len(rows) == limit:
                    return SourcePage(
                        rows=rows,
                        next_cursor=_encode_cursor(files[index], row_number),
                    )
                rows.append(file_rows[row_number])
        return SourcePage(rows=rows, next_cursor=None)

    # --- internals ----------------------------------------------------------

    def _resolve_target(self, config: Mapping[str, object]) -> Path:
        raw = config.get("path")
        if not isinstance(raw, str) or not raw.strip():
            raise ConnectorSourceError(
                "Connector config must set a non-empty 'path'."
            )
        # resolve() collapses '..' and follows symlinks, so the guard below sees
        # the real destination. Checking the literal string would accept both a
        # traversal path and a link that points outside the root.
        resolved = Path(raw).resolve()
        if not resolved.is_relative_to(self._allowed_root):
            raise ConnectorSourceError(
                f"Connector path '{raw}' resolves outside the allowed root."
            )
        if not resolved.exists():
            raise ConnectorSourceError(f"Connector path '{raw}' does not exist.")
        return resolved

    def _start_position(self, files: list[Path], cursor: str | None) -> tuple[int, int]:
        if cursor is None:
            return 0, 0
        name, offset = _decode_cursor(cursor)
        for index, path in enumerate(files):
            if path.name == name:
                return index, offset
        # Restarting at row 0 of whatever file sorts first would re-ingest data
        # already pulled and make the run counters describe a pull that never
        # happened. Fail loudly instead.
        raise ConnectorSourceError(
            f"Connector cursor names file '{name}', which is no longer present."
        )


def _csv_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    # Sorted, not directory order: a cursor is only resumable if the file
    # sequence is deterministic across calls and across hosts.
    return sorted(
        (path for path in target.iterdir() if path.is_file() and path.suffix == _SUFFIX),
        key=lambda path: path.name,
    )


def _read_rows(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: value for key, value in row.items() if key is not None}
            for row in csv.DictReader(handle)
        ]


def _encode_cursor(path: Path, row_offset: int) -> str:
    return f"{path.name}:{row_offset}"


def _decode_cursor(cursor: str) -> tuple[str, int]:
    # rsplit, not split: a filename may legitimately contain ':'.
    name, separator, raw_offset = cursor.rpartition(":")
    if not separator or not name:
        raise ConnectorSourceError(f"Malformed connector cursor '{cursor}'.")
    try:
        offset = int(raw_offset)
    except ValueError as exc:
        raise ConnectorSourceError(f"Malformed connector cursor '{cursor}'.") from exc
    if offset < 0:
        raise ConnectorSourceError(f"Malformed connector cursor '{cursor}'.")
    return name, offset
