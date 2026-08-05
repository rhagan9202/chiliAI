"""Integration tests for SAFE-CMS-014 Postgres workflow definitions."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from workflow_definitions.adapters.postgres import PostgresWorkflowDefinitionRepository
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    WorkflowStepDefinition,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_KB_ID = "kb-safe-cms-014-pg"

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set; skipping workflow definition integration tests."
        )
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
            "DELETE FROM workflow_definition_snapshots WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    yield connection_provider
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM workflow_definition_snapshots WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    connection_provider.close()


def _definition(
    definition_id: str = "provider-review",
    version: str = "v1",
    *,
    knowledge_base_id: str = _KB_ID,
    name: str | None = None,
    status: str = "draft",
) -> WorkflowDefinition:
    created_at = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    return WorkflowDefinition(
        definition_id=definition_id,
        knowledge_base_id=knowledge_base_id,
        domain_name="medicare_fraud",
        name=name or "Provider review",
        version=version,
        status=cast(WorkflowDefinitionStatus, status),
        allowed_capability_refs=["rag.query", "analytics.peer_context"],
        steps=[
            WorkflowStepDefinition(
                step_id="ask-rag",
                label="Ask RAG",
                capability_ref="rag.query",
            ),
            WorkflowStepDefinition(
                step_id="peer-context",
                label="Peer context",
                capability_ref="analytics.peer_context",
                input_refs=["alert.provider_npi"],
                output_refs=["peer_context"],
            ),
        ],
        created_by="analyst-1",
        approved_by="admin-1" if status == "approved" else None,
        created_at=created_at,
        updated_at=created_at,
        approved_at=created_at if status == "approved" else None,
    )


def test_postgres_workflow_definition_repository_round_trips_definition(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)
    definition = _definition()

    stored = repository.save_definition(definition)
    found = repository.get_definition(_KB_ID, "provider-review", "v1")

    assert found is not None
    assert stored == found
    assert found.snapshot_id == "kb-safe-cms-014-pg:provider-review:v1"
    assert [step.step_id for step in found.steps] == ["ask-rag", "peer-context"]
    assert found.steps[1].input_refs == ["alert.provider_npi"]


def test_postgres_workflow_definition_repository_lists_by_kb_and_sorts_by_key(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)
    repository.save_definition(_definition("definition-b", "v2"))
    repository.save_definition(_definition("definition-a", "v2"))
    repository.save_definition(_definition("definition-a", "v1"))
    repository.save_definition(
        _definition(
            "definition-c",
            "v1",
            knowledge_base_id=_KB_ID + "-other",
        )
    )

    page = repository.list_definitions(knowledge_base_id=_KB_ID, limit=2, offset=1)

    assert page.total_items == 3
    assert [(item.definition_id, item.version) for item in page.items] == [
        ("definition-a", "v2"),
        ("definition-b", "v2"),
    ]


def test_postgres_workflow_definition_repository_updates_existing_snapshot(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)
    repository.save_definition(_definition(name="Original"))

    replacement = _definition(name="Replacement", status="approved")
    updated = repository.update_definition(replacement)

    found = repository.get_definition(_KB_ID, "provider-review", "v1")
    assert found is not None
    assert updated == found
    assert found.name == "Replacement"
    assert found.status == "approved"
    assert found.approved_by == "admin-1"


def test_postgres_workflow_definition_repository_rejects_duplicate_snapshot(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)
    repository.save_definition(_definition())

    with pytest.raises(ValueError, match="already exists"):
        repository.save_definition(_definition())


def test_postgres_workflow_definition_repository_update_missing_raises(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresWorkflowDefinitionRepository(provider)

    with pytest.raises(KeyError):
        repository.update_definition(_definition("missing", "v1"))
