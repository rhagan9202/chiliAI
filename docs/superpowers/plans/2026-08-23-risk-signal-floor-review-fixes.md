# Risk Signal Floor Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close review findings for configurable risk signal floors before pushing local `prod`.

**Architecture:** Keep `analytics.min_risk_signals` as the domain-pack admission gate, but make its effects explicit across contracts, tests, docs, and analyst-facing metadata. Preserve the existing default of two signals for every pack that does not opt into one-signal scoring.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, pytest, OpenAPI export, openapi-typescript, React/TypeScript, pnpm build.

**Spec:** Multi-team review findings for commit `3df5c6f15491ff949a23ddb949cb81b5d05bd2ba`.

## Global Constraints

- Work from a clean branch based on local `prod` at `3df5c6f`.
- Use TDD for behavioral changes: write failing tests, verify red, implement, verify green.
- Do not change the default signal floor from `2`.
- Keep CMS DE-SynPUF explicitly configured at `analytics.min_risk_signals: 1`.
- Regenerate frontend contracts after backend Pydantic/API contract changes.
- Run focused tests as tasks land and full verification before merge.

---

### Task 1: Generated Contracts And Operator Docs

**Files:**
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`
- Modify: `backend/README.md`
- Modify: `docs/wiki/contracts/domain-config.md`
- Modify: `docs/architecture.md`
- Modify: `docs/ledger/module-map.md`
- Modify: `backend/analytics/peerstats/README.md`
- Modify: `backend/agent/coordinator.py`

**Interfaces:**
- Consumes: `AnalyticsConfig.min_risk_signals: int = Field(default=2, ge=1)`
- Produces: frontend generated `AnalyticsConfig` including `min_risk_signals?: number`

- [ ] **Step 1: Regenerate OpenAPI**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
```

Expected: `chili_app/openapi.json` includes `min_risk_signals` under `AnalyticsConfig`.

- [ ] **Step 2: Regenerate TypeScript API schema**

Run:

```bash
cd chili_app && npm run codegen:api
```

Expected: `chili_app/src/lib/api/schema.ts` includes `min_risk_signals?: number`.

- [ ] **Step 3: Update operator docs and stale comments**

Change all stale text that says risk scoring requires two signals to instead say the floor is domain-configured and defaults to two.

Specific required edits:
- `backend/README.md` optional analytics section must document `medium_risk_threshold`, `high_risk_threshold`, and `min_risk_signals`.
- `docs/wiki/contracts/domain-config.md` must document `min_risk_signals` default `2`, valid range `>=1`, and CMS DE-SynPUF rationale.
- `docs/architecture.md` and `docs/ledger/module-map.md` must stop saying the platform requires at least two signals unconditionally.
- `backend/analytics/peerstats/README.md` and `backend/agent/coordinator.py` must replace the hardcoded `>=2-signal floor` language with `configured signal floor`.

- [ ] **Step 4: Verify generated contract content**

Run:

```bash
rg -n "min_risk_signals" chili_app/openapi.json chili_app/src/lib/api/schema.ts backend/README.md docs/wiki/contracts/domain-config.md docs/architecture.md docs/ledger/module-map.md backend/analytics/peerstats/README.md backend/agent/coordinator.py
```

Expected: generated contract files and docs all reference the new field; no stale unconditional two-signal language remains in these files.

### Task 2: Backend Regression Coverage For Configurable Floor

**Files:**
- Modify: `backend/tests/analytics/risk/test_service.py`
- Modify: `backend/tests/analytics/score_runs/test_executor.py`
- Modify: `backend/tests/api/test_dependencies.py`
- Modify: `backend/tests/config/test_schema.py`

**Interfaces:**
- Consumes: `create_risk_service(..., min_signals=1)`
- Consumes: `api.dependencies.get_risk_service() -> RiskService`
- Consumes: `handle_score_batch_queued(event, deps) -> int`
- Produces: regression tests proving one-signal scoring reaches score runs, API DI, validation, and thresholds.

- [ ] **Step 1: RED - add service threshold and validation tests**

Add tests:

```python
def test_the_signal_floor_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="min_signals must be at least 1"):
        create_risk_service(
            InMemoryRiskSignalSource(profiles=[]),
            event_bus=InMemoryEventBus(),
            min_signals=0,
        )


def test_one_signal_floor_still_uses_risk_thresholds() -> None:
    service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="low-provider",
                    signals=[RiskSignal(signal_name="weak", value=0.2, weight=1.0)],
                ),
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="high-provider",
                    signals=[RiskSignal(signal_name="strong", value=0.9, weight=1.0)],
                ),
            ]
        ),
        event_bus=InMemoryEventBus(),
        min_signals=1,
        default_medium_risk_threshold=0.5,
        default_high_risk_threshold=0.8,
    )

    low = service.assess(RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="low-provider"))
    high = service.assess(RiskAssessmentRequest(knowledge_base_id="kb-1", entity_id="high-provider"))

    assert low.risk_level == "low"
    assert high.risk_level == "high"
```

Run:

```bash
uv run --project backend pytest backend/tests/analytics/risk/test_service.py::test_the_signal_floor_rejects_invalid_values backend/tests/analytics/risk/test_service.py::test_one_signal_floor_still_uses_risk_thresholds
```

Expected: fail before any implementation only if existing behavior does not already cover it; if tests pass immediately, record that no production change is needed for this slice.

- [ ] **Step 2: RED - add config validation test**

Add:

```python
def test_analytics_config_rejects_non_positive_signal_floor() -> None:
    with pytest.raises(ValidationError):
        AnalyticsConfig(min_risk_signals=0)
```

Run the single test and verify it fails or passes from existing validation.

- [ ] **Step 3: RED - add API DI propagation test**

Add a test in `backend/tests/api/test_dependencies.py` that installs a config with `AnalyticsConfig(min_risk_signals=1, medium_risk_threshold=0.4, high_risk_threshold=0.7)`, calls `dependencies.get_risk_service()`, and asserts the service has `min_signals == 1`, `default_medium_risk_threshold == 0.4`, and `default_high_risk_threshold == 0.7`.

Run:

```bash
uv run --project backend pytest backend/tests/api/test_dependencies.py::test_get_risk_service_uses_configured_analytics_floor
```

Expected: fails if API DI drops `min_signals`.

- [ ] **Step 4: RED - add real score-run one-signal test**

Add a score-run executor test using a real `RiskService` and `InMemoryRiskSignalSource` with one signal for `e1`. Assert `scored_entities == 1`, `skipped_entities == 0`, and an `events.types.RiskScoredEvent` was published on the event bus.

Run:

```bash
uv run --project backend pytest backend/tests/analytics/score_runs/test_executor.py::test_score_run_counts_one_signal_entity_as_scored_with_configured_floor
```

Expected: fails if score-run behavior still treats one-signal profiles as skipped.

- [ ] **Step 5: GREEN - implement minimal code if any RED test fails**

If a test fails because production wiring is missing, fix only the missing wiring. If all tests pass because implementation already exists, keep the tests as regression coverage and do not change production code.

- [ ] **Step 6: Verify focused regression suite**

Run:

```bash
uv run --project backend pytest backend/tests/analytics/risk/test_service.py backend/tests/analytics/score_runs/test_executor.py backend/tests/api/test_dependencies.py backend/tests/config/test_schema.py
```

Expected: all selected tests pass.

### Task 3: Analyst Semantics And Frontend Copy

**Files:**
- Modify: `backend/analytics/risk/service_models.py`
- Modify: `backend/api/contracts.py`
- Modify: `backend/analytics/explainability/service.py`
- Modify: `backend/agent/coordinator.py`
- Modify: `chili_app/src/components/investigation/EntityDossierHeader.tsx`
- Modify tests nearest these surfaces as needed.

**Interfaces:**
- Produces: risk responses expose `signal_count` and `min_risk_signals`
- Produces: evidence provenance metadata can preserve evidence breadth
- Produces: frontend risk meter accessibility copy no longer says composite risk

- [ ] **Step 1: RED - assert risk response carries signal-floor metadata**

Add or update risk service test so a one-signal response asserts:

```python
assert response.factor_count == 1
assert response.signal_count == 1
assert response.min_risk_signals == 1
```

Run the single test and verify it fails before adding fields.

- [ ] **Step 2: GREEN - add metadata fields**

Add fields to `RiskAssessmentResponse`:

```python
signal_count: int = Field(ge=0)
min_risk_signals: int = Field(ge=1)
```

Populate both in `RiskService.assess()`. Keep `factor_count` for backward compatibility.

- [ ] **Step 3: RED - assert evidence provenance includes signal metadata**

Add a focused test near explainability provenance or coordinator context building that checks `signal_count` and `min_risk_signals` survive into `ExplanationContext.scores` or evidence metadata.

- [ ] **Step 4: GREEN - propagate metadata into explanation context**

Add `scores["signal_count"] = float(risk_response.signal_count)` and `scores["min_risk_signals"] = float(risk_response.min_risk_signals)` in `build_explanation_context()`.

- [ ] **Step 5: Update frontend accessibility copy**

Change `aria-label="Composite risk"` to `aria-label="Risk score"` in `EntityDossierHeader.tsx`.

- [ ] **Step 6: Verify focused tests**

Run:

```bash
uv run --project backend pytest backend/tests/analytics/risk/test_service.py backend/tests/analytics/explainability backend/tests/agent/test_risk_scored_graph_flow.py
```

Expected: all pass.

### Task 4: Graph Alert Guardrail

**Files:**
- Modify: `backend/tests/agent/test_config_reload.py` or nearest existing coordinator Flow B test.
- Modify: `backend/agent/coordinator.py` only if test exposes unintended behavior.

**Interfaces:**
- Consumes: one-signal `RiskAssessmentResponse`
- Produces: documented alert behavior for low/medium single-signal scores

- [ ] **Step 1: RED - add one-signal alert semantics test**

Add a focused coordinator test that creates a one-signal low-risk assessment under `min_signals=1` and exercises the records/graph analytics fan-out alert path. Assert the intended behavior:

```python
assert no AlertsCreatedEvent is published for low-risk one-signal assessments
```

If current product decision is instead that all scored top-N entities create alerts, name the test accordingly and assert exactly that. The preferred fix is to prevent low-risk one-signal scores from becoming alerts.

- [ ] **Step 2: GREEN - implement threshold guard if needed**

If the RED test shows low-risk single-signal alerts are produced, add a narrow guard before `_run_explainability_stage()` so Flow B only creates alerts for medium/high risk. Do not change risk history or graph risk projection.

- [ ] **Step 3: Verify coordinator tests**

Run:

```bash
uv run --project backend pytest backend/tests/agent/test_risk_scored_graph_flow.py backend/tests/agent/test_config_reload.py backend/tests/agent/test_records_analytics_fanout.py
```

Expected: all pass.

### Task 5: Final Verification And Commit

**Files:**
- All files touched by Tasks 1-4.

- [ ] **Step 1: Run backend full suite**

Run with Docker services healthy:

```bash
uv run pytest
```

from `backend/`.

Expected: all backend tests pass.

- [ ] **Step 2: Run backend static checks**

Run:

```bash
uv run --project backend ruff check backend
uv run --project backend pyright
```

Expected: no errors.

- [ ] **Step 3: Run frontend generated/build checks**

Run:

```bash
pnpm build
```

from `chili_app/`.

Expected: frontend typecheck/build passes.

- [ ] **Step 4: Whitespace and git state**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: whitespace clean, only intended files changed.

- [ ] **Step 5: Commit**

Commit message:

```bash
git commit -m "fix(risk): close signal floor review gaps"
```

Expected: one focused commit on the fix branch, ready for review and merge to local `prod`.
