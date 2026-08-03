"""Integration tests for SAFE-CMS-012 Postgres identity link persistence."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analytics.identity_resolution import (
    IdentityLinkRepositoryQuery,
)
from analytics.identity_resolution.adapters.postgres import (
    PostgresIdentityLinkRepository,
)
from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from tests.analytics.test_identity_resolution_repository import _link

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_KB_ID = "kb-identity-link-pg"

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping identity-link integration tests.")
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
            "DELETE FROM identity_links WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    yield connection_provider
    with connection_provider.connection() as conn:
        conn.execute(
            "DELETE FROM identity_links WHERE knowledge_base_id LIKE %s",
            (_KB_ID + "%",),
        )
        conn.commit()
    connection_provider.close()


def test_postgres_identity_link_repository_upserts_and_lists_by_kb(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresIdentityLinkRepository(provider)
    first = _link("identity_link:kb-identity-link-pg:canonical-1:source-1").model_copy(
        update={
            "knowledge_base_id": _KB_ID,
            "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
        deep=True,
    )
    second = _link("identity_link:kb-identity-link-pg:canonical-1:source-2").model_copy(
        update={
            "knowledge_base_id": _KB_ID,
            "source_entity_id": "source:2",
            "updated_at": datetime(2026, 1, 3, tzinfo=timezone.utc),
        },
        deep=True,
    )
    hidden = _link("identity_link:kb-identity-link-pg-other:canonical-1:source-1").model_copy(
        update={"knowledge_base_id": _KB_ID + "-other"},
        deep=True,
    )

    repository.upsert_link(first)
    repository.upsert_link(second)
    repository.upsert_link(hidden)

    stored = repository.get_link(knowledge_base_id=_KB_ID, link_id=first.id)
    page = repository.list_links(
        IdentityLinkRepositoryQuery(
            knowledge_base_id=_KB_ID,
            canonical_entity_id="canonical:1",
            limit=10,
            offset=0,
        )
    )

    assert stored is not None
    assert stored.match_reasons == first.match_reasons
    assert stored.source_refs == ["source-system:a"]
    assert page.total == 2
    assert [item.source_entity_id for item in page.items] == ["source:2", "source:1"]


def test_postgres_identity_link_repository_keeps_same_link_id_kb_scoped(
    provider: ConnectionProvider,
) -> None:
    repository = PostgresIdentityLinkRepository(provider)
    shared_id = "identity_link:shared-canonical-source"
    first = _link(shared_id).model_copy(
        update={
            "knowledge_base_id": _KB_ID,
            "canonical_entity_id": "canonical:1",
            "source_entity_id": "source:1",
        },
        deep=True,
    )
    second = _link(shared_id).model_copy(
        update={
            "knowledge_base_id": _KB_ID + "-other",
            "canonical_entity_id": "canonical:2",
            "source_entity_id": "source:2",
        },
        deep=True,
    )

    repository.upsert_link(first)
    repository.upsert_link(second)

    stored_first = repository.get_link(knowledge_base_id=_KB_ID, link_id=shared_id)
    stored_second = repository.get_link(
        knowledge_base_id=_KB_ID + "-other",
        link_id=shared_id,
    )

    assert stored_first is not None
    assert stored_second is not None
    assert stored_first.canonical_entity_id == "canonical:1"
    assert stored_second.canonical_entity_id == "canonical:2"


def test_identity_links_constraint_rejects_any_invalid_decision_history_item(
    provider: ConnectionProvider,
) -> None:
    with pytest.raises(Exception, match="ck_identity_links_decision_history_values"):
        with provider.connection() as conn:
            conn.execute(
                """
                INSERT INTO identity_links (
                    id, knowledge_base_id, canonical_entity_id, source_entity_id,
                    relationship_type, confidence, score, review_state,
                    decision_source, source_refs, match_reasons, decision_history,
                    created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s::jsonb, %s::jsonb, %s::jsonb,
                    %s, %s
                )
                """,
                (
                    "identity_link:invalid-history",
                    _KB_ID,
                    "canonical:invalid-history",
                    "source:invalid-history",
                    "resolved_identity",
                    "medium",
                    0.5,
                    "steward_review",
                    "test",
                    "[]",
                    "[]",
                    (
                        "["
                        '{"decision":"approve_merge","actor_user_id":"steward-1"},'
                        '{"decision":"invalid_decision","actor_user_id":"steward-2"}'
                        "]"
                    ),
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
            )
            conn.commit()
