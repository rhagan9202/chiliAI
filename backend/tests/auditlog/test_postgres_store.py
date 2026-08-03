"""Integration tests for the durable audit-log repository."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from auditlog.adapters.postgres import PostgresAuditLogRepository
from auditlog.exceptions import AuditLogPersistenceError
from auditlog.models import AuditEvent, AuditEventQuery, AuditOutcome
from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_TENANT_ID = "tenant-audit-postgres-test"


def _event(
    event_id: str,
    *,
    occurred_at: datetime,
    knowledge_base_id: str = "kb-audit-1",
    actor_user_id: str = "analyst-1",
    action: str = "case.update",
    resource_type: str = "case",
    resource_id: str = "case-1",
    outcome: AuditOutcome = "success",
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        occurred_at=occurred_at,
        tenant_id=_TENANT_ID,
        knowledge_base_id=knowledge_base_id,
        actor_user_id=actor_user_id,
        actor_email=f"{actor_user_id}@example.test",
        actor_roles=["auditor", "analyst"],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before={"status": "open", "risk": 0.64},
        after={"status": "reviewed", "risk": 0.91},
        correlation_id=f"corr-{event_id}",
        client_ip="203.0.113.9",
        user_agent="pytest",
        outcome=outcome,
        metadata={"source": "postgres-test", "schema": 1},
    )


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping audit-log integration tests.")
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
        conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (_TENANT_ID,))
        conn.commit()
    yield connection_provider
    with connection_provider.connection() as conn:
        conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (_TENANT_ID,))
        conn.commit()
    connection_provider.close()


pytestmark = pytest.mark.integration


def test_append_and_query_roundtrip_newest_first(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresAuditLogRepository(provider)
    base_time = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
    repository.append(_event("pg-audit-1", occurred_at=base_time))
    repository.append(
        _event(
            "pg-audit-2",
            occurred_at=base_time + timedelta(minutes=1),
            action="case.feedback.create",
        )
    )
    repository.append(
        _event(
            "pg-audit-3",
            occurred_at=base_time + timedelta(minutes=2),
            knowledge_base_id="kb-audit-2",
            action="alert.acknowledge",
        )
    )

    page = repository.list(
        AuditEventQuery(
            tenant_id=_TENANT_ID,
            knowledge_base_id="kb-audit-1",
            action_prefix="case.",
            limit=10,
            offset=0,
        )
    )

    assert page.total_items == 2
    assert [event.event_id for event in page.items] == ["pg-audit-2", "pg-audit-1"]
    assert page.items[0].before == {"status": "open", "risk": 0.64}
    assert page.items[0].after == {"status": "reviewed", "risk": 0.91}
    assert page.items[0].metadata == {"source": "postgres-test", "schema": 1}
    assert page.items[0].actor_roles == ["auditor", "analyst"]


def test_query_filters_and_paginates_after_count(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresAuditLogRepository(provider)
    base_time = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)
    for index in range(3):
        repository.append(
            _event(
                f"pg-audit-page-{index}",
                occurred_at=base_time + timedelta(minutes=index),
                actor_user_id="analyst-page",
                resource_id=f"case-{index}",
            )
        )

    page = repository.list(
        AuditEventQuery(
            tenant_id=_TENANT_ID,
            actor_user_id="analyst-page",
            resource_type="case",
            outcome="success",
            limit=1,
            offset=1,
        )
    )

    assert page.total_items == 3
    assert page.limit == 1
    assert page.offset == 1
    assert [event.event_id for event in page.items] == ["pg-audit-page-1"]


def test_append_conflict_is_rejected_without_mutating_existing_row(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresAuditLogRepository(provider)
    first = _event(
        "pg-audit-conflict",
        occurred_at=datetime(2026, 8, 3, 16, 0, tzinfo=UTC),
        action="case.update",
    )
    repository.append(first)

    with pytest.raises(AuditLogPersistenceError):
        repository.append(
            _event(
                "pg-audit-conflict",
                occurred_at=datetime(2026, 8, 3, 16, 1, tzinfo=UTC),
                action="case.delete",
            )
        )

    page = repository.list(AuditEventQuery(tenant_id=_TENANT_ID, limit=10, offset=0))
    stored = [event for event in page.items if event.event_id == "pg-audit-conflict"]
    assert len(stored) == 1
    assert stored[0].action == "case.update"
