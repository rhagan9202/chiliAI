"""Postgres-backed playbook snapshot repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from config.schema import FraudPlaybookConfig
from database.protocols import ConnectionProvider, Row
from playbooks.models import (
    PlaybookSnapshot,
    PlaybookSnapshotPage,
    PlaybookSnapshotSource,
    PlaybookStatus,
)

__all__ = ["PostgresPlaybookRepository"]

_COLUMNS = (
    "knowledge_base_id, domain_name, playbook_id, version, status, definition, "
    "source, published_by, published_at, created_at, updated_at"
)

_INSERT_DO_NOTHING = f"""
    INSERT INTO fraud_playbook_snapshots (
        {_COLUMNS}
    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
    ON CONFLICT (knowledge_base_id, domain_name, playbook_id, version) DO NOTHING
"""

_SELECT_BY_KEY = f"""
    SELECT {_COLUMNS}
    FROM fraud_playbook_snapshots
    WHERE knowledge_base_id = %s AND domain_name = %s AND playbook_id = %s
      AND version = %s
"""


class PostgresPlaybookRepository:
    """Store immutable playbook snapshots in ``fraud_playbook_snapshots``."""

    def __init__(self, provider: ConnectionProvider) -> None:
        self._provider = provider

    def upsert_snapshot(self, snapshot: PlaybookSnapshot) -> PlaybookSnapshot:
        """Store a new snapshot or return an identical existing natural key."""
        with self._provider.connection() as conn:
            conn.execute(_INSERT_DO_NOTHING, _insert_params(snapshot))
            row = conn.execute(
                _SELECT_BY_KEY,
                (
                    snapshot.knowledge_base_id,
                    snapshot.domain_name,
                    snapshot.playbook_id,
                    snapshot.version,
                ),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise ValueError(
                    f"Playbook snapshot '{snapshot.snapshot_id}' was not stored."
                )
            stored = _row_to_snapshot(row)
            if _normalized_definition(stored.definition) != _normalized_definition(
                snapshot.definition
            ):
                conn.rollback()
                raise ValueError(
                    f"Playbook snapshot '{snapshot.snapshot_id}' already exists "
                    "with different definition."
                )
            conn.commit()
            return stored

    def get_snapshot(
        self,
        *,
        knowledge_base_id: str,
        domain_name: str,
        playbook_id: str,
        version: str,
    ) -> PlaybookSnapshot | None:
        with self._provider.connection() as conn:
            row = conn.execute(
                _SELECT_BY_KEY,
                (knowledge_base_id, domain_name, playbook_id, version),
            ).fetchone()
        return None if row is None else _row_to_snapshot(row)

    def list_snapshots(
        self,
        *,
        knowledge_base_id: str,
        domain_name: str,
        limit: int = 50,
        offset: int = 0,
    ) -> PlaybookSnapshotPage:
        with self._provider.connection() as conn:
            total_row = conn.execute(
                """
                SELECT count(*)
                FROM fraud_playbook_snapshots
                WHERE knowledge_base_id = %s AND domain_name = %s
                """,
                (knowledge_base_id, domain_name),
            ).fetchone()
            total = cast(int, total_row[0]) if total_row is not None else 0
            if limit <= 0 or offset < 0:
                rows: list[Row] = []
            else:
                rows = conn.execute(
                    f"""
                    SELECT {_COLUMNS}
                    FROM fraud_playbook_snapshots
                    WHERE knowledge_base_id = %s AND domain_name = %s
                    ORDER BY playbook_id ASC, version ASC
                    LIMIT %s OFFSET %s
                    """,
                    (knowledge_base_id, domain_name, limit, offset),
                ).fetchall()
        return PlaybookSnapshotPage(
            items=[_row_to_snapshot(row) for row in rows],
            total=total,
            limit=max(limit, 1),
            offset=max(offset, 0),
        )


def _insert_params(snapshot: PlaybookSnapshot) -> tuple[object, ...]:
    return (
        snapshot.knowledge_base_id,
        snapshot.domain_name,
        snapshot.playbook_id,
        snapshot.version,
        snapshot.status,
        json.dumps(snapshot.definition.model_dump(mode="json")),
        snapshot.source,
        snapshot.published_by,
        snapshot.published_at,
        snapshot.created_at,
        snapshot.updated_at,
    )


def _row_to_snapshot(row: Row) -> PlaybookSnapshot:
    knowledge_base_id = cast(str, row[0])
    domain_name = cast(str, row[1])
    playbook_id = cast(str, row[2])
    version = cast(str, row[3])
    return PlaybookSnapshot(
        snapshot_id=f"{knowledge_base_id}:{domain_name}:{playbook_id}:{version}",
        knowledge_base_id=knowledge_base_id,
        domain_name=domain_name,
        playbook_id=playbook_id,
        version=version,
        status=cast(PlaybookStatus, row[4]),
        definition=_decode_definition(row[5]),
        source=cast(PlaybookSnapshotSource, row[6]),
        published_by=cast(str, row[7]),
        published_at=cast(datetime, row[8]),
        created_at=cast(datetime, row[9]),
        updated_at=cast(datetime, row[10]),
    )


def _decode_definition(value: object) -> FraudPlaybookConfig:
    raw = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    return FraudPlaybookConfig.model_validate(raw)


def _normalized_definition(definition: FraudPlaybookConfig) -> dict[str, object]:
    return cast(
        dict[str, object],
        FraudPlaybookConfig.model_validate(
            definition.model_dump(mode="json")
        ).model_dump(mode="json"),
    )
