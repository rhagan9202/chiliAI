# SAFE-CMS-018 Readiness Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global KB/domain readiness control plane so app surfaces share one active context and expose blockers before users act on stale or incomplete data.

**Architecture:** Introduce a backend `readiness` package that aggregates existing KB summary, document status projection, connector state, workflow definitions, and capability registry into one KB-scoped response. Expose it through a viewer-gated FastAPI route, regenerate OpenAPI contracts, then wire the app shell to show a compact active-KB selector and readiness panel using the existing URL-backed `useActiveKnowledgeBase()` hook.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest, Ruff, Pyright, React 19, TanStack Query, Vitest, generated OpenAPI TypeScript contracts.

---

## File Structure

- Create `backend/readiness/models.py`: readiness component status literals, blocker/warning records, KB context summary, and aggregate response models.
- Create `backend/readiness/service.py`: pure aggregation service over existing repository/service protocols.
- Create `backend/readiness/__init__.py`: package exports.
- Modify `backend/pyproject.toml`: include `readiness*` and `tests/readiness` in packaging/Pyright discovery.
- Test `backend/tests/readiness/test_service.py`: service aggregation behavior without FastAPI.
- Modify `backend/api/contracts.py`: wire-level readiness response models.
- Create `backend/api/routers/readiness.py`: `GET /knowledgebases/{knowledge_base_id}/readiness`.
- Modify `backend/api/dependencies.py`: readiness service dependency.
- Modify `backend/api/app.py`: include readiness router.
- Test `backend/tests/api/test_readiness_router.py`: auth/Kb scope, response shape, no-ready blockers.
- Regenerate `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts`.
- Create `chili_app/src/api/readiness.ts`: query key, fetcher, and hook.
- Create `chili_app/src/components/layout/WorkspaceControl.tsx`: active KB selector plus compact readiness status and details.
- Modify `chili_app/src/components/layout/TopBar.tsx`: render `WorkspaceControl`.
- Modify `chili_app/src/components/layout/AppShell.tsx`: pass active-KB state into the top bar.
- Test `chili_app/src/api/__tests__/readiness.test.ts`, `chili_app/src/components/layout/__tests__/WorkspaceControl.test.tsx`, and `chili_app/src/components/layout/__tests__/AppShell.test.tsx`.

## Implementation Status

- Completed in this pass: Tasks 1 and 2.
- Remaining work: Tasks 3 through 5.

---

### Task 1: Readiness Domain Model And Service

**Files:**
- Create: `backend/readiness/models.py`
- Create: `backend/readiness/service.py`
- Create: `backend/readiness/__init__.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/readiness/test_service.py`

- [x] **Step 1: Write failing service tests**

Create `backend/tests/readiness/test_service.py` with tests that seed:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.service import AuditLogService
from capabilities.service import create_default_capability_registry_service
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorSyncCounters,
)
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.service import ConnectorService
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from readiness.service import ReadinessService
from shared.types import KnowledgeBase
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import WorkflowDefinitionCreate, WorkflowStepDefinition
from workflow_definitions.service import WorkflowDefinitionService


BASE_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
KnowledgeBaseStatus = Literal["active", "building", "ready", "error", "archived"]


def _kb(status: KnowledgeBaseStatus = "ready") -> KnowledgeBase:
    return KnowledgeBase(
        id="kb-cms",
        name="CMS Fraud KB",
        description="Readiness test KB",
        domain="medicare_fraud",
        status=status,
        document_count=3,
        entity_count=25,
        relationship_count=40,
        created_at=BASE_TIME,
    )


def _service() -> tuple[
    ReadinessService,
    ConnectorService,
    WorkflowDefinitionService,
    InMemoryKnowledgeBaseRepository,
]:
    kb_repository = InMemoryKnowledgeBaseRepository()
    connector_service = ConnectorService(InMemoryConnectorRepository())
    workflow_service = WorkflowDefinitionService(
        InMemoryWorkflowDefinitionRepository(),
        InMemoryWorkflowRunStore(),
        AuditLogService(InMemoryAuditLogRepository()),
    )
    return (
        ReadinessService(
            knowledge_base_repository=kb_repository,
            connector_service=connector_service,
            workflow_definition_service=workflow_service,
            capability_registry=create_default_capability_registry_service(),
            active_domain_name="medicare_fraud",
        ),
        connector_service,
        workflow_service,
        kb_repository,
    )


def test_readiness_is_ready_when_kb_connectors_workflows_and_capabilities_are_ready() -> None:
    readiness_service, connector_service, workflow_service, kb_repository = _service()
    kb_repository.create(_kb())
    connector_service.register_connector(
        "kb-cms",
        ConnectorDefinitionCreate(
            connector_id="cms-claims",
            name="CMS Claims",
            source_type="filesystem",
            knowledge_base_id="kb-cms",
            credentials_ref="env:CMS_CONNECTOR_TOKEN",
            schedule=ConnectorSchedule(mode="manual"),
            mapping=ConnectorMappingRef(
                mapping_id="claims-feed",
                mapping_version="v1",
                feed_name="claims_feed",
            ),
            config={"path": "/imports/cms/claims.csv"},
        ),
    )
    run = connector_service.start_sync(
        knowledge_base_id="kb-cms",
        connector_id="cms-claims",
        requested_by="operator-1",
    )
    connector_service.complete_sync(
        run.run_id,
        counters=ConnectorSyncCounters(pulled=3, accepted=3, quarantined=0, failed=0),
        ingest_correlation_id="ingest-1",
        source_cursor="claims.csv:3",
    )
    workflow_service.create_draft(
        "kb-cms",
        WorkflowDefinitionCreate(
            definition_id="daily-review",
            name="Daily Review",
            version="v1",
            domain_name="medicare_fraud",
            allowed_capability_refs=["rag.query"],
            steps=[
                WorkflowStepDefinition(
                    step_id="ask",
                    label="Ask",
                    capability_ref="rag.query",
                )
            ],
        ),
        actor_user_id="analyst-1",
        actor_email="analyst@example.test",
        actor_roles=["analyst"],
        correlation_id="corr-1",
    )

    readiness = readiness_service.get_readiness("kb-cms")

    assert readiness.ready is True
    assert readiness.knowledge_base.id == "kb-cms"
    assert readiness.active_domain_name == "medicare_fraud"
    assert readiness.components["knowledge_base"].status == "ready"
    assert readiness.components["connectors"].status == "ready"
    assert readiness.components["workflows"].status == "ready"
    assert readiness.components["capabilities"].status == "ready"
    assert readiness.blockers == []
    assert readiness.components["connectors"].details["completed_runs"] == 1


def test_readiness_reports_blockers_for_building_kb_no_connectors_and_no_workflows() -> None:
    readiness_service, _connector_service, _workflow_service, kb_repository = _service()
    kb_repository.create(_kb(status="building"))

    readiness = readiness_service.get_readiness("kb-cms")

    assert readiness.ready is False
    assert {blocker.component for blocker in readiness.blockers} == {
        "knowledge_base",
        "connectors",
        "workflows",
    }
    assert readiness.components["knowledge_base"].status == "blocked"
    assert readiness.components["connectors"].status == "blocked"
    assert readiness.components["workflows"].status == "blocked"
    available_count = cast(
        int,
        readiness.components["capabilities"].details["available_count"],
    )
    assert available_count > 0
```

- [x] **Step 2: Run focused red tests**

Run: `uv run --project backend pytest backend/tests/readiness/test_service.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'readiness'`.

- [x] **Step 3: Implement minimal readiness models and service**

Create Pydantic models with:

```python
ReadinessComponentStatus = Literal["ready", "blocked", "warning", "unknown"]

class ReadinessIssue(BaseModel):
    component: str
    code: str
    message: str
    action: str | None = None

class ReadinessComponent(BaseModel):
    status: ReadinessComponentStatus
    label: str
    summary: str
    blockers: list[ReadinessIssue] = Field(default_factory=list)
    warnings: list[ReadinessIssue] = Field(default_factory=list)
    details: dict[str, JsonValue] = Field(default_factory=dict)

class ReadinessKnowledgeBaseSummary(BaseModel):
    id: str
    name: str
    domain: str | None = None
    status: str
    document_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    updated_at: datetime | None = None
    created_at: datetime

class ReadinessResponse(BaseModel):
    knowledge_base: ReadinessKnowledgeBaseSummary
    active_domain_name: str
    ready: bool
    components: dict[str, ReadinessComponent]
    blockers: list[ReadinessIssue] = Field(default_factory=list)
    warnings: list[ReadinessIssue] = Field(default_factory=list)
```

`ReadinessService.get_readiness(knowledge_base_id)` must:

- raise `KeyError(knowledge_base_id)` when the KB is missing;
- mark `knowledge_base` blocked unless `kb.status == "ready"`;
- warn on KB/domain mismatch instead of blocking;
- mark `connectors` blocked when there are no connector definitions or when the newest run for any connector is `failed`;
- mark `workflows` blocked when no workflow definitions exist for the KB;
- mark `capabilities` blocked when no capabilities are available for the active domain;
- set aggregate `ready` to `False` when any component has blockers.

- [x] **Step 4: Run focused green tests and lint/typecheck**

Run:

```bash
uv run --project backend pytest backend/tests/readiness/test_service.py -q
uv run --project backend ruff check backend/readiness backend/tests/readiness/test_service.py
uv run --project backend pyright
```

Expected: tests pass, Ruff clean, Pyright `0 errors, 0 warnings`.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/readiness backend/tests/readiness backend/pyproject.toml docs/superpowers/plans/2026-08-05-safe-cms-018-readiness-control.md
git commit -m "feat: add readiness aggregation service"
```

### Task 2: Readiness API Route And Contracts

**Files:**
- Modify: `backend/api/contracts.py`
- Create: `backend/api/routers/readiness.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/app.py`
- Test: `backend/tests/api/test_readiness_router.py`
- Generated: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts`

- [x] **Step 1: Write failing API tests**

Add tests for:

- viewer can fetch `GET /knowledgebases/{knowledge_base_id}/readiness`;
- viewer outside the KB scope gets `404`;
- response contains no credential references;
- missing KB returns `404`.

- [x] **Step 2: Run focused red API tests**

Run: `uv run --project backend pytest backend/tests/api/test_readiness_router.py -q`

Expected: FAIL with missing router or `404`.

- [x] **Step 3: Implement API contracts, dependency, and router**

Add wire models mirroring `ReadinessResponse`, then add:

```text
GET /knowledgebases/{knowledge_base_id}/readiness
```

The route must use `Depends(require_role("viewer"))`, the same KB-scope 404 behavior as capability/workflow routes, and `ReadinessService`.

- [x] **Step 4: Regenerate contracts**

Run:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
npm run codegen:api
```

- [x] **Step 5: Run focused green API tests and app route tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_readiness_router.py backend/tests/api/test_app.py -q
uv run --project backend ruff check backend/api/routers/readiness.py backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/tests/api/test_readiness_router.py backend/readiness backend/tests/readiness
uv run --project backend pyright
```

- [x] **Step 6: Commit**

Run:

```bash
git add backend/api backend/readiness backend/tests/api/test_readiness_router.py chili_app/openapi.json chili_app/src/lib/api/schema.ts docs/superpowers/plans/2026-08-05-safe-cms-018-readiness-control.md
git commit -m "feat: expose knowledge base readiness api"
```

### Task 3: Frontend Readiness API Client

**Files:**
- Create: `chili_app/src/api/readiness.ts`
- Test: `chili_app/src/api/__tests__/readiness.test.ts`

- [ ] **Step 1: Write failing frontend API tests**

Test that `getKnowledgeBaseReadiness("kb-1")` fetches `/knowledgebases/kb-1/readiness`, that `useKnowledgeBaseReadiness(null)` is disabled, and that query keys are stable.

- [ ] **Step 2: Run focused red tests**

Run: `npm run test:run -- src/api/__tests__/readiness.test.ts`

Expected: FAIL because `../readiness` does not exist.

- [ ] **Step 3: Implement API client and hook**

Use generated `KnowledgeBaseReadinessResponse` type from `src/api/contracts.ts`, `apiFetch`, and TanStack Query.

- [ ] **Step 4: Run focused green tests**

Run:

```bash
npm run test:run -- src/api/__tests__/readiness.test.ts
npm run build
```

- [ ] **Step 5: Commit**

Run:

```bash
git add chili_app/src/api/readiness.ts chili_app/src/api/__tests__/readiness.test.ts docs/superpowers/plans/2026-08-05-safe-cms-018-readiness-control.md
git commit -m "feat: add readiness api client"
```

### Task 4: App-Shell Workspace Control

**Files:**
- Create: `chili_app/src/components/layout/WorkspaceControl.tsx`
- Modify: `chili_app/src/components/layout/TopBar.tsx`
- Modify: `chili_app/src/components/layout/AppShell.tsx`
- Modify: `chili_app/src/components/layout/layout.css`
- Test: `chili_app/src/components/layout/__tests__/WorkspaceControl.test.tsx`
- Test: `chili_app/src/components/layout/__tests__/AppShell.test.tsx`

- [ ] **Step 1: Write failing component tests**

Cover:

- active KB selector renders the in-domain KB list from `useActiveKnowledgeBase`;
- choosing another KB calls `setActiveKnowledgeBase` and updates `?kb=`;
- readiness status shows blocked/ready and lists blocker actions without exposing credentials;
- no-ready-KB state is explicit.

- [ ] **Step 2: Run focused red tests**

Run:

```bash
npm run test:run -- src/components/layout/__tests__/WorkspaceControl.test.tsx src/components/layout/__tests__/AppShell.test.tsx
```

Expected: FAIL because `WorkspaceControl` does not exist or `TopBar` does not render it.

- [ ] **Step 3: Implement compact workspace control**

Render a top-bar control with:

- a labeled `<select>` for active KB;
- a small readiness badge;
- a details disclosure for blockers/warnings;
- disabled selector with explicit empty state when there is no active KB.

Use existing class naming under `app-topbar__*` and add only compact, app-shell-specific CSS.

- [ ] **Step 4: Run focused green tests and build**

Run:

```bash
npm run test:run -- src/components/layout/__tests__/WorkspaceControl.test.tsx src/components/layout/__tests__/AppShell.test.tsx
npm run build
```

- [ ] **Step 5: Commit**

Run:

```bash
git add chili_app/src/components/layout/WorkspaceControl.tsx chili_app/src/components/layout/TopBar.tsx chili_app/src/components/layout/AppShell.tsx chili_app/src/components/layout/layout.css chili_app/src/components/layout/__tests__/WorkspaceControl.test.tsx chili_app/src/components/layout/__tests__/AppShell.test.tsx docs/superpowers/plans/2026-08-05-safe-cms-018-readiness-control.md
git commit -m "feat: add workspace readiness control"
```

### Task 5: Final Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-08-05-safe-cms-018-readiness-control.md`

- [ ] **Step 1: Run backend gates**

Run:

```bash
uv run --project backend pytest backend/tests/readiness backend/tests/api/test_readiness_router.py backend/tests/api/test_app.py -q
uv run --project backend pytest -m "not integration" backend/tests -q
uv run --project backend ruff check backend
uv run --project backend pyright
```

- [ ] **Step 2: Run frontend gates**

Run:

```bash
npm run test:run
npm run build
```

- [ ] **Step 3: Run contract, migration, and whitespace gates**

Run:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
npm run codegen:api
scripts/ci_migration_check.sh
git diff --check
```

- [ ] **Step 4: Commit final plan status**

Run:

```bash
git add docs/superpowers/plans/2026-08-05-safe-cms-018-readiness-control.md
git commit -m "docs: update safe cms 018 plan status"
```
