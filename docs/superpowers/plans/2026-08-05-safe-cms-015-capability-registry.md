# SAFE-CMS-015 Capability Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the temporary workflow capability allow-list with a typed registry that exposes discoverable capability metadata, permission requirements, domain compatibility, health, examples, and typed execution envelopes.

**Architecture:** Add a focused `capabilities` backend package containing immutable capability manifests and a registry service. Expose a KB-scoped browse endpoint through FastAPI, then make workflow-definition validation consult the registry rather than the `SAFE-CMS-014` built-in constant. Later tasks add policy override checks, execution adapters, and frontend browsing without coupling individual modules to workflow internals.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI dependency injection, pytest, existing chiliAI audit/RBAC patterns.

---

## File Structure

- Create `backend/capabilities/models.py`: Pydantic models for manifests, JSON schemas, permission requirements, health, examples, query filters, registry pages, and execution envelopes.
- Create `backend/capabilities/registry.py`: in-process registry interface plus default static manifests for the five `SAFE-CMS-015` derisking capabilities.
- Create `backend/capabilities/service.py`: browse/filter service and lookup helpers used by API and workflow-definition validation.
- Create `backend/capabilities/__init__.py`: package exports.
- Modify `backend/workflow_definitions/service.py`: inject `CapabilityRegistryService` and validate workflow definitions against registered manifests.
- Modify `backend/api/contracts.py`: API response contracts for registry browsing.
- Create `backend/api/routers/capabilities.py`: KB-scoped capability browse endpoint with viewer RBAC and KB scoping.
- Modify `backend/api/dependencies.py`: provide the singleton default registry service and pass it into `WorkflowDefinitionService`.
- Modify `backend/api/app.py`: include the new router.
- Add tests under `backend/tests/capabilities/`, `backend/tests/workflow_definitions/`, and `backend/tests/api/`.

---

## Implementation Status

- Completed in this pass: Tasks 1, 2, 3, 4, and 5.
- Completed verification in this pass: focused capability/workflow/API tests, full non-integration backend tests, Ruff, Pyright, OpenAPI export, API codegen, focused frontend tests, full frontend test suite, frontend build, migration replay, and whitespace checks.
- Remaining work: final verified commit.

---

### Task 1: Typed Capability Manifest Registry

**Files:**
- Create: `backend/capabilities/models.py`
- Create: `backend/capabilities/registry.py`
- Create: `backend/capabilities/service.py`
- Create: `backend/capabilities/__init__.py`
- Test: `backend/tests/capabilities/test_registry.py`

- [x] **Step 1: Write the failing model and registry tests**

```python
from capabilities import CapabilityQuery, create_default_capability_registry_service


def test_default_registry_exposes_safe_cms_015_derisking_capabilities() -> None:
    service = create_default_capability_registry_service()

    page = service.list_capabilities(CapabilityQuery(domain_name="medicare_fraud"))

    assert page.total_items == 5
    assert [item.capability_id for item in page.items] == [
        "analytics.peer_context",
        "evidence.checklist.generate",
        "rag.query",
        "case.note.draft",
        "connector.sync.status",
    ]
    peer_context = service.get_required("analytics.peer_context")
    assert peer_context.input_schema["type"] == "object"
    assert peer_context.output_schema["type"] == "object"
    assert peer_context.permission.required_roles == ["analyst"]
    assert peer_context.domain_compatibility.supported_domains == ["medicare_fraud"]


def test_registry_filters_by_role_domain_and_side_effect_class() -> None:
    service = create_default_capability_registry_service()

    page = service.list_capabilities(
        CapabilityQuery(
            domain_name="medicare_fraud",
            role="viewer",
            side_effect_class="read",
        )
    )

    assert {item.capability_id for item in page.items} == {
        "analytics.peer_context",
        "rag.query",
        "connector.sync.status",
    }
```

- [x] **Step 2: Run the focused red test**

Run: `uv run --project backend pytest backend/tests/capabilities/test_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'capabilities'`.

- [x] **Step 3: Implement the registry models and static manifest catalog**

Create Pydantic models with these fields:

```python
CapabilityManifest(
    capability_id: str,
    version: str,
    module: str,
    label: str,
    description: str,
    input_schema: dict[str, JsonValue],
    output_schema: dict[str, JsonValue],
    side_effect_class: Literal["read", "write", "external_call", "approval"],
    permission: CapabilityPermission(required_roles=list[str], requires_audit=bool),
    domain_compatibility: CapabilityDomainCompatibility(
        supported_domains=list[str], unsupported_domains=list[str], environment_tags=list[str]
    ),
    health: CapabilityHealth(status=Literal["healthy", "degraded", "disabled"], last_checked_at=datetime | None, details=str | None),
    examples: list[CapabilityExample],
)
```

Register exactly these default capability IDs for the first sprint slice:

```python
[
    "analytics.peer_context",
    "evidence.checklist.generate",
    "rag.query",
    "case.note.draft",
    "connector.sync.status",
]
```

- [x] **Step 4: Run the focused green test**

Run: `uv run --project backend pytest backend/tests/capabilities/test_registry.py -q`
Expected: PASS.

- [x] **Step 5: Commit** - batched into the final verified sprint-slice commit.

Run:

```bash
git add backend/capabilities backend/tests/capabilities docs/superpowers/plans/2026-08-05-safe-cms-015-capability-registry.md
git commit -m "feat: add capability registry"
```

### Task 2: Capability Browse API

**Files:**
- Modify: `backend/api/contracts.py`
- Create: `backend/api/routers/capabilities.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/app.py`
- Test: `backend/tests/api/test_capabilities_router.py`
- Test: `backend/tests/api/test_app.py`

- [x] **Step 1: Write the failing API tests**

```python
def test_viewer_can_browse_kb_capabilities() -> None:
    app = _app_harness()
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(f"/knowledgebases/{KB_ID}/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["items"][0]["capability_id"] == "analytics.peer_context"
    assert body["items"][0]["input_schema"]["type"] == "object"


def test_capability_browse_filters_by_role_and_side_effect_class() -> None:
    app = _app_harness()
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(
            f"/knowledgebases/{KB_ID}/capabilities",
            params={"role": "viewer", "side_effect_class": "read"},
        )

    assert response.status_code == 200
    assert {item["capability_id"] for item in response.json()["items"]} == {
        "analytics.peer_context",
        "rag.query",
        "connector.sync.status",
    }
```

- [x] **Step 2: Run the focused red API test**

Run: `uv run --project backend pytest backend/tests/api/test_capabilities_router.py -q`
Expected: FAIL with 404 or missing import for the new router.

- [x] **Step 3: Implement contracts, dependency, and router**

Add response models:

```python
CapabilityManifestResponse
CapabilityListResponse
CapabilityPermissionResponse
CapabilityDomainCompatibilityResponse
CapabilityHealthResponse
CapabilityExampleResponse
```

Add `get_capability_registry_service()` in `api.dependencies`, include it in `CONFIG_CACHE_REGISTRY`, and include `capabilities_router` in `api.app`.

- [x] **Step 4: Run focused API tests and app route tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_capabilities_router.py backend/tests/api/test_app.py -q
```

Expected: PASS.

- [x] **Step 5: Commit** - batched into the final verified sprint-slice commit.

Run:

```bash
git add backend/api backend/tests/api backend/capabilities docs/superpowers/plans/2026-08-05-safe-cms-015-capability-registry.md
git commit -m "feat: expose capability registry api"
```

### Task 3: Workflow Definition Validation Integration

**Files:**
- Modify: `backend/workflow_definitions/models.py`
- Modify: `backend/workflow_definitions/service.py`
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/workflow_definitions/test_service.py`
- Test: `backend/tests/api/test_workflow_definitions_router.py`

- [x] **Step 1: Write failing validation tests**

```python
def test_create_draft_accepts_registered_connector_status_capability() -> None:
    service, _, _, _ = _service()
    payload = _valid_create_payload().model_copy(
        update={
            "allowed_capability_refs": ["connector.sync.status"],
            "steps": [
                WorkflowStepDefinition(
                    step_id="sync-status",
                    label="Connector status",
                    capability_ref="connector.sync.status",
                )
            ],
        }
    )

    created = service.create_draft("kb-1", payload, **ACTOR_KWARGS)

    assert created.steps[0].capability_ref == "connector.sync.status"
```

- [x] **Step 2: Run the focused red validation test**

Run: `uv run --project backend pytest backend/tests/workflow_definitions/test_service.py::test_create_draft_accepts_registered_connector_status_capability -q`
Expected: FAIL because the old hard-coded workflow allow-list does not include `connector.sync.status`.

- [x] **Step 3: Inject the capability registry service**

Change `WorkflowDefinitionService.__init__` to accept `capability_registry: CapabilityRegistryService | None = None`, default it to `create_default_capability_registry_service()`, and validate allowed/step capability refs through registry lookups.

- [x] **Step 4: Run workflow-definition tests**

Run:

```bash
uv run --project backend pytest backend/tests/workflow_definitions/test_service.py backend/tests/api/test_workflow_definitions_router.py -q
```

Expected: PASS.

- [x] **Step 5: Commit** - batched into the final verified sprint-slice commit.

Run:

```bash
git add backend/workflow_definitions backend/api/dependencies.py backend/tests/workflow_definitions backend/tests/api docs/superpowers/plans/2026-08-05-safe-cms-015-capability-registry.md
git commit -m "feat: validate workflows with capability registry"
```

### Task 4: Permission Policy Checks and Execution Envelopes

**Files:**
- Modify: `backend/capabilities/service.py`
- Modify: `backend/capabilities/models.py`
- Test: `backend/tests/capabilities/test_registry.py`

- [x] **Step 1: Write failing tests for role denial and typed envelopes**
- [x] **Step 2: Add `authorize()` and `CapabilityExecutionEnvelope` helpers**
- [x] **Step 3: Run focused capability tests**
- [x] **Step 4: Commit** - batched into the final verified sprint-slice commit.

### Task 5: Registry Browser UI

**Files:**
- Modify: `chili_app/src/**`
- Test: relevant frontend tests or build gate

- [x] **Step 1: Locate the existing admin/workflow navigation surface**
- [x] **Step 2: Add generated API types after backend contract export**
- [x] **Step 3: Add a dense capability registry browser with schema, permission, domain, health, and example details**
- [x] **Step 4: Run frontend build and focused tests**
- [x] **Step 5: Commit** - batched into the final verified sprint-slice commit.

### Task 6: Final Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-08-05-safe-cms-015-capability-registry.md`

- [x] **Step 1: Run backend focused gates**

Run:

```bash
uv run --project backend pytest backend/tests/capabilities backend/tests/workflow_definitions backend/tests/api/test_capabilities_router.py backend/tests/api/test_workflow_definitions_router.py -q
```

- [x] **Step 2: Run broad backend gates**

Run:

```bash
uv run --project backend pytest -m "not integration" backend/tests -q
uv run --project backend ruff check backend
uv run --project backend pyright
scripts/ci_migration_check.sh
```

- [x] **Step 3: Run frontend gate after UI work**

Run:

```bash
npm run build
```

- [x] **Step 4: Commit final plan status** - batched into the final verified sprint-slice commit.

Run:

```bash
git add docs/superpowers/plans/2026-08-05-safe-cms-015-capability-registry.md
git commit -m "docs: update safe cms 015 plan status"
```
