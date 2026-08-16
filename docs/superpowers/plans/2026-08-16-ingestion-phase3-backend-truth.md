# Ingestion Phase 3 — Backend Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the backend able to answer the questions the UI has been guessing at — what a knowledge base can actually *do*, whether an upload will replace something, what parameters a score run should use, and who changed what — then surface each of those in the workspace that phase 2 built.

**Architecture:** Recompose the readiness aggregate around per-activity states rather than a binary flag, so optional-and-absent stops reading as blocked. Add a precheck endpoint so replace-on-upload is visible before submit rather than discovered after. Move score-run parameters out of a frontend hardcode into the domain pack. Extend the existing audit helper to the ingestion actions that were ruled material. Stop reporting a legitimate empty state as an analytics failure. Then wire each to the section that consumes it.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic, pytest, pyright strict; React 19 + TypeScript (Vite 8), TanStack Query, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-14-ingestion-experience-redesign-design.md` (§3a activities, §4 backend changes, §6 partial-delete, §8 phase 3)

**Predecessors:** phase 1 (`2026-08-14-ingestion-phase1-truth-and-safety.md`) and phase 2 (`2026-08-15-ingestion-phase2-ia-split.md`), both merged. Phase 2's Library/Workspace split is the surface this phase fills in; its deferral list names several items this plan closes.

## Global Constraints

- Backend: `pyright` (bare, run from `backend/`) must be clean — its `tool.pyright.include` covers much of `tests/**`, so test code is strict-checked too. `ruff check --no-cache .` clean. pytest coverage ≥ 85% per package.
- **Never point `DATABASE_URL` at the dev `chili` database when running tests.** `tests/database/test_migrations.py` runs `alembic downgrade base` → `upgrade head`, which empties every app table. `tests/conftest.py` defaults to `…:5432/chili_test`; an explicit env export still wins, so do not set one.
- The backend venv does not exist in a fresh worktree. Create it with:
  `cd backend && uv venv --python 3.12 && uv pip install -e ".[dev,neo4j,qdrant,openai,anthropic,s3,sentence-transformers,analytics,auth,postgres,observability]"`
  The last four extras are not in CLAUDE.md's install line but `pyright` needs them — without `postgres` alone it reports ~230 phantom import errors from Alembic.
- **After ANY frontend-consumed Pydantic change**, regenerate contracts from the repo root:
  `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` then `cd chili_app && npm run codegen:api`. CI fails on drift. Never hand-edit `chili_app/src/lib/api/schema.ts`.
- Frontend: TypeScript **strict is now enabled** (both `tsconfig.app.json` and `tsconfig.node.json`). No `any`, no unused locals. `npm run lint`, `npm run build`, `npm run test:run` all green.
- Frontend wire DTOs import from `chili_app/src/api/contracts.ts` only.
- Cross-module rule: backend modules communicate only through the FastAPI gateway, the agent coordinator, or `shared/`. No ad-hoc cross-module imports.
- External systems stay behind their `protocols.py` + `adapters/` pair. A new read needs a protocol method and an implementation in **every** adapter, in-memory included.
- e2e runs against the full real stack. A mocked subject is not verification.
- **Never silence errors, suppress warnings, or bypass type/lint checks.** Fix structurally.
- Commit after every task, conventional-commit subjects.

## Decisions taken before planning (do not relitigate)

Three questions the spec left open were settled with the user:

1. **`score_runs.catalog_version` is derived, not declared.** The pack declares only `model_version` and `batch_size`. `catalog_version` always comes from `feature_catalog.version`. Reason: `analytics/score_runs/executor.py:123-132` fails a run whose `catalog_version` disagrees with the active `feature_catalog.version`, so a separately-declared value that drifted would fail every run started from the pack default. A config that can invalidate every run it starts is not worth the flexibility, and nothing today wants the two to differ.
2. **The risk-stage fix stops the event, not just the log.** For `RiskInsufficientSignalsError` only: no `AnalysisFailedEvent`, a debug log, and one per-run summary. Every other `RiskError` keeps publishing exactly as now. Reason: a failure event for a legitimate empty state pollutes the event stream and can surface as a failed stage in the runs timeline the workspace now shows.
3. **Scope is full phase 3** — backend changes plus the frontend surfaces that consume them, so nothing lands unused.

## Findings from exploration that change the work

Read these before task 1; each contradicts something a reader would reasonably assume from the spec.

- **The Neo4j `relationship.weight` mismatch appears already fixed.** `graph/adapters/neo4j_adapter.py:404` writes `relationship.weight = row.weight` in the upsert, and 441/459/1081 read it back. The spec's item 6b is likely stale. Task 12 verifies and closes it rather than scheduling a fix; if the mismatch is real, that task reports it and stops.
- **`knowledge_base.delete` is already audited.** `api/routers/knowledgebases.py:483` and `:518` already call `record_knowledge_base_audit_event` on both the 207 and 204 paths. The spec lists it among the actions to add; only `document.upload`, `document.delete` and `records.submit` are actually missing.
- **The Alertable activity needs a repository method that does not exist.** `analytics/metrics/adapters/protocols.py` exposes `load_current_metrics(knowledge_base_id, entity_id)` — every read is entity-scoped, and `_CURRENT_SELECT_SQL` filters on both columns. There is no KB-wide "has any metric" query. Task 2 adds one to the protocol and both adapters.
- **Replace-detection already exists and precheck must reuse it.** `repository.get_document_by_content_hash(kb_id, content_hash)` at `api/routers/knowledgebases.py:916` is exactly what the upload path uses to find a replacement. Precheck must call the same method so the two can never disagree; a second implementation is the defect this task exists to prevent.
- **`GET /config/domain` returns `DomainConfig` itself** (`api/routers/config.py:99`, `response_model=DomainConfig`). Adding a block to the schema exposes it with no separate response model — but it does change the generated frontend contract, so regeneration is required.

## File Structure

```
backend/readiness/models.py                    MOD  ReadinessActivity, ActivityState, response gains `activities`
backend/readiness/service.py                   MOD  activity derivation; optional components stop blocking
backend/analytics/metrics/adapters/protocols.py MOD  + has_metrics(knowledge_base_id)
backend/analytics/metrics/adapters/postgres.py  MOD  implement it
backend/analytics/metrics/adapters/in_memory.py MOD  implement it
backend/api/routers/readiness.py               MOD  pass the metric reader through
backend/api/dependencies.py                    MOD  wire the metric reader into ReadinessService

backend/api/contracts.py                       MOD  DocumentPrecheckRequest/Response, KnowledgeBaseDeleteReport
backend/api/routers/knowledgebases.py          MOD  precheck endpoint; 207 response_model; upload+delete audit rows
backend/api/routers/records.py                 MOD  records.submit audit rows

backend/config/schema.py                       MOD  ScoreRunDefaultsConfig + DomainConfig.score_runs
backend/config/defaults/*.yaml                 MOD  declare score_runs where the pack has a risk model
backend/agent/coordinator.py                   MOD  RiskInsufficientSignalsError → debug + per-run summary, no event

backend/tests/readiness/test_activities.py     NEW
backend/tests/api/test_document_precheck.py    NEW
backend/tests/api/test_ingestion_audit.py      NEW
backend/tests/config/test_score_run_defaults.py NEW
backend/tests/agent/test_risk_stage_noise.py   NEW

chili_app/src/components/layout/WorkspaceControl.tsx   MOD  activity summary chip replaces binary Ready/Blocked
chili_app/src/features/kb/overview/ActivityRows.tsx    NEW  per-activity states with reasons
chili_app/src/features/kb/overview/OverviewSection.tsx MOD  render ActivityRows
chili_app/src/api/knowledgebases.ts                    MOD  usePrecheckDocuments
chili_app/src/features/kb/add-data/ConfirmUpload.tsx   NEW  confirm stage with replace warnings
chili_app/src/features/kb/add-data/useDocumentsFlow.tsx MOD  route submit through confirm
chili_app/src/features/kb/runs/RunsSection.tsx         MOD  score-run params from config; delete hardcoded fallbacks
chili_app/src/features/kb/settings/SettingsSection.tsx MOD  207 cleanup report + Retry cleanup
chili_app/e2e/kb-activities.spec.ts                    NEW
chili_app/e2e/kb-replace-warning.spec.ts               NEW
```

---

### Task 1: A knowledge base can say what it is able to do

The readiness aggregate answers "is this ready" with one boolean, which is why a knowledge base with no connectors — a normal state for manual upload — has been reading as Blocked forever. Replace it with four activity states that each answer a question the user actually has.

**Files:**
- Modify: `backend/readiness/models.py`
- Test: `backend/tests/readiness/test_activity_models.py` (create)

**Interfaces:**
- Produces:
  - `ActivityState = Literal["ready", "not_ready", "not_configured", "failed"]`
  - `ActivityId = Literal["queryable", "alertable", "scorable", "auto_fed"]`
  - `ReadinessActivity(BaseModel)` — `id: ActivityId`, `label: str`, `state: ActivityState`, `summary: str`, `reasons: list[ReadinessIssue]` (default empty)
  - `ReadinessResponse.activities: list[ReadinessActivity]` (default empty)
- `ReadinessResponse.ready`, `components`, `blockers`, `warnings` all keep their current shapes and names — task 2 changes what fills them, task 3 changes what `ready` means.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/readiness/test_activity_models.py
"""The activity vocabulary a knowledge base uses to describe itself."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from readiness.models import ReadinessActivity, ReadinessIssue


def test_an_activity_carries_its_state_and_a_human_summary() -> None:
    activity = ReadinessActivity(
        id="queryable",
        label="Queryable",
        state="ready",
        summary="53 entities are available to investigate.",
    )

    assert activity.state == "ready"
    assert activity.reasons == []


def test_an_activity_can_explain_why_it_is_not_available() -> None:
    activity = ReadinessActivity(
        id="scorable",
        label="Scorable",
        state="not_ready",
        summary="Score runs need ingested entities.",
        reasons=[
            ReadinessIssue(
                component="score_runs",
                code="no_entities",
                message="This knowledge base has no entities yet.",
                action="Add documents or records.",
            )
        ],
    )

    assert activity.reasons[0].code == "no_entities"


def test_not_configured_is_a_state_of_its_own() -> None:
    # The whole point of the recomposition: optional-and-absent is not a
    # failure, and must not be representable as one by accident.
    activity = ReadinessActivity(
        id="auto_fed",
        label="Auto-fed",
        state="not_configured",
        summary="No connectors are registered.",
    )

    assert activity.state == "not_configured"


def test_an_unknown_state_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReadinessActivity(
            id="queryable",
            label="Queryable",
            state="blocked",  # type: ignore[arg-type]
            summary="…",
        )


def test_an_unknown_activity_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReadinessActivity(
            id="exportable",  # type: ignore[arg-type]
            label="Exportable",
            state="ready",
            summary="…",
        )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/readiness/test_activity_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'ReadinessActivity'`.

- [ ] **Step 3: Add the models**

In `backend/readiness/models.py`, after `ReadinessComponent`:

```python
ActivityState: TypeAlias = Literal["ready", "not_ready", "not_configured", "failed"]
ActivityId: TypeAlias = Literal["queryable", "alertable", "scorable", "auto_fed"]


class ReadinessActivity(BaseModel):
    """What a knowledge base can currently do, and why it cannot.

    Deliberately separate from `ReadinessComponent`: a component describes a
    subsystem's health, an activity describes a thing the user wants to do.
    `not_configured` exists so that optional setup a user never asked for —
    connectors, most often — stops presenting as a blocker.
    """

    id: ActivityId
    label: str = Field(min_length=1)
    state: ActivityState
    summary: str = Field(min_length=1)
    reasons: list[ReadinessIssue] = Field(
        default_factory=lambda: cast(list[ReadinessIssue], [])
    )
```

Add `activities` to `ReadinessResponse`, after `components`:

```python
    activities: list[ReadinessActivity] = Field(
        default_factory=lambda: cast(list[ReadinessActivity], [])
    )
```

Export `ActivityId`, `ActivityState` and `ReadinessActivity` from `__all__`, and re-export from `backend/readiness/__init__.py` alongside the existing names.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/readiness/test_activity_models.py -q`
Expected: PASS, 5 cases.

- [ ] **Step 5: Commit**

```bash
cd backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
git add backend/readiness/models.py backend/readiness/__init__.py backend/tests/readiness/test_activity_models.py
git commit -m "feat(readiness): add the per-activity vocabulary"
```

---

### Task 2: Ask whether a knowledge base has any metrics at all

The Alertable activity needs to know whether monitoring has ever evaluated a metric for a knowledge base. Every existing read is entity-scoped, so this is a genuinely new question and needs a protocol method plus an implementation in each adapter.

**Files:**
- Modify: `backend/analytics/metrics/adapters/protocols.py`
- Modify: `backend/analytics/metrics/adapters/postgres.py`
- Modify: `backend/analytics/metrics/adapters/in_memory.py`
- Test: `backend/tests/analytics/metrics/test_has_metrics.py` (create)

**Interfaces:**
- Produces: `EntityMetricRepository.has_metrics(knowledge_base_id: str) -> bool` on the protocol and both adapters.

Why a boolean rather than a count: the only question anyone has is "can alerts fire here", and returning a count invites a caller to render it as a total, which it is not — `entity_metrics_current` holds one row per (entity, metric), not per evaluation.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/analytics/metrics/test_has_metrics.py
"""Whether a knowledge base has had any metric evaluated, at all."""

from __future__ import annotations

from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.models import EntityMetricSample


def _sample(knowledge_base_id: str, entity_id: str) -> EntityMetricSample:
    # `observed_at` defaults to now; `correlation_id` is required.
    return EntityMetricSample(
        knowledge_base_id=knowledge_base_id,
        entity_id=entity_id,
        metric_name="claim_amount",
        value=1.0,
        correlation_id="corr-1",
    )


def test_a_knowledge_base_with_no_metrics_reports_false() -> None:
    store = InMemoryEntityMetricRepository()

    assert store.has_metrics("kb-empty") is False


def test_one_recorded_metric_is_enough() -> None:
    store = InMemoryEntityMetricRepository()
    store.record_metrics([_sample("kb-1", "e-1")])

    assert store.has_metrics("kb-1") is True


def test_metrics_are_scoped_to_their_knowledge_base() -> None:
    # The predicate drives a per-KB activity state; leaking across knowledge
    # bases would tell an empty corpus that its alerts can fire.
    store = InMemoryEntityMetricRepository()
    store.record_metrics([_sample("kb-1", "e-1")])

    assert store.has_metrics("kb-2") is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/metrics/test_has_metrics.py -q`
Expected: FAIL — `AttributeError: 'InMemoryEntityMetricRepository' object has no attribute 'has_metrics'`.

- [ ] **Step 3: Add the protocol method and both implementations**

Protocol (`adapters/protocols.py`), alongside `load_current_metrics`:

```python
    def has_metrics(self, knowledge_base_id: str) -> bool:
        """Whether any metric has been recorded for this knowledge base.

        Answers "can alerts fire here" for the readiness aggregate. Deliberately
        a boolean: `entity_metrics_current` holds one row per (entity, metric),
        so a count would be a number no caller could correctly label.
        """
        ...
```

Postgres (`adapters/postgres.py`) — add the SQL beside the other statements and implement with an existence probe rather than a count:

```python
_CURRENT_EXISTS_SQL = """
    SELECT 1
    FROM entity_metrics_current
    WHERE knowledge_base_id = %s
    LIMIT 1
"""
```

In-memory (`adapters/in_memory.py`) — match however that store keys its rows; return whether any recorded sample carries the knowledge base id.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/analytics/metrics/test_has_metrics.py -q`
Expected: PASS, 3 cases.

Then run the module's existing tests to confirm nothing regressed:
Run: `cd backend && .venv/bin/pytest tests/analytics/metrics -q`

- [ ] **Step 5: Commit**

```bash
cd backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
git add backend/analytics/metrics backend/tests/analytics/metrics/test_has_metrics.py
git commit -m "feat(metrics): add a knowledge-base-wide has_metrics probe"
```

---

### Task 3: Derive the four activities, and stop optional absence from blocking

This is the substance of the recomposition. Four activities, each with an honest predicate, and the component blockers that only ever meant "you have not set this up" reclassified so they can no longer make a knowledge base look broken.

**Files:**
- Modify: `backend/readiness/service.py`
- Modify: `backend/api/dependencies.py` (wire the metric store into `ReadinessService`)
- Modify: `backend/api/routers/readiness.py` if it constructs the service directly
- Test: `backend/tests/readiness/test_activities.py` (create)
- Modify: `backend/tests/readiness/` existing tests that assert `ready` or blocker contents

**Interfaces:**
- Consumes: `ReadinessActivity` (task 1), `EntityMetricRepository.has_metrics` (task 2).
- Produces: `ReadinessService.__init__` gains a keyword-only `entity_metric_repository: EntityMetricRepository`. `get_readiness` fills `activities`.

**The four predicates, exactly:**

| Activity | `ready` when | `not_configured` when | `failed` when |
|---|---|---|---|
| `queryable` | `entity_count > 0` | never | never |
| `alertable` | `entity_metric_repository.has_metrics(kb)` | no metrics recorded | never |
| `scorable` | `entity_count > 0` and `feature_catalog.version` resolves | catalog has no features | never |
| `auto_fed` | ≥1 connector whose latest run completed | no connectors registered | ≥1 connector whose latest run failed |

Everything not `ready`, `not_configured` or `failed` is `not_ready`.

Note `queryable` and `alertable` have no `failed` state: an empty corpus is not a broken one. Only `auto_fed` can fail, because only a connector can be configured *and* broken.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/readiness/test_activities.py
"""What a knowledge base reports it can do, and why it cannot."""

from __future__ import annotations

from readiness.models import ReadinessActivity, ReadinessResponse


def _activity(response: ReadinessResponse, activity_id: str) -> ReadinessActivity:
    match = next((item for item in response.activities if item.id == activity_id), None)
    assert match is not None, f"no '{activity_id}' activity in {response.activities}"
    return match


def test_an_empty_knowledge_base_is_not_queryable_but_is_not_broken(
    readiness_service_factory,
) -> None:
    service = readiness_service_factory(entity_count=0)

    response = service.get_readiness("kb-1")

    assert _activity(response, "queryable").state == "not_ready"
    assert response.ready is False


def test_entities_make_a_knowledge_base_queryable(readiness_service_factory) -> None:
    service = readiness_service_factory(entity_count=53)

    response = service.get_readiness("kb-1")

    assert _activity(response, "queryable").state == "ready"


def test_no_connectors_is_not_configured_rather_than_blocked(
    readiness_service_factory,
) -> None:
    # The regression this whole recomposition exists to prevent: a manually
    # fed knowledge base read as Blocked forever because it had no connectors
    # it was never going to have.
    service = readiness_service_factory(entity_count=53, connectors=[])

    response = service.get_readiness("kb-1")

    assert _activity(response, "auto_fed").state == "not_configured"
    assert all(blocker.code != "no_connectors" for blocker in response.blockers)


def test_a_failed_connector_sync_is_a_genuine_failure(
    readiness_service_factory,
) -> None:
    service = readiness_service_factory(
        entity_count=53,
        connectors=[("conn-1", "failed")],
    )

    response = service.get_readiness("kb-1")

    auto_fed = _activity(response, "auto_fed")
    assert auto_fed.state == "failed"
    assert auto_fed.reasons, "a failed activity must say which connector failed"


def test_alertable_follows_whether_any_metric_has_been_evaluated(
    readiness_service_factory,
) -> None:
    without = readiness_service_factory(entity_count=53, has_metrics=False)
    with_metrics = readiness_service_factory(entity_count=53, has_metrics=True)

    assert _activity(without.get_readiness("kb-1"), "alertable").state == "not_configured"
    assert _activity(with_metrics.get_readiness("kb-1"), "alertable").state == "ready"


def test_ready_means_no_failure_and_at_least_one_activity_available(
    readiness_service_factory,
) -> None:
    # A knowledge base with entities is useful even with nothing else set up.
    service = readiness_service_factory(entity_count=53, connectors=[], has_metrics=False)

    response = service.get_readiness("kb-1")

    assert response.ready is True


def test_a_failed_activity_makes_the_knowledge_base_not_ready(
    readiness_service_factory,
) -> None:
    service = readiness_service_factory(
        entity_count=53,
        connectors=[("conn-1", "failed")],
    )

    assert service.get_readiness("kb-1").ready is False


def test_missing_workflows_and_capabilities_no_longer_block(
    readiness_service_factory,
) -> None:
    service = readiness_service_factory(
        entity_count=53,
        workflow_definitions=[],
        capabilities=[],
    )

    response = service.get_readiness("kb-1")

    codes = {blocker.code for blocker in response.blockers}
    assert "no_workflows" not in codes
    assert "no_capabilities" not in codes
```

Write a `readiness_service_factory` fixture in `backend/tests/readiness/conftest.py` (create it if absent) that builds a `ReadinessService` over in-memory doubles, with keyword defaults for `entity_count`, `connectors`, `has_metrics`, `workflow_definitions` and `capabilities`. Read the existing readiness tests first and reuse their doubles rather than writing new ones.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/readiness/test_activities.py -q`
Expected: FAIL — `activities` is empty, so `_activity` asserts.

- [ ] **Step 3: Implement the derivation**

In `backend/readiness/service.py`:

1. Accept the metric store: add `entity_metric_repository: EntityMetricRepository` to `__init__` (keyword-only, like its siblings) and store it. Add the domain config or feature catalog version the `scorable` predicate needs — read how `active_domain_name` is already threaded and follow the same route rather than importing config directly.

2. Reclassify the three optional codes. `no_connectors`, `no_workflows` and `no_capabilities` move from `blockers` to a new `not_configured` classification held on the component. The simplest change that keeps `ReadinessComponent`'s shape: keep building those issues, but append them to `warnings` rather than `blockers`, and let the activity layer carry the `not_configured` state. Do not delete the issues — their `message` and `action` are what the Overview rows render.

3. Build the activities from the table above and set `response.activities`.

4. Change `ready` to: `not any(activity.state == "failed" for activity in activities) and any(activity.state == "ready" for activity in activities)`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/readiness -q`
Expected: PASS. Existing readiness tests that assert the old `ready` semantics or blocker membership will fail — those are the semantics this task deliberately changes. Update each to the new expectation and say so in your report; do not delete one.

- [ ] **Step 5: Regenerate the frontend contract**

From the repo root:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && npm run build
```

The frontend does not read `activities` yet — that is task 9 — but the contract must not drift.

- [ ] **Step 6: Commit**

```bash
cd backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright && .venv/bin/pytest tests/readiness -q
git add backend/readiness backend/api/dependencies.py backend/api/routers/readiness.py backend/tests/readiness chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(readiness): report per-activity states instead of one binary flag"
```

---

### Task 4: Tell the analyst what an upload will replace, before they submit

Uploading a file whose content already exists silently replaces the existing document and rebuilds its graph artifacts. That is correct behaviour and completely invisible. The endpoint here answers the question the confirm stage needs to ask.

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/routers/knowledgebases.py`
- Test: `backend/tests/api/test_document_precheck.py` (create)

**Interfaces:**
- Produces:
  - `DocumentPrecheckRequest` — `files: list[DocumentPrecheckItem]` where an item is `filename: str` + `content_hash: str` (sha256 hex).
  - `DocumentPrecheckResponse` — `items: list[DocumentPrecheckResult]` where a result is `filename: str`, `content_hash: str`, `replaces_document_id: str | None`, `replaces_filename: str | None`.
  - `POST /knowledgebases/{knowledge_base_id}/documents/precheck`, `require_role("analyst")` — same role as upload, because it reveals what the knowledge base contains.

**It must reuse `repository.get_document_by_content_hash`** — the same call the upload path makes at `api/routers/knowledgebases.py:916`. A second implementation of "what will this replace" is exactly the defect this endpoint exists to prevent.

Precheck is advisory: state can change between precheck and upload, and the upload path re-resolves the replacement itself. Say so in the endpoint docstring so nobody later "optimises" the upload path to trust a precheck result.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_document_precheck.py
"""Precheck answers what an upload would replace, without uploading."""

from __future__ import annotations

from hashlib import sha256


def test_an_unseen_hash_replaces_nothing(client, seeded_knowledge_base) -> None:
    digest = sha256(b"never seen before").hexdigest()

    response = client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents/precheck",
        json={"files": [{"filename": "new.txt", "content_hash": digest}]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["replaces_document_id"] is None
    assert item["replaces_filename"] is None


def test_a_known_hash_names_the_document_it_would_replace(
    client, seeded_knowledge_base, existing_document
) -> None:
    response = client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents/precheck",
        json={
            "files": [
                {
                    "filename": "renamed-copy.txt",
                    "content_hash": existing_document.content_hash,
                }
            ]
        },
    )

    item = response.json()["items"][0]
    assert item["replaces_document_id"] == existing_document.id
    # The analyst is warned by the name they will recognise, which is the
    # stored document's — not the name they happen to be uploading under.
    assert item["replaces_filename"] == existing_document.filename


def test_precheck_answers_per_file_and_preserves_order(
    client, seeded_knowledge_base, existing_document
) -> None:
    unseen = sha256(b"unseen").hexdigest()

    response = client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents/precheck",
        json={
            "files": [
                {"filename": "a.txt", "content_hash": unseen},
                {"filename": "b.txt", "content_hash": existing_document.content_hash},
            ]
        },
    )

    items = response.json()["items"]
    assert [item["filename"] for item in items] == ["a.txt", "b.txt"]
    assert items[0]["replaces_document_id"] is None
    assert items[1]["replaces_document_id"] == existing_document.id


def test_precheck_changes_nothing(
    client, seeded_knowledge_base, existing_document
) -> None:
    # It is a question, not an action: the document it names must still be
    # there afterwards, untouched.
    client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents/precheck",
        json={
            "files": [
                {"filename": "x.txt", "content_hash": existing_document.content_hash}
            ]
        },
    )

    listing = client.get(f"/knowledgebases/{seeded_knowledge_base.id}/documents")
    assert any(doc["id"] == existing_document.id for doc in listing.json()["items"])


def test_an_unknown_knowledge_base_is_a_404(client) -> None:
    digest = sha256(b"x").hexdigest()

    response = client.post(
        "/knowledgebases/kb-does-not-exist/documents/precheck",
        json={"files": [{"filename": "a.txt", "content_hash": digest}]},
    )

    assert response.status_code == 404


def test_an_empty_file_list_is_rejected(client, seeded_knowledge_base) -> None:
    response = client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents/precheck",
        json={"files": []},
    )

    assert response.status_code == 422
```

Read `backend/tests/api/` for the existing client and knowledge-base fixtures and reuse them; add an `existing_document` fixture only if none exists.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_document_precheck.py -q`
Expected: FAIL — 404 on every case, the route does not exist.

- [ ] **Step 3: Add the contracts and the endpoint**

Contracts, beside the other document models:

```python
class DocumentPrecheckItem(BaseModel):
    """One file an analyst is about to upload."""

    filename: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)


class DocumentPrecheckRequest(BaseModel):
    files: list[DocumentPrecheckItem] = Field(min_length=1)


class DocumentPrecheckResult(BaseModel):
    filename: str
    content_hash: str
    replaces_document_id: str | None = None
    replaces_filename: str | None = None


class DocumentPrecheckResponse(BaseModel):
    items: list[DocumentPrecheckResult]
```

Endpoint in `api/routers/knowledgebases.py`, near the upload route, with `require_role("analyst")`, a 404 when the knowledge base is unknown (match how the neighbouring routes raise it), and a body that maps each item through `repository.get_document_by_content_hash`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/api/test_document_precheck.py -q`
Expected: PASS, 6 cases.

- [ ] **Step 5: Regenerate contracts, then commit**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && npm run build
cd ../backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
git add backend/api backend/tests/api/test_document_precheck.py chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(api): add a document precheck endpoint for replace-on-upload"
```

---

### Task 5: Give the 207 partial-delete report a contract

`DELETE /knowledgebases/{id}` already returns `207 Multi-Status` with a per-step cleanup report when a step fails, and the API client already hands that body back. But the route returns a bare `JSONResponse` with no `response_model`, so the shape is absent from the OpenAPI schema and no generated type exists — which is exactly why phase 2 could not build the Settings UI for it.

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/routers/knowledgebases.py`
- Test: `backend/tests/api/test_knowledge_base_delete_report.py` (create)

**Interfaces:**
- Produces:
  - `KnowledgeBaseDeletionStep` — `step: str`, `status: Literal["succeeded", "failed"]`, `error: str | None = None`
  - `KnowledgeBaseDeletionReport` — `knowledge_base_id: str`, `pending_cleanup: bool`, `steps: list[KnowledgeBaseDeletionStep]`
  - The 207 branch returns that model; the 204 branch is unchanged.

Declare it via `responses={207: {"model": KnowledgeBaseDeletionReport}}` on the route decorator so the schema carries it without changing the 204 success path. Read how other routes in this file declare non-default responses and match that.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_knowledge_base_delete_report.py
"""The partial-delete report is a typed contract, not an untyped dict."""

from __future__ import annotations


def test_a_clean_delete_is_still_204(client, seeded_knowledge_base) -> None:
    response = client.delete(f"/knowledgebases/{seeded_knowledge_base.id}")

    assert response.status_code == 204
    assert response.content == b""


def test_a_partial_delete_reports_each_step(
    client, seeded_knowledge_base, failing_cleanup_step
) -> None:
    response = client.delete(f"/knowledgebases/{seeded_knowledge_base.id}")

    assert response.status_code == 207
    body = response.json()
    assert body["knowledge_base_id"] == seeded_knowledge_base.id
    assert body["pending_cleanup"] is True
    failed = [step for step in body["steps"] if step["status"] == "failed"]
    assert failed, "a partial delete must name the step that failed"
    assert failed[0]["error"], "a failed step must carry its error"


def test_the_report_shape_is_in_the_openapi_schema(client) -> None:
    # The reason this task exists: without a declared response model there is
    # no generated frontend type, so the UI cannot render the report.
    schema = client.get("/openapi.json").json()
    assert "KnowledgeBaseDeletionReport" in schema["components"]["schemas"]
```

Write `failing_cleanup_step` as a fixture that makes exactly one cleanup step raise — read `api/_kb_cleanup.py`'s `kb_deletion_steps` to find the seam, and monkeypatch the narrowest thing that works.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_knowledge_base_delete_report.py -q`
Expected: the schema case FAILS — the model does not exist.

- [ ] **Step 3: Add the models and declare the response**

Build the 207 body through the new model instead of a dict literal. The existing keys (`knowledge_base_id`, `pending_cleanup`, `steps`) stay exactly as they are — this task types the shape, it does not change it. Verify against `api/routers/knowledgebases.py:502` that no key is renamed.

- [ ] **Step 4: Run the tests, regenerate contracts, commit**

```bash
cd backend && .venv/bin/pytest tests/api/test_knowledge_base_delete_report.py -q
cd .. && PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && npm run build
cd ../backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
git add backend/api backend/tests/api/test_knowledge_base_delete_report.py chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(api): give the partial-delete report a response model"
```

---

### Task 6: Score-run parameters come from the pack, not a frontend constant

`cms-fraud-features-v1` and `risk-linear-v1` are hardcoded in the React tree. The catalog version is already knowable from config; the model version and batch size are not configured anywhere.

**Files:**
- Modify: `backend/config/schema.py`
- Modify: `backend/config/defaults/medicare_fraud.yaml`, `medicare_fraud_cms_desynpuf.yaml` (and the others only if they have a risk model)
- Test: `backend/tests/config/test_score_run_defaults.py` (create)

**Interfaces:**
- Produces:
  - `ScoreRunDefaultsConfig` — `model_version: str = Field(min_length=1)`, `batch_size: int = Field(default=100, gt=0, le=1000)`
  - `DomainConfig.score_runs: ScoreRunDefaultsConfig | None = None`
  - A read-only derived property or helper exposing the effective catalog version from `feature_catalog.version` — **`catalog_version` is not a declarable field.** See the decision above: the executor fails any run whose catalog version disagrees with the active catalog, so a pack that could declare a different one could configure runs that always fail.

`batch_size`'s bounds mirror `ScoreRunStartRequest.batch_size` (`gt=0, le=1000`) so a pack cannot configure a default the API would reject.

`score_runs` is optional: a pack with no risk model has nothing to declare, and the UI falls back to disabling the control with a reason rather than inventing a version.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/config/test_score_run_defaults.py
"""Score-run defaults are declared by the pack, except the catalog version."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import DomainConfig, ScoreRunDefaultsConfig


def test_a_pack_may_declare_a_model_version_and_batch_size() -> None:
    defaults = ScoreRunDefaultsConfig(model_version="risk-linear-v1", batch_size=250)

    assert defaults.model_version == "risk-linear-v1"
    assert defaults.batch_size == 250


def test_batch_size_defaults_to_the_api_default() -> None:
    assert ScoreRunDefaultsConfig(model_version="risk-linear-v1").batch_size == 100


def test_a_batch_size_the_api_would_reject_is_rejected_here() -> None:
    # Bounds mirror ScoreRunStartRequest so a pack cannot configure a default
    # that every run start would 422 on.
    with pytest.raises(ValidationError):
        ScoreRunDefaultsConfig(model_version="risk-linear-v1", batch_size=1001)
    with pytest.raises(ValidationError):
        ScoreRunDefaultsConfig(model_version="risk-linear-v1", batch_size=0)


def test_catalog_version_is_not_declarable(minimal_domain_config_dict) -> None:
    # It is derived from feature_catalog.version. Allowing a pack to declare a
    # second value invites configuring runs the executor fails on sight.
    payload = {
        **minimal_domain_config_dict,
        "score_runs": {"model_version": "risk-linear-v1", "catalog_version": "other-v9"},
    }

    with pytest.raises(ValidationError):
        DomainConfig.model_validate(payload)


def test_score_runs_is_optional(minimal_domain_config_dict) -> None:
    config = DomainConfig.model_validate(minimal_domain_config_dict)

    assert config.score_runs is None
```

`test_catalog_version_is_not_declarable` requires the model to forbid extra keys. Check whether `DomainConfig`'s models already set `extra="forbid"`; if they do not, set it on `ScoreRunDefaultsConfig` only, and say so in your report rather than changing the whole config's strictness.

Reuse or add a `minimal_domain_config_dict` fixture from the existing `backend/tests/config/` suite.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/config/test_score_run_defaults.py -q`
Expected: FAIL — `ImportError: cannot import name 'ScoreRunDefaultsConfig'`.

- [ ] **Step 3: Add the config model and declare it in the packs**

Add `ScoreRunDefaultsConfig` near `FeatureCatalogConfig` in `config/schema.py`, and the optional field on `DomainConfig`.

In `backend/config/defaults/medicare_fraud.yaml` and `medicare_fraud_cms_desynpuf.yaml`, add:

```yaml
score_runs:
  model_version: risk-linear-v1
  batch_size: 100
```

Do **not** add it to `food_supply_chain.yaml` or `department_air_force_housing.yaml` unless those packs actually run risk scoring — an unused declaration is a claim the pack does not support.

- [ ] **Step 4: Run the tests, regenerate contracts, commit**

`GET /config/domain` returns `DomainConfig` directly, so this changes the frontend contract.

```bash
cd backend && .venv/bin/pytest tests/config -q
cd .. && PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && npm run build
cd ../backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
git add backend/config backend/tests/config chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(config): let a domain pack declare its score-run defaults"
```

---

### Task 7: Ingestion writes audit rows

A UAT ruling made ingestion material, which means it belongs in the append-only ledger. Three actions are missing; `knowledge_base.delete` is already there and needs no work.

**Files:**
- Modify: `backend/api/routers/knowledgebases.py` (upload, document delete)
- Modify: `backend/api/routers/records.py` (file upload, push)
- Test: `backend/tests/api/test_ingestion_audit.py` (create)

**Interfaces:**
- Consumes: `record_knowledge_base_audit_event` from `api/dependencies.py` — the same helper the create and delete paths already use. Do not write a second one.
- Produces: audit rows with actions `document.upload`, `document.delete`, `records.submit`.

**What goes in the row.** The helper's docstring says "without raw document data", and that constraint is the point: an audit row records *that* something happened and to what, never the content. Filenames, counts, content hashes and document ids are fine; file bytes, parsed rows and record field values are not.

Each action's `metadata` should carry what an investigator would need to reconstruct the event without the payload:
- `document.upload` — document count, filenames, total bytes, and how many replaced an existing document.
- `document.delete` — the document id and filename.
- `records.submit` — feed name, source (`file_upload` or `api_push`), and the receipt's accepted/duplicate/rejected/suppressed counts.

**Failure must not break ingestion.** `AuditLogService.record` already isolates write failures — confirm that by reading it before relying on it, and say in your report what you found.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_ingestion_audit.py
"""Ingestion is material, so it lands in the audit ledger."""

from __future__ import annotations


def test_uploading_documents_writes_an_audit_row(
    client, seeded_knowledge_base, audit_events
) -> None:
    client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents",
        files=[("files", ("a.txt", b"hello", "text/plain"))],
    )

    row = audit_events.latest(action="document.upload")
    assert row is not None
    assert row.knowledge_base_id == seeded_knowledge_base.id
    assert row.metadata["document_count"] == 1
    assert "a.txt" in row.metadata["filenames"]


def test_the_upload_row_records_no_document_content(
    client, seeded_knowledge_base, audit_events
) -> None:
    # The ledger says what happened, never what was in the file.
    secret = b"patient-identifiable-content"
    client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents",
        files=[("files", ("a.txt", secret, "text/plain"))],
    )

    row = audit_events.latest(action="document.upload")
    assert secret.decode() not in str(row.model_dump())


def test_deleting_a_document_writes_an_audit_row(
    client, seeded_knowledge_base, existing_document, audit_events
) -> None:
    client.delete(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents/{existing_document.id}"
    )

    row = audit_events.latest(action="document.delete")
    assert row is not None
    assert row.metadata["document_id"] == existing_document.id


def test_submitting_records_writes_an_audit_row_with_its_receipt_counts(
    client, seeded_knowledge_base, audit_events
) -> None:
    client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/records",
        json={"feed_name": "carrier_claims_a", "rows": [{"CLM_ID": "1"}]},
    )

    row = audit_events.latest(action="records.submit")
    assert row is not None
    assert row.metadata["feed_name"] == "carrier_claims_a"
    assert "accepted_count" in row.metadata


def test_a_failing_audit_write_does_not_fail_the_upload(
    client, seeded_knowledge_base, broken_audit_service
) -> None:
    # The ledger is a record of ingestion, not a gate on it.
    response = client.post(
        f"/knowledgebases/{seeded_knowledge_base.id}/documents",
        files=[("files", ("a.txt", b"hello", "text/plain"))],
    )

    assert response.status_code < 400
```

Read the records router first and match the real request shape and feed name for the test pack; the JSON above is illustrative. Write `audit_events` as a fixture exposing the recorded rows, and `broken_audit_service` as one whose repository raises.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_ingestion_audit.py -q`
Expected: FAIL — no rows recorded for the three new actions.

- [ ] **Step 3: Add the audit calls**

At each site, call `record_knowledge_base_audit_event` after the action succeeds, with the actor from the route's existing `require_role` dependency. The upload and records routes currently take their role as a bare `dependencies=[...]` entry — change those to a named `user: User = Depends(require_role("analyst"))` parameter so the actor is available, exactly as `create_knowledge_base` at `:234` already does.

- [ ] **Step 4: Run the tests and the neighbouring suites**

```bash
cd backend && .venv/bin/pytest tests/api/test_ingestion_audit.py tests/api/test_knowledgebases.py tests/api/test_records.py -q
```

- [ ] **Step 5: Commit**

```bash
cd backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
git add backend/api backend/tests/api/test_ingestion_audit.py
git commit -m "feat(audit): record document upload, document delete and records submit"
```

---

### Task 8: Stop reporting an empty risk profile as an analytics failure

A knowledge base with no registered risk profile is a legitimate, common state. Today every entity in it produces an `AnalysisFailedEvent` and a `logger.warning`, so a normal ingestion run looks like a cascade of failures — and the runs timeline the workspace now shows will render it that way.

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_risk_stage_noise.py` (create)

**Interfaces:**
- `_run_risk_stage` distinguishes `RiskInsufficientSignalsError` from every other `RiskError`. The former: no event, `logger.debug`, and a counter the caller summarises once per run. The latter: unchanged — event published, warning logged.

`RiskInsufficientSignalsError` is raised at `analytics/risk/service.py:63-64` when a profile has fewer than two signals, which is precisely "nothing has been registered for this entity". It is its own exception type, so the distinction needs no string matching.

The per-run summary belongs where the stage loop can count — find where `_run_risk_stage` is called (`agent/coordinator.py:2336`) and emit one `logger.info` after the loop naming how many entities were skipped for want of signals. One line per run, not per entity.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/agent/test_risk_stage_noise.py
"""A knowledge base with no risk profile is not a failing one."""

from __future__ import annotations

import logging


def test_insufficient_signals_publishes_no_failure_event(
    risk_stage_harness, caplog
) -> None:
    harness = risk_stage_harness(raises="insufficient_signals")

    harness.run()

    assert harness.published_analysis_failed == [], (
        "an unregistered risk profile is an empty state, not a failure"
    )


def test_insufficient_signals_logs_at_debug_not_warning(
    risk_stage_harness, caplog
) -> None:
    harness = risk_stage_harness(raises="insufficient_signals")

    with caplog.at_level(logging.DEBUG):
        harness.run()

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [r for r in caplog.records if r.levelno == logging.DEBUG]


def test_a_real_risk_failure_still_publishes_and_warns(
    risk_stage_harness, caplog
) -> None:
    # The distinction is the whole point: a configuration error is still a
    # failure and must stay as loud as it is today.
    harness = risk_stage_harness(raises="configuration_error")

    with caplog.at_level(logging.DEBUG):
        harness.run()

    assert len(harness.published_analysis_failed) == 1
    assert [r for r in caplog.records if r.levelno == logging.WARNING]


def test_one_summary_line_per_run_not_per_entity(risk_stage_harness, caplog) -> None:
    harness = risk_stage_harness(raises="insufficient_signals", entity_count=25)

    with caplog.at_level(logging.INFO):
        harness.run()

    summaries = [r for r in caplog.records if "skipped" in r.getMessage().lower()]
    assert len(summaries) == 1
    assert "25" in summaries[0].getMessage()
```

Build `risk_stage_harness` over the existing coordinator test doubles — `backend/tests/agent/test_coordinator.py` around line 4421 already constructs exactly this scenario ("This KB has no derived risk signals registered anywhere") and is the right place to borrow from.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/agent/test_risk_stage_noise.py -q`
Expected: FAIL — an event is published and a warning logged.

- [ ] **Step 3: Implement the distinction**

In `_run_risk_stage`, catch `RiskInsufficientSignalsError` before the general `RiskError` handler. Return a value the caller can count — either `None` plus a returned flag, or a small result type; choose whichever fits the existing call site with least disturbance and say which you chose.

Do not broaden the catch. Only `RiskInsufficientSignalsError` changes behaviour.

- [ ] **Step 4: Run the agent suite**

Run: `cd backend && .venv/bin/pytest tests/agent -q`
Expected: PASS. The existing coordinator test at ~4421 asserts today's behaviour for this exact scenario — update it to the new expectation and say so in your report.

- [ ] **Step 5: Commit**

```bash
cd backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
git add backend/agent/coordinator.py backend/tests/agent
git commit -m "fix(agent): stop reporting an unregistered risk profile as a failure"
```

---

### Task 9: The top bar says what the knowledge base can do

`WorkspaceControl` renders "Ready" or "Blocked" from one boolean. With activities available it can say something true and specific instead.

**Files:**
- Modify: `chili_app/src/components/layout/WorkspaceControl.tsx`
- Test: `chili_app/src/components/layout/__tests__/WorkspaceControl.test.tsx` (create or extend)

**Interfaces:**
- Consumes: `KnowledgeBaseReadinessResponse.activities` (task 3, via regenerated contracts).

**The chip's copy, in priority order:**
1. Any activity `failed` → danger tone, e.g. `Connector failed`.
2. No knowledge base selected → `No KB`, unknown tone (unchanged).
3. `queryable` ready → `Queryable · 53 entities`.
4. Nothing ready, nothing failed → `Empty`, default tone.

"Blocked"/danger presentation is reserved for genuine failure. An empty knowledge base is empty, not blocked — that is the regression this whole recomposition exists to fix, and the tone is where it shows.

The existing `<details>` disclosure keeps listing issues; feed it the activities' `reasons` in addition to `blockers`/`warnings` so a `not_configured` activity can explain itself.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/components/layout/__tests__/WorkspaceControl.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { WorkspaceControl } from '../WorkspaceControl'
import type { KnowledgeBaseReadinessResponse } from '../../../api/contracts'

const knowledgeBases = [
  { id: 'kb-1', name: 'Fraud KB', description: '', status: 'ready',
    document_count: 8, entity_count: 53, relationship_count: 21,
    created_at: '2026-08-01T00:00:00Z', updated_at: null, domain: 'medicare_fraud' },
]

function readiness(
  activities: KnowledgeBaseReadinessResponse['activities'],
): KnowledgeBaseReadinessResponse {
  return {
    knowledge_base: { id: 'kb-1', name: 'Fraud KB', domain: 'medicare_fraud',
      status: 'ready', document_count: 8, entity_count: 53,
      relationship_count: 21, created_at: '2026-08-01T00:00:00Z', updated_at: null },
    active_domain_name: 'medicare_fraud',
    ready: true,
    components: {},
    activities,
    blockers: [],
    warnings: [],
  } as KnowledgeBaseReadinessResponse
}

function renderControl(data: KnowledgeBaseReadinessResponse) {
  render(
    <WorkspaceControl
      activeKnowledgeBaseId="kb-1"
      isError={false}
      isLoading={false}
      knowledgeBases={knowledgeBases}
      onSelectKnowledgeBase={vi.fn()}
      readiness={data}
      readinessError={false}
      readinessLoading={false}
    />,
  )
}

describe('WorkspaceControl activity summary', () => {
  it('names what the knowledge base can do, with its entity count', () => {
    renderControl(readiness([
      { id: 'queryable', label: 'Queryable', state: 'ready',
        summary: '53 entities are available to investigate.', reasons: [] },
    ]))

    expect(screen.getByTestId('workspace-readiness-status')).toHaveTextContent(
      'Queryable · 53 entities',
    )
  })

  it('reads Empty, not Blocked, when nothing is set up yet', () => {
    // The regression this replaces: a manually fed knowledge base showed
    // Blocked forever because it had no connectors it was never going to have.
    renderControl(readiness([
      { id: 'queryable', label: 'Queryable', state: 'not_ready', summary: '…', reasons: [] },
      { id: 'auto_fed', label: 'Auto-fed', state: 'not_configured', summary: '…', reasons: [] },
    ]))

    const chip = screen.getByTestId('workspace-readiness-status')
    expect(chip).toHaveTextContent('Empty')
    expect(chip).not.toHaveTextContent('Blocked')
  })

  it('shows danger only for a genuine failure', () => {
    renderControl(readiness([
      { id: 'queryable', label: 'Queryable', state: 'ready', summary: '…', reasons: [] },
      { id: 'auto_fed', label: 'Auto-fed', state: 'failed',
        summary: 'Latest connector sync failed.', reasons: [] },
    ]))

    expect(screen.getByTestId('workspace-readiness-status')).toHaveTextContent(/failed/i)
  })

  it('still says so when no knowledge base is selected', () => {
    render(
      <WorkspaceControl
        activeKnowledgeBaseId={null}
        isError={false}
        isLoading={false}
        knowledgeBases={[]}
        onSelectKnowledgeBase={vi.fn()}
        readiness={undefined}
        readinessError={false}
        readinessLoading={false}
      />,
    )

    expect(screen.getByTestId('workspace-readiness-status')).toHaveTextContent(
      /no knowledge base/i,
    )
  })
})
```

- [ ] **Step 2: Run it to verify it fails, implement, verify it passes**

Run: `cd chili_app && npm run test:run -- src/components/layout/__tests__/WorkspaceControl.test.tsx`

Replace `readinessLabel`/`readinessTone` with activity-driven equivalents. Keep the `data-testid` values — `workspace-control`, `workspace-readiness-status`, `workspace-readiness-details` — the e2e suite locates by them.

- [ ] **Step 3: Commit**

```bash
cd chili_app && npm run lint && npm run build && npm run test:run
git add chili_app/src/components/layout
git commit -m "feat(kb): make the top-bar chip an activity summary"
```

---

### Task 10: Overview explains each activity, and what to do about it

The workspace Overview states the knowledge base's situation in a sentence. Add the per-activity rows underneath, so "not set up" reads as a quiet row with an action rather than an alarm.

**Files:**
- Create: `chili_app/src/features/kb/overview/ActivityRows.tsx`
- Create: `chili_app/src/features/kb/overview/__tests__/ActivityRows.test.tsx`
- Modify: `chili_app/src/features/kb/overview/OverviewSection.tsx`
- Modify: `chili_app/src/features/kb/overview/__tests__/OverviewSection.test.tsx`

**Interfaces:**
- Produces: `ActivityRows` — props `{ activities: ReadinessActivity[] }`.
- `OverviewSection` gains an optional `activities` prop; when absent or empty it renders nothing extra, so the section still works while readiness is loading.

Presentation rules, from spec §3a:
- `ready` — quiet confirmation, no call to action.
- `not_ready` — the reason plus the action that would change it.
- `not_configured` — quiet "not set up" with action text. **No danger tone, no warning icon.**
- `failed` — danger tone, the reason, and the action.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/features/kb/overview/__tests__/ActivityRows.test.tsx
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ActivityRows } from '../ActivityRows'

describe('ActivityRows', () => {
  it('renders one row per activity with its label', () => {
    render(<ActivityRows activities={[
      { id: 'queryable', label: 'Queryable', state: 'ready', summary: 'Ready to investigate.', reasons: [] },
      { id: 'alertable', label: 'Alertable', state: 'not_configured', summary: 'No metrics evaluated yet.', reasons: [] },
    ]} />)

    expect(screen.getByText('Queryable')).toBeInTheDocument()
    expect(screen.getByText('Alertable')).toBeInTheDocument()
  })

  it('presents unconfigured optional setup quietly, not as a problem', () => {
    // UXA: absent optional setup is not a failure, and must not borrow a
    // failure's presentation.
    render(<ActivityRows activities={[
      { id: 'auto_fed', label: 'Auto-fed', state: 'not_configured',
        summary: 'No connectors registered.',
        reasons: [{ component: 'connectors', code: 'no_connectors',
          message: 'No connectors are configured.', action: 'Register a connector.' }] },
    ]} />)

    const row = screen.getByTestId('activity-row-auto_fed')
    expect(row).toHaveAttribute('data-state', 'not_configured')
    expect(within(row).getByText('Register a connector.')).toBeInTheDocument()
    expect(row).not.toHaveAttribute('data-tone', 'danger')
  })

  it('presents a failure as a failure', () => {
    render(<ActivityRows activities={[
      { id: 'auto_fed', label: 'Auto-fed', state: 'failed',
        summary: 'Latest connector sync failed.',
        reasons: [{ component: 'connectors', code: 'connector_sync_failed',
          message: 'Sync failed for conn-1.', action: 'Inspect the sync run.' }] },
    ]} />)

    const row = screen.getByTestId('activity-row-auto_fed')
    expect(row).toHaveAttribute('data-state', 'failed')
    expect(within(row).getByText('Sync failed for conn-1.')).toBeInTheDocument()
  })

  it('renders nothing when there are no activities', () => {
    const { container } = render(<ActivityRows activities={[]} />)

    expect(container).toBeEmptyDOMElement()
  })
})
```

- [ ] **Step 2: Implement and wire into Overview**

`OverviewSection` reads readiness via the existing `useKnowledgeBaseReadiness(knowledgeBaseId)` hook rather than taking it from the workspace context, so the section owns its own query and the header is unaffected.

- [ ] **Step 3: Commit**

```bash
cd chili_app && npm run lint && npm run build && npm run test:run
git add chili_app/src/features/kb/overview
git commit -m "feat(kb): show per-activity states with their actions on Overview"
```

---

### Task 11: Warn before an upload replaces something

With the precheck endpoint in place, the Add-data flow can state consequences before submit instead of after.

**Files:**
- Modify: `chili_app/src/api/knowledgebases.ts`
- Create: `chili_app/src/features/kb/add-data/ConfirmUpload.tsx`
- Create: `chili_app/src/features/kb/add-data/__tests__/ConfirmUpload.test.tsx`
- Modify: `chili_app/src/features/kb/add-data/useDocumentsFlow.tsx`
- Modify: `chili_app/src/features/kb/add-data/__tests__/AddDataSection.test.tsx`

**Interfaces:**
- Produces: `precheckDocuments(kbId, items)` + `usePrecheckDocuments(kbId)` in `api/knowledgebases.ts`; `ConfirmUpload` component.

**Hashing happens in the browser** via `crypto.subtle.digest('SHA-256', buffer)`. It must produce the same lowercase hex the backend's `hashlib.sha256(content).hexdigest()` does — a test asserting a known vector against a known digest is the cheapest way to be sure, and worth having.

The confirm stage renders: N files, the target knowledge base, and one warning line per file that would replace an existing document, naming the **stored** document's filename. If precheck fails, the flow must still allow submit — a precheck outage is not a reason to block ingestion. Say so in a comment.

- [ ] **Step 1: Write the failing tests**

```tsx
// chili_app/src/features/kb/add-data/__tests__/ConfirmUpload.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmUpload, sha256Hex } from '../ConfirmUpload'

const stagedFile = (name: string) => new File(['claim payload'], name, { type: 'text/plain' })

describe('sha256Hex', () => {
  it('matches the digest the backend computes for the same bytes', async () => {
    // Known vector: sha256("abc"). The backend hashes with
    // hashlib.sha256(content).hexdigest(), so a mismatch here would make every
    // precheck answer wrong while looking plausible.
    const digest = await sha256Hex(new File(['abc'], 'a.txt'))

    expect(digest).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    )
  })
})

describe('ConfirmUpload', () => {
  it('states the file count and the target knowledge base', () => {
    render(
      <ConfirmUpload
        files={[stagedFile('a.txt'), stagedFile('b.txt')]}
        knowledgeBaseName="Fraud KB"
        precheck={{ items: [] }}
        precheckFailed={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.getByText(/2 files/i)).toBeInTheDocument()
    expect(screen.getByText(/Fraud KB/)).toBeInTheDocument()
  })

  it('names the stored document an upload would replace', () => {
    // The analyst is warned by the name they will recognise — the one already
    // in the knowledge base, not the name they happen to be uploading under.
    render(
      <ConfirmUpload
        files={[stagedFile('renamed-copy.txt')]}
        knowledgeBaseName="Fraud KB"
        precheck={{
          items: [
            {
              filename: 'renamed-copy.txt',
              content_hash: 'a'.repeat(64),
              replaces_document_id: 'doc-7',
              replaces_filename: 'original-claim.txt',
            },
          ],
        }}
        precheckFailed={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.getByText(/original-claim\.txt/)).toBeInTheDocument()
    expect(screen.getByText(/rebuild/i)).toBeInTheDocument()
  })

  it('shows no warning when nothing would be replaced', () => {
    render(
      <ConfirmUpload
        files={[stagedFile('a.txt')]}
        knowledgeBaseName="Fraud KB"
        precheck={{
          items: [
            {
              filename: 'a.txt',
              content_hash: 'b'.repeat(64),
              replaces_document_id: null,
              replaces_filename: null,
            },
          ],
        }}
        precheckFailed={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('still allows submit when the precheck itself failed', async () => {
    // A precheck outage is not a reason to block ingestion — the upload path
    // re-resolves replacements server-side regardless.
    const onConfirm = vi.fn()
    render(
      <ConfirmUpload
        files={[stagedFile('a.txt')]}
        knowledgeBaseName="Fraud KB"
        precheck={null}
        precheckFailed
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    )

    const confirm = screen.getByRole('button', { name: /upload/i })
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('cancelling returns without submitting', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    render(
      <ConfirmUpload
        files={[stagedFile('a.txt')]}
        knowledgeBaseName="Fraud KB"
        precheck={{ items: [] }}
        precheckFailed={false}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Implement, verify, commit**

```bash
cd chili_app && npm run lint && npm run build && npm run test:run
git add chili_app/src/api/knowledgebases.ts chili_app/src/features/kb/add-data
git commit -m "feat(kb): warn which documents an upload will replace"
```

---

### Task 12: Score-run parameters, run history, and the partial-delete report in the UI

Three small consumers of the backend work, grouped because each is a handful of lines in a section that already exists.

**Files:**
- Modify: `chili_app/src/features/kb/runs/RunsSection.tsx` + its test
- Modify: `chili_app/src/features/kb/settings/SettingsSection.tsx` + its test
- Modify: `chili_app/src/api/knowledgebases.ts` (delete mutation returns the report)

**Three changes:**

1. **Score-run params from config.** `RunsSection` reads `score_runs` from `useDomainConfig()`. The hardcoded `'cms-fraud-features-v1'` and `'risk-linear-v1'` fallbacks are **deleted**. `catalog_version` comes from the config's feature catalog version, `model_version` and `batch_size` from `score_runs`. When a pack declares no `score_runs`, the start button is disabled with the reason "This domain pack declares no score-run model." — the project's disabled-control convention, reason as adjacent text.

2. **Run history.** The existing paginated `useScoreRuns` list already returns more than the one run the section shows (`{ limit: 1 }`). Raise the limit and render the recent runs beneath the active one, each with its status, model version and relative time. No API change.

3. **The partial-delete report.** `useDeleteKnowledgeBase` currently types its result as `void`, discarding a 207 body the client already returns. Type it as `KnowledgeBaseDeletionReport | null` (task 5's model), and have `SettingsSection` render the per-step report with a "Retry cleanup" action that re-invokes the same delete. A 204 keeps its current behaviour exactly.

**Verify before you build item 3:** confirm `apiDelete`/`apiRequest` genuinely returns the parsed 207 body rather than discarding it for a non-204 status. Read `chili_app/src/lib/apiClient.ts`. If it does not, that is a finding — report it rather than working around it.

- [ ] **Step 1: Write the failing tests**

```tsx
// added to chili_app/src/features/kb/runs/__tests__/RunsSection.test.tsx
describe('score-run parameters', () => {
  it('starts a run with the versions the pack declares', async () => {
    renderSection(12, {
      score_runs: { model_version: 'risk-linear-v2', batch_size: 250 },
      feature_catalog: { version: 'cms-fraud-features-v3', features: [] },
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Start score-all' }))

    const body = JSON.parse(String(lastRequest('/score-runs')?.body))
    expect(body.model_version).toBe('risk-linear-v2')
    expect(body.catalog_version).toBe('cms-fraud-features-v3')
    expect(body.batch_size).toBe(250)
  })

  it('disables start and names the reason when the pack declares no score runs', async () => {
    // Deleting the hardcoded fallbacks means a pack without a risk model has
    // no version to invent — so the control says why rather than guessing.
    renderSection(12, { score_runs: null })

    const start = await screen.findByRole('button', { name: 'Start score-all' })
    expect(start).toBeDisabled()
    expect(
      screen.getByText('This domain pack declares no score-run model.'),
    ).toBeInTheDocument()
  })

  it('lists recent runs beneath the active one', async () => {
    renderSection(12, undefined, {
      scoreRuns: [
        { id: 'run-3', status: 'completed', model_version: 'risk-linear-v2' },
        { id: 'run-2', status: 'failed', model_version: 'risk-linear-v1' },
      ],
    })

    const history = await screen.findByRole('list', { name: /score run history/i })
    expect(within(history).getAllByRole('listitem')).toHaveLength(2)
    expect(within(history).getByText('risk-linear-v1')).toBeInTheDocument()
  })
})
```

```tsx
// added to chili_app/src/features/kb/settings/__tests__/SettingsSection.test.tsx
describe('partial delete', () => {
  it('renders the per-step report when cleanup did not finish', async () => {
    deleteResponds(207, {
      knowledge_base_id: 'kb-1',
      pending_cleanup: true,
      steps: [
        { step: 'graph', status: 'succeeded', error: null },
        { step: 'vectors', status: 'failed', error: 'connection refused' },
      ],
    })
    renderSection()

    await confirmDelete('Fraud KB')

    const report = await screen.findByTestId('cleanup-report')
    expect(within(report).getByText('vectors')).toBeInTheDocument()
    expect(within(report).getByText(/connection refused/)).toBeInTheDocument()
  })

  it('offers a retry that re-invokes the delete', async () => {
    deleteResponds(207, {
      knowledge_base_id: 'kb-1',
      pending_cleanup: true,
      steps: [{ step: 'vectors', status: 'failed', error: 'connection refused' }],
    })
    renderSection()
    await confirmDelete('Fraud KB')

    await userEvent.click(await screen.findByRole('button', { name: /retry cleanup/i }))

    expect(deleteRequests()).toHaveLength(2)
  })

  it('a clean 204 delete still just leaves', async () => {
    deleteResponds(204, null)
    const { onDeleted } = renderSection()

    await confirmDelete('Fraud KB')

    await waitFor(() => expect(onDeleted).toHaveBeenCalled())
    expect(screen.queryByTestId('cleanup-report')).not.toBeInTheDocument()
  })
})
```

Read both test files first and match their existing helper names and render signatures — `renderSection`, `deleteRequests` and the fetch stub already exist in some form from phase 2. Extend them rather than introducing parallel helpers; `deleteResponds`, `confirmDelete` and `lastRequest` are the new ones you will need.

- [ ] **Step 2: Implement, verify, commit**

```bash
cd chili_app && npm run lint && npm run build && npm run test:run
git add chili_app/src
git commit -m "feat(kb): configure score runs from the pack and surface the cleanup report"
```

---

### Task 13: Verify the two spec items that may already be resolved

Two of the spec's backend items look done. Confirm each rather than implementing a fix for a problem that does not exist — and if either is genuinely broken, report it and stop rather than expanding this task.

**Files:**
- Read only, unless a check fails.

- [ ] **Step 1: The Neo4j `relationship.weight` read/write mismatch**

The spec says the adapter reads a property it never writes. Read `backend/graph/adapters/neo4j_adapter.py`: line 404 writes `relationship.weight = row.weight` inside the upsert `SET` clause, and 441/459/1081 read it back.

Write a test that round-trips a relationship carrying a weight through the adapter and asserts the value survives. It belongs in the existing Neo4j adapter test module and should be marked `@pytest.mark.integration` alongside its neighbours.

If it passes: the item is resolved. Record that in your report with the line references, and note that the spec's §4.6 second half is stale.
If it fails: **stop and report.** Do not fix it inside this task — a genuine graph-persistence bug deserves its own task and its own review.

- [ ] **Step 2: `knowledge_base.delete` audit rows**

`api/routers/knowledgebases.py:483` and `:518` already call `record_knowledge_base_audit_event` on the 207 and 204 paths. Confirm both by reading, and confirm a test covers each. If one is uncovered, add it here — that is small enough to belong in this task.

- [ ] **Step 3: Commit whatever the checks produced**

```bash
cd backend && .venv/bin/pytest -q -m integration tests/graph 2>&1 | tail -5
git add backend/tests
git commit -m "test(graph): pin relationship weight round-tripping through Neo4j"
```

---

### Task 14: End-to-end verification and documentation

**Files:**
- Create: `chili_app/e2e/kb-activities.spec.ts`
- Create: `chili_app/e2e/kb-replace-warning.spec.ts`
- Modify: `chili_app/README.md`, `docs/architecture.md`, `backend/README.md`
- Modify: `docs/superpowers/plans/2026-08-15-ingestion-phase2-ia-split.md` — mark the deferrals this phase closed

- [ ] **Step 1: Write the e2e specs**

`kb-activities.spec.ts` — against the real stack: a freshly created knowledge base shows `Empty` in the top bar rather than `Blocked`, and its Overview lists Auto-fed as not set up with an action rather than as a failure. After ingesting a document with entities it reads `Queryable · N entities`.

`kb-replace-warning.spec.ts` — upload a document, then stage a byte-identical file under a different name and assert the confirm stage names the stored document it would replace. Then submit and assert the inventory still holds one document, not two.

Both must create and delete their own knowledge base with failure-surviving cleanup (`afterAll` or `try/finally`) — the suite runs `workers: 1` against a shared stack, and phase 2 established that pattern across five specs.

- [ ] **Step 2: Run the full stack and the whole suite**

```bash
make dev            # leave running
cd chili_app && npm run test:e2e
```

A failure here is yours to diagnose. If a spec fails because the product is wrong, fix the product and say so — do not bend the spec.

- [ ] **Step 3: Update the documentation**

- `chili_app/README.md` — the activity chip, the confirm stage, score-run params from the pack, the cleanup report.
- `docs/architecture.md` — readiness now reports per-activity states; the precheck endpoint; `score_runs` in the domain config.
- `backend/README.md` — the new endpoint and the config block.
- Phase 2's plan — mark the deferrals this phase closed (readiness recomposition, precheck, score-run config, the 207 report) so the list stays honest about what is still owed.

Do **not** edit `docs/superpowers/specs/` — the spec is a historical record.

Then sweep for statements this phase falsified: search non-archived docs for `Blocked`, `cms-fraud-features-v1`, `risk-linear-v1`, and readiness's binary phrasing, and correct each. Judge each hit: a present-tense claim about current behaviour gets fixed; past-tense history explaining why the design changed stays.

- [ ] **Step 4: Run every gate**

```bash
cd chili_app && npm run lint && npm run build && npm run test:run
cd ../backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov
cd .. && git diff --stat chili_app/openapi.json    # expect empty: contracts already regenerated
python3 scripts/backlog_consistency.py --check
python3 scripts/security_review_check.py
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs(kb): describe per-activity readiness and the phase-3 backend surfaces"
```

---

## Done when

- A knowledge base with entities and nothing else configured reads `Queryable · N entities`, never `Blocked`.
- Overview lists all four activities; absent optional setup renders quietly with an action, and only a genuine failure renders as danger.
- Staging a byte-identical file names the document it would replace, before submit.
- No `cms-fraud-features-v1` or `risk-linear-v1` string remains in `chili_app/src/`.
- `document.upload`, `document.delete` and `records.submit` write audit rows carrying no document content.
- Ingesting into a knowledge base with no risk profile produces no `AnalysisFailedEvent` and one summary log line.
- A 207 partial delete renders its per-step report with a working "Retry cleanup".
- Backend `pyright` and `ruff` clean, pytest ≥85%; frontend lint, build, unit and e2e all green; `chili_app/openapi.json` regenerated and committed with no drift.
