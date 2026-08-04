"""Integration tests for SAFE-CMS-013 Postgres playbook snapshots."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.schema import DatabaseConfig, FraudPlaybookConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from playbooks.adapters.postgres import PostgresPlaybookRepository
from playbooks.models import PlaybookSnapshot

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DOMAIN = "safe_cms_013_pg"

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping playbook integration tests.")
    return url


@pytest.fixture
def provider(database_url: str) -> Iterator[ConnectionProvider]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    connection_provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert connection_provider is not None
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM fraud_playbook_snapshots WHERE domain_name LIKE %s",
            (_DOMAIN + "%",),
        )
        conn.commit()
    yield connection_provider
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM fraud_playbook_snapshots WHERE domain_name LIKE %s",
            (_DOMAIN + "%",),
        )
        conn.commit()
    connection_provider.close()


def _snapshot(
    *,
    domain_name: str = _DOMAIN,
    playbook_id: str = "provider_billing_spike_review",
    version: str = "v1",
    title: str | None = None,
) -> PlaybookSnapshot:
    published_at = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    return PlaybookSnapshot(
        snapshot_id=f"{domain_name}:{playbook_id}:{version}",
        domain_name=domain_name,
        playbook_id=playbook_id,
        version=version,
        status="published",
        definition=FraudPlaybookConfig(
            id=playbook_id,
            version=version,
            title=title or f"{playbook_id} title",
            status="published",
        ),
        source="domain_config",
        published_by="admin-1",
        published_at=published_at,
        created_at=published_at,
        updated_at=published_at,
    )


def test_postgres_playbook_repository_round_trips_snapshot(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresPlaybookRepository(provider)
    snapshot = _snapshot()

    stored = repository.upsert_snapshot(snapshot)
    found = repository.get_snapshot(
        domain_name=snapshot.domain_name,
        playbook_id=snapshot.playbook_id,
        version=snapshot.version,
    )

    assert found is not None
    assert stored == found
    assert found.snapshot_id == "safe_cms_013_pg:provider_billing_spike_review:v1"
    assert found.definition.title == "provider_billing_spike_review title"


def test_postgres_playbook_repository_lists_by_domain_and_sorts_by_key(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresPlaybookRepository(provider)
    repository.upsert_snapshot(
        _snapshot(playbook_id="identity_mismatch_review", version="v2")
    )
    repository.upsert_snapshot(
        _snapshot(playbook_id="provider_billing_spike_review", version="v1")
    )
    repository.upsert_snapshot(
        _snapshot(
            domain_name=_DOMAIN + "_other",
            playbook_id="housing_outlier_review",
            version="v1",
        )
    )
    repository.upsert_snapshot(
        _snapshot(playbook_id="identity_mismatch_review", version="v1")
    )

    page = repository.list_snapshots(domain_name=_DOMAIN, limit=2, offset=1)

    assert page.total == 3
    assert [(item.playbook_id, item.version) for item in page.items] == [
        ("identity_mismatch_review", "v2"),
        ("provider_billing_spike_review", "v1"),
    ]


def test_postgres_playbook_repository_rejects_conflicting_definition(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresPlaybookRepository(provider)
    repository.upsert_snapshot(_snapshot())

    conflicting = _snapshot(title="Different title")

    with pytest.raises(ValueError, match="already exists with different definition"):
        repository.upsert_snapshot(conflicting)

    stored = repository.get_snapshot(
        domain_name=_DOMAIN,
        playbook_id="provider_billing_spike_review",
        version="v1",
    )
    assert stored is not None
    assert stored.definition.title == "provider_billing_spike_review title"
