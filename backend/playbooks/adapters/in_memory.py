"""In-memory playbook repository."""

from __future__ import annotations

from playbooks.models import PlaybookSnapshot, PlaybookSnapshotPage

__all__ = ["InMemoryPlaybookRepository"]


class InMemoryPlaybookRepository:
    """Dict-backed playbook snapshot repository for tests and local development."""

    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str, str, str], PlaybookSnapshot] = {}

    def upsert_snapshot(self, snapshot: PlaybookSnapshot) -> PlaybookSnapshot:
        key = (
            snapshot.knowledge_base_id,
            snapshot.domain_name,
            snapshot.playbook_id,
            snapshot.version,
        )
        existing = self._snapshots.get(key)
        if existing is not None:
            if existing.definition.model_dump(mode="json") != snapshot.definition.model_dump(
                mode="json"
            ):
                raise ValueError(
                    f"Playbook snapshot '{snapshot.snapshot_id}' already exists "
                    "with different definition."
                )
            return existing.model_copy(deep=True)
        stored = snapshot.model_copy(deep=True)
        self._snapshots[key] = stored
        return stored.model_copy(deep=True)

    def get_snapshot(
        self,
        *,
        knowledge_base_id: str,
        domain_name: str,
        playbook_id: str,
        version: str,
    ) -> PlaybookSnapshot | None:
        snapshot = self._snapshots.get(
            (knowledge_base_id, domain_name, playbook_id, version)
        )
        return snapshot.model_copy(deep=True) if snapshot is not None else None

    def list_snapshots(
        self,
        *,
        knowledge_base_id: str,
        domain_name: str,
        limit: int = 50,
        offset: int = 0,
    ) -> PlaybookSnapshotPage:
        matches = [
            snapshot.model_copy(deep=True)
            for snapshot in self._snapshots.values()
            if snapshot.knowledge_base_id == knowledge_base_id
            and snapshot.domain_name == domain_name
        ]
        matches.sort(key=lambda item: (item.playbook_id, item.version))
        if limit <= 0 or offset < 0:
            items: list[PlaybookSnapshot] = []
        else:
            items = matches[offset : offset + limit]
        return PlaybookSnapshotPage(
            items=items,
            total=len(matches),
            limit=max(limit, 1),
            offset=max(offset, 0),
        )
