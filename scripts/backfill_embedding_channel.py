"""Stamp `embedding_channel` on vectors indexed before the write site set it.

Record-derived vectors were indexed without `embedding_channel`, and
`ServiceContextRetriever` filters every RAG search on it — so those vectors were
present, correct, and unreachable. `agent/coordinator.py` now stamps them at
index time; this backfills what is already in the store, because a forward-only
fix leaves every existing knowledge base silently empty to RAG.

Qdrant only. The in-memory store is process-lifetime, so there is nothing to
backfill there.

    python scripts/backfill_embedding_channel.py --dry-run
    python scripts/backfill_embedding_channel.py

Idempotent: points that already carry the key are skipped, so re-running is
safe and a partial run can simply be repeated. Scoped to `source_kind=record`
by default — document vectors have always been stamped, and touching them would
widen the blast radius for no gain.

**The key must land under `metadata`, not at the payload root.** The Qdrant
adapter builds every filter as `metadata.{key}` (`_field_condition_for_filter`),
so a root-level `embedding_channel` is invisible to search — the first run of
this script stamped 1,995 points at the root and changed nothing. Qdrant's
`set_payload` takes a `key` parameter for exactly this, merging into the nested
object rather than replacing it.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import cast

import httpx

__all__ = ["BackfillSummary", "backfill_collection", "list_collections", "main"]

_DEFAULT_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
_CHANNEL_KEY = "embedding_channel"
_CHANNEL_TEXT = "text"
_SOURCE_KIND_KEY = "source_kind"
_SOURCE_KIND_RECORD = "record"
_PAGE = 256


@dataclass(frozen=True)
class BackfillSummary:
    """What one collection needed and what was done to it."""

    collection: str
    scanned: int
    missing_channel: int
    updated: int


def list_collections(client: httpx.Client, base_url: str) -> list[str]:
    response = client.get(f"{base_url}/collections")
    response.raise_for_status()
    payload = cast("dict[str, object]", response.json())
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    entries = cast("dict[str, object]", result).get("collections")
    if not isinstance(entries, list):
        return []
    names: list[str] = []
    for entry in cast("list[object]", entries):
        if isinstance(entry, dict):
            name = cast("dict[str, object]", entry).get("name")
            if isinstance(name, str):
                names.append(name)
    return sorted(names)


def backfill_collection(
    client: httpx.Client, base_url: str, collection: str, *, dry_run: bool
) -> BackfillSummary:
    """Scan one collection and stamp record points that lack the channel."""

    scanned = 0
    needing: list[object] = []
    offset: object = None

    while True:
        body: dict[str, object] = {"limit": _PAGE, "with_payload": True}
        if offset is not None:
            body["offset"] = offset
        response = client.post(f"{base_url}/collections/{collection}/points/scroll", json=body)
        response.raise_for_status()
        result = cast("dict[str, object]", response.json()).get("result")
        if not isinstance(result, dict):
            break
        page = cast("dict[str, object]", result)
        points = page.get("points")
        if not isinstance(points, list):
            break
        for point in cast("list[object]", points):
            if not isinstance(point, dict):
                continue
            entry = cast("dict[str, object]", point)
            payload = entry.get("payload")
            payload_map = (
                cast("dict[str, object]", payload) if isinstance(payload, dict) else {}
            )
            scanned += 1
            metadata = payload_map.get("metadata")
            metadata_map = (
                cast("dict[str, object]", metadata) if isinstance(metadata, dict) else {}
            )
            # Only the nested copy counts — a root-level key is not what search
            # reads, so a point carrying only that one still needs stamping.
            already = _CHANNEL_KEY in metadata_map
            is_record = (
                payload_map.get(_SOURCE_KIND_KEY) == _SOURCE_KIND_RECORD
                or metadata_map.get(_SOURCE_KIND_KEY) == _SOURCE_KIND_RECORD
            )
            if not already and is_record:
                needing.append(entry.get("id"))
        offset = page.get("next_page_offset")
        if offset is None:
            break

    if needing and not dry_run:
        response = client.post(
            f"{base_url}/collections/{collection}/points/payload",
            json={
                "payload": {_CHANNEL_KEY: _CHANNEL_TEXT},
                "points": needing,
                "key": "metadata",
            },
            params={"wait": "true"},
        )
        response.raise_for_status()
        # Remove the root-level copy this script wrote before the nesting was
        # understood. Harmless but misleading: it makes a point look stamped.
        cleanup = client.post(
            f"{base_url}/collections/{collection}/points/payload/delete",
            json={"keys": [_CHANNEL_KEY], "points": needing},
            params={"wait": "true"},
        )
        cleanup.raise_for_status()

    return BackfillSummary(
        collection=collection,
        scanned=scanned,
        missing_channel=len(needing),
        updated=0 if dry_run else len(needing),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=_DEFAULT_QDRANT_URL)
    parser.add_argument("--collection", action="append", dest="collections")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    base_url: str = str(args.qdrant_url).rstrip("/")
    dry_run: bool = bool(args.dry_run)

    with httpx.Client(timeout=60.0) as client:
        selected: list[str] = args.collections or list_collections(client, base_url)
        if not selected:
            print("No collections found; nothing to do.")
            return 0

        total_missing = 0
        for name in selected:
            summary = backfill_collection(client, base_url, name, dry_run=dry_run)
            total_missing += summary.missing_channel
            if summary.missing_channel:
                verb = "would stamp" if dry_run else "stamped"
                print(
                    f"{summary.collection}: {verb} {summary.missing_channel} "
                    f"of {summary.scanned} points"
                )

    if total_missing == 0:
        print("Every record vector already carries the text channel.")
    elif dry_run:
        print(f"\nDry run: {total_missing} points need stamping. Re-run without --dry-run.")
    else:
        print(f"\nStamped {total_missing} points.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
