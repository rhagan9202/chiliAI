# SAFE-CMS-017 First-Class Connectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class connector definitions and sync-run tracking so CMS-like source pulls can be configured, inspected, replayed, quarantined, and audited without exposing credentials.

**Architecture:** Start with a domain-neutral `connectors` backend package that owns manifests, sync-run records, quarantine records, repository protocols, and an in-memory adapter. Later tasks expose KB-scoped API routes, add a local filesystem pull adapter, and publish ingestion-compatible receipts/events through existing ingestion boundaries rather than inventing a parallel pipeline.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest, existing audit/RBAC/repository conventions, React/Vitest for later management UI.

---

## File Structure

- Create `backend/connectors/models.py`: connector definitions, schedule, credentials reference, mapping reference, sync run, sync counters, quarantine record, and pages.
- Create `backend/connectors/repository.py`: repository protocol for definitions, runs, and quarantine records.
- Create `backend/connectors/adapters/in_memory.py`: dict-backed repository for tests/local development.
- Create `backend/connectors/adapters/__init__.py`: adapter exports.
- Create `backend/connectors/__init__.py`: package exports.
- Create `backend/connectors/service.py`: lifecycle service for registering connectors, starting/completing/failing runs, and quarantining records.
- Modify `backend/pyproject.toml`: include the new connector package and tests in packaging/Pyright discovery.
- Modify `backend/api/contracts.py`: request/response models for connector definitions and sync runs.
- Create `backend/api/routers/connectors.py`: KB-scoped connector browse/register/run/quarantine endpoints.
- Modify `backend/api/dependencies.py`: singleton connector service dependency.
- Modify `backend/api/app.py`: include connector router.
- Modify `backend/capabilities/registry.py`: make `connector.sync.status` reflect the new connector run contract.
- Later frontend files under `chili_app/src/api/connectors.ts`, `chili_app/src/components/connectors/`, and `chili_app/src/pages/ConfigurationPage.tsx`.

## Implementation Status

- Completed in this pass: Tasks 1 through 3.
- Remaining work: Tasks 4 and 5.

---

### Task 1: Connector Models And In-Memory Repository

**Files:**
- Create: `backend/connectors/models.py`
- Create: `backend/connectors/repository.py`
- Create: `backend/connectors/adapters/in_memory.py`
- Create: `backend/connectors/adapters/__init__.py`
- Create: `backend/connectors/__init__.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/connectors/test_in_memory.py`

- [x] **Step 1: Write failing model and repository tests**

Create `backend/tests/connectors/test_in_memory.py`:

```python
from __future__ import annotations

from connectors import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorSyncCounters,
    ConnectorSyncRunCreate,
    ConnectorSyncRunUpdate,
    ConnectorQuarantineRecordCreate,
)
from connectors.adapters.in_memory import InMemoryConnectorRepository


def _definition_payload() -> ConnectorDefinitionCreate:
    return ConnectorDefinitionCreate(
        connector_id="cms-claims-drop",
        name="CMS Claims Drop",
        source_type="filesystem",
        knowledge_base_id="kb-cms",
        domain_name="medicare_fraud",
        credentials_ref="env:CMS_CONNECTOR_TOKEN",
        schedule=ConnectorSchedule(mode="manual"),
        mapping=ConnectorMappingRef(
            mapping_id="claims-feed",
            mapping_version="v1",
            feed_name="claims_feed",
        ),
        config={"path": "/imports/cms/claims.csv"},
    )


def test_repository_saves_definitions_without_exposing_credentials() -> None:
    repository = InMemoryConnectorRepository()

    definition = repository.save_definition(_definition_payload())

    assert definition.connector_id == "cms-claims-drop"
    assert definition.credentials_ref == "env:CMS_CONNECTOR_TOKEN"
    assert definition.credentials_display == "env:CMS_...OKEN"
    assert definition.config == {"path": "/imports/cms/claims.csv"}
    page = repository.list_definitions(knowledge_base_id="kb-cms")
    assert page.total_items == 1
    assert page.items[0].connector_id == "cms-claims-drop"


def test_repository_tracks_runs_and_quarantine_by_connector() -> None:
    repository = InMemoryConnectorRepository()
    repository.save_definition(_definition_payload())

    run = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
            idempotency_key="run-key-1",
        )
    )
    updated = repository.update_run(
        run.run_id,
        ConnectorSyncRunUpdate(
            status="completed",
            counters=ConnectorSyncCounters(
                pulled=12,
                accepted=10,
                quarantined=2,
                failed=0,
            ),
            ingest_correlation_id="ingest-1",
            source_cursor="cursor-12",
        ),
    )
    quarantine = repository.add_quarantine_record(
        ConnectorQuarantineRecordCreate(
            run_id=run.run_id,
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            source_record_id="claim-99",
            reason="missing provider_npi",
            raw_ref="object://connector/cms-claims-drop/claim-99.json",
        )
    )

    assert updated.status == "completed"
    assert updated.counters.quarantined == 2
    assert updated.completed_at is not None
    assert quarantine.quarantine_id.startswith(f"{run.run_id}:")
    assert repository.list_runs(connector_id="cms-claims-drop").total_items == 1
    assert repository.list_quarantine(run_id=run.run_id).items[0].source_record_id == "claim-99"
```

- [x] **Step 2: Run focused red tests**

Run: `uv run --project backend pytest backend/tests/connectors/test_in_memory.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'connectors'`.

- [x] **Step 3: Implement models and in-memory repository**

Add immutable Pydantic models for definitions and mutable run records. Use `credentials_ref` only as a reference string and expose `credentials_display` as a redacted computed field:

```python
def _redact_credentials_ref(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 8:
        return "..."
    return f"{value[:7]}...{value[-4:]}"
```

The in-memory repository must deep-copy records on read/write, sort definitions by `(knowledge_base_id, connector_id)`, sort runs newest first by `started_at`, and sort quarantine records by `(run_id, source_record_id)`.

- [x] **Step 4: Run focused green tests and lint**

Run:

```bash
uv run --project backend pytest backend/tests/connectors/test_in_memory.py -q
uv run --project backend ruff check backend/connectors backend/tests/connectors/test_in_memory.py
uv run --project backend pyright
```

Expected: PASS, Ruff clean, and Pyright reports `0 errors, 0 warnings`.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/connectors backend/tests/connectors backend/pyproject.toml docs/superpowers/plans/2026-08-05-safe-cms-017-first-class-connectors.md
git commit -m "feat: add connector models and repository"
```

### Task 2: Connector Lifecycle Service

**Files:**
- Create: `backend/connectors/service.py`
- Test: `backend/tests/connectors/test_service.py`

- [x] **Step 1: Write failing service tests**

Create service tests proving registration validates KB scope, duplicate connector ids are idempotent only when the definition matches, `start_sync()` reuses an existing run with the same idempotency key, and `complete_sync()` records counters and ingest correlation.

- [x] **Step 2: Run focused red tests**

Run: `uv run --project backend pytest backend/tests/connectors/test_service.py -q`

Expected: FAIL because `connectors.service` does not exist.

- [x] **Step 3: Implement `ConnectorService`**

The service wraps `ConnectorRepositoryProtocol`, exposes `register_connector()`, `list_connectors()`, `start_sync()`, `complete_sync()`, `fail_sync()`, and `quarantine_record()`, and never returns raw credentials beyond `credentials_ref`.

- [x] **Step 4: Run focused green tests and lint**

Run:

```bash
uv run --project backend pytest backend/tests/connectors/test_service.py backend/tests/connectors/test_in_memory.py -q
uv run --project backend ruff check backend/connectors backend/tests/connectors
```

Expected: PASS and Ruff clean.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/connectors backend/tests/connectors docs/superpowers/plans/2026-08-05-safe-cms-017-first-class-connectors.md
git commit -m "feat: add connector lifecycle service"
```

### Task 3: Connector API Contracts And Routes

**Files:**
- Modify: `backend/api/contracts.py`
- Create: `backend/api/routers/connectors.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/app.py`
- Test: `backend/tests/api/test_connectors_router.py`

- [x] **Step 1: Write failing API tests**

Add tests for viewer listing connectors, analyst registering a connector with a credentials reference, analyst starting a sync run, and quarantine list visibility without raw secrets.

- [x] **Step 2: Run focused red API tests**

Run: `uv run --project backend pytest backend/tests/api/test_connectors_router.py -q`

Expected: FAIL with missing router or 404.

- [x] **Step 3: Implement API contracts and router**

Add KB-scoped routes:

```text
GET /knowledgebases/{knowledge_base_id}/connectors
POST /knowledgebases/{knowledge_base_id}/connectors
POST /knowledgebases/{knowledge_base_id}/connectors/{connector_id}/sync-runs
GET /knowledgebases/{knowledge_base_id}/connectors/{connector_id}/sync-runs
GET /knowledgebases/{knowledge_base_id}/connectors/{connector_id}/quarantine
```

- [x] **Step 4: Regenerate OpenAPI and frontend contracts**

Run:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
npm run codegen:api
```

- [x] **Step 5: Run focused green API tests and app route tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_connectors_router.py backend/tests/api/test_app.py -q
```

Expected: PASS.

- [x] **Step 6: Commit**

Run:

```bash
git add backend/api backend/connectors backend/tests/api chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts docs/superpowers/plans/2026-08-05-safe-cms-017-first-class-connectors.md
git commit -m "feat: expose connector management api"
```

### Task 4: Connector Capability Status Adapter

**Files:**
- Modify: `backend/capabilities/registry.py`
- Create: `backend/connectors/status_adapter.py`
- Test: `backend/tests/connectors/test_status_adapter.py`
- Test: `backend/tests/capabilities/test_registry.py`

- [ ] **Step 1: Write failing status adapter tests**

Add tests proving `connector.sync.status` returns latest run status, counters, source cursor, and audit-safe connector metadata through `CapabilityExecutionEnvelope`.

- [ ] **Step 2: Run focused red tests**

Run: `uv run --project backend pytest backend/tests/connectors/test_status_adapter.py -q`

Expected: FAIL because `connectors.status_adapter` does not exist.

- [ ] **Step 3: Implement status adapter and manifest schema update**

Use the connector service/repository to resolve latest run for a connector and return a read-only envelope. Keep `credentials_ref` out of the output.

- [ ] **Step 4: Run focused green tests**

Run:

```bash
uv run --project backend pytest backend/tests/connectors/test_status_adapter.py backend/tests/capabilities/test_registry.py -q
uv run --project backend ruff check backend/connectors backend/capabilities backend/tests/connectors backend/tests/capabilities/test_registry.py
```

Expected: PASS and Ruff clean.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/connectors backend/capabilities/registry.py backend/tests/connectors backend/tests/capabilities/test_registry.py docs/superpowers/plans/2026-08-05-safe-cms-017-first-class-connectors.md
git commit -m "feat: add connector status capability adapter"
```

### Task 5: Final Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-08-05-safe-cms-017-first-class-connectors.md`

- [ ] **Step 1: Run backend gates**

Run:

```bash
uv run --project backend pytest backend/tests/connectors backend/tests/api/test_connectors_router.py backend/tests/capabilities/test_registry.py -q
uv run --project backend pytest -m "not integration" backend/tests -q
uv run --project backend ruff check backend
uv run --project backend pyright
```

- [ ] **Step 2: Run frontend gates after API contract work**

Run:

```bash
npm run test:run
npm run build
```

- [ ] **Step 3: Run migration/schema and whitespace gates**

Run:

```bash
scripts/ci_migration_check.sh
git diff --check
```

- [ ] **Step 4: Commit final plan status**

Run:

```bash
git add docs/superpowers/plans/2026-08-05-safe-cms-017-first-class-connectors.md
git commit -m "docs: update safe cms 017 plan status"
```
