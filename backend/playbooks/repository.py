"""Playbook repository boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from playbooks.models import PlaybookSnapshot, PlaybookSnapshotPage


@runtime_checkable
class PlaybookRepository(Protocol):
    """Store immutable published playbook snapshots."""

    def upsert_snapshot(self, snapshot: PlaybookSnapshot) -> PlaybookSnapshot:
        """Store a snapshot or return an identical existing natural key."""
        ...

    def get_snapshot(
        self, *, domain_name: str, playbook_id: str, version: str
    ) -> PlaybookSnapshot | None:
        """Return one snapshot by natural key, or ``None`` if absent."""
        ...

    def list_snapshots(
        self, *, domain_name: str, limit: int = 50, offset: int = 0
    ) -> PlaybookSnapshotPage:
        """Return a deterministic page of snapshots for a domain."""
        ...


__all__ = ["PlaybookRepository"]
