"""Shared backend pytest configuration.

Integration tests (``@pytest.mark.integration``) each read a service URL env var
and skip when it is unset. Per the project rule that integration/e2e tests run
against the full running stack, the defaults below point those vars at the live
dev stack (``make dev`` / ``docker-compose.dev.yaml``) so the tests RUN instead of
silently skipping — no per-shell exports needed.

``os.environ.setdefault`` is used so an explicitly-provided value always wins
(CI and ``make test`` both export ``DATABASE_URL`` explicitly), while bare host
``.venv`` runs fall back to the localhost-published ports. The stack must be
up; if a service is unreachable the integration test fails (surfacing a real
problem) rather than skipping.

Smokes that are not docker-compose stack services are intentionally NOT defaulted
and remain opt-in (they need an external secret, a model download, or a separate
daemon, none of which belong in the dev stack): ``OPENAI_API_KEY`` (paid external
API), ``SENTENCE_TRANSFORMERS_SMOKE_MODEL`` (large model download), and the Ollama
e2e (``OLLAMA_MODEL`` + a reachable Ollama server). Set these explicitly to
exercise those paths.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _setdefault_test_service_urls() -> None:
    """Default integration-test service URLs to the live stack.

    Test-specific vars derive from the app-style vars when present (the
    in-container case) and fall back to localhost-published ports (the host
    ``.venv`` case).
    """

    # DELIBERATELY chili_test, never the dev-stack ``chili`` DB: the migration
    # integration tests run ``alembic downgrade base`` against DATABASE_URL,
    # which empties every app table. Defaulting to the dev DB has destroyed
    # seeded demo state twice (2026-05, 2026-07-16). The dev compose stack
    # creates ``chili_test`` via infra/postgres/init-test-db.sql; an explicit
    # DATABASE_URL (CI, ``make test`` — both export chili-test-safe DSNs) wins.
    os.environ.setdefault(
        "DATABASE_URL", "postgresql://chili:chili@localhost:5432/chili_test"
    )
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
    os.environ.setdefault(
        "CHILI_TEST_REDIS_URL",
        os.environ.get("REDIS_URL", "redis://localhost:6379"),
    )
    os.environ.setdefault(
        "NEO4J_TEST_URI",
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
    )
    # The dev stack runs Neo4j with NEO4J_AUTH=none, so any non-empty value
    # connects; derive from the app password when one is configured.
    os.environ.setdefault(
        "NEO4J_TEST_PASSWORD",
        os.environ.get("NEO4J_PASSWORD", "none"),
    )


_setdefault_test_service_urls()


@pytest.fixture(scope="session", autouse=True)
def _ensure_migrated_test_database() -> None:
    """Bring a fresh ``chili_test`` to ``alembic upgrade head`` once per session.

    ``infra/postgres/init-test-db.sql`` creates the test database *empty*; the
    Postgres-backed integration tests assume the schema exists and historically
    only passed because an earlier full run's ``test_migrations.py`` had left
    ``upgrade head`` applied. On a genuinely fresh volume (first ``make test``
    after ``make clean``) every table-touching test failed with
    ``UndefinedTable`` before the migration test ran (suite order puts
    ``tests/api``/``tests/cases``/``tests/conversations`` first). This fixture
    removes that order/state dependency: if the database is reachable and has
    no ``alembic_version`` table, apply migrations before any test runs.

    Unreachable database → do nothing (unit-only runs without the dev stack
    keep working; integration tests fail/skip exactly as they do today).
    """

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return
    try:
        import psycopg
    except ImportError:
        return
    try:
        with psycopg.connect(database_url, connect_timeout=3) as conn:
            row = conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()
            already_migrated = row is not None and row[0] is not None
    except psycopg.Error:
        return
    if already_migrated:
        return
    import subprocess
    import sys

    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head against the test database failed:\n"
            f"{result.stderr}"
        )


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "defaults"
    / "medicare_fraud.yaml"
)


@pytest.fixture(autouse=True)
def default_chili_config_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Give tests a deterministic domain config unless a case overrides it.

    ``CHILI_ACTIVE_PACK_STATE_PATH`` is pointed at a per-test temp location so
    an active-pack pointer written on the developer machine (or by another
    test) can never retarget the suite away from ``CHILI_CONFIG_PATH`` — see
    ``config/store.py`` (pointer > env precedence).

    ``CHILI_CONFIG_OVERLAY_PATH`` is scrubbed for the same reason: a developer
    shell following the README overlay worked example would otherwise layer
    the dev overlay onto every ``load_config`` call in the suite (BL-044).
    Overlay tests set it explicitly via their own ``monkeypatch``.
    """

    monkeypatch.delenv("CHILI_CONFIG_OVERLAY_PATH", raising=False)
    monkeypatch.setenv("CHILI_CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
    monkeypatch.setenv("CHILI_ENV", "local")
    monkeypatch.setenv(
        "CHILI_ACTIVE_PACK_STATE_PATH", str(tmp_path / "active_pack.json")
    )
