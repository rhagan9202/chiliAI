"""Integration test: migration 0020's downgrade on a populated database.

``0020_playbook_snapshot_kb_scope`` widened ``fraud_playbook_snapshots``
uniqueness to include ``knowledge_base_id``, so an upgraded database can
legitimately hold one snapshot row per knowledge base for the same
``(domain_name, playbook_id, version)``. Its ``downgrade()`` re-adds
``PRIMARY KEY (domain_name, playbook_id, version)`` -- a key the pre-0020
schema has no column to disambiguate those rows under -- before dropping
``knowledge_base_id``.

``tests/database/test_migrations.py`` only ever downgrades a freshly
migrated EMPTY database, so this was never exercised against real data.

Design decision: the downgrade fails loudly instead of silently deleting the
extra rows. Playbook snapshots are the ``playbooks`` module's immutable
published history (see ``docs/architecture.md`` module map); a downgrade that
quietly discards some of them to make an ``ADD CONSTRAINT`` succeed is a data
-loss hazard the operator never asked for and may not notice (alembic's exit
code alone would look identical to a clean downgrade). Failing with a clear,
actionable error keeps the operator in control: they inspect the duplicates
and decide how to resolve them (export, reassign, or explicitly delete)
before retrying.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DOMAIN = "task12_migration_0020_downgrade"


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_snapshot(
    provider: ConnectionProvider,
    *,
    knowledge_base_id: str,
    playbook_id: str,
    version: str,
) -> None:
    now = datetime.now(timezone.utc)
    with provider.connection() as conn:
        conn.execute(
            """
            INSERT INTO fraud_playbook_snapshots (
                knowledge_base_id, domain_name, playbook_id, version, status,
                definition, source, published_by, published_at, created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                knowledge_base_id,
                _DOMAIN,
                playbook_id,
                version,
                "published",
                json.dumps({"steps": []}),
                "domain_config",
                "task-12-test",
                now,
                now,
                now,
            ),
        )
        conn.commit()


def test_downgrade_fails_loudly_on_snapshots_from_two_knowledge_bases(
    database_url: str,
) -> None:
    """The downgrade must refuse to run rather than silently drop rows.

    Seeds two knowledge bases' snapshots sharing a
    (domain_name, playbook_id, version), then downgrades to 0019. The
    unmodified migration fails with Postgres's raw
    ``could not create unique index`` error from the bare ``ADD CONSTRAINT``.
    After the fix, it must instead fail with a clear, actionable message
    identifying the duplicate-owning migration and telling the operator how
    to resolve it -- and must not have deleted either row.
    """

    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    try:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM fraud_playbook_snapshots WHERE domain_name = %s",
                (_DOMAIN,),
            )
            conn.commit()

        _seed_snapshot(
            provider, knowledge_base_id="kb-a", playbook_id="p1", version="1"
        )
        _seed_snapshot(
            provider, knowledge_base_id="kb-b", playbook_id="p1", version="1"
        )

        try:
            downgrade = _run_alembic(database_url, "downgrade", "0019_fraud_playbooks")

            assert downgrade.returncode != 0, (
                "downgrade must refuse to run on populated duplicate rows, "
                f"but it exited 0. stdout={downgrade.stdout!r}"
            )
            assert "cannot downgrade fraud_playbook_snapshots" in (
                downgrade.stderr.lower()
            ), (
                "expected the migration's own actionable guard message, not "
                f"a bare constraint-violation error. stderr={downgrade.stderr!r}"
            )

            with provider.connection() as conn:
                remaining = conn.execute(
                    "SELECT count(*) FROM fraud_playbook_snapshots "
                    "WHERE domain_name = %s",
                    (_DOMAIN,),
                ).fetchone()
            assert remaining is not None
            assert int(cast(int, remaining[0])) == 2, (
                "the guard must reject the downgrade without deleting either "
                "knowledge base's row"
            )
        finally:
            restore = _run_alembic(database_url, "upgrade", "head")
            assert restore.returncode == 0, restore.stderr
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM fraud_playbook_snapshots WHERE domain_name = %s",
                (_DOMAIN,),
            )
            conn.commit()
        provider.close()
