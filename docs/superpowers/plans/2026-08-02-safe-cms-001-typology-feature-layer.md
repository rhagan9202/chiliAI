# SAFE-CMS-001 Typology And Feature Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first CMS fraud surge slice: versioned domain-pack typologies, reusable feature definitions, and a KB-scoped read surface for feature catalog/value display.

**Architecture:** Keep CMS-specific fraud labels in the Medicare domain pack and add only generic platform models/routes. Start with config-validated typologies and feature definitions, then expose catalog reads through KB-scoped API routes and frontend primitives. Feature values use a dedicated feature service surface so later score-all/provenance work can attach catalog version, transformation version, source refs, and score-run lineage without weakening `entity_derived_signals`.

**Tech Stack:** Pydantic v2 config models, FastAPI routers/dependencies, pytest, generated OpenAPI TypeScript contracts, React Query, Vitest/Testing Library.

---

## Task 0: Inventory And Baseline

**Files:**
- Read: `backend/config/schema.py`
- Read: `backend/config/defaults/medicare_fraud.yaml`
- Read: `backend/analytics/risk/adapters/postgres.py`
- Read: `backend/analytics/peerstats/adapters/postgres.py`
- Read: `backend/api/routers/analytics.py`
- Read: `backend/api/routers/knowledgebases.py`
- Read: `chili_app/src/api/analytics.ts`
- Read: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Verify: `backend/tests/config/test_schema.py`
- Verify: `backend/tests/config/test_loader.py`

- [x] **Step 1: Confirm branch and worktree state**

Run:

```bash
git status --short --branch
```

Expected: branch `fix/normalize-kb-query-param` with only intentional planning-doc changes.

- [x] **Step 2: Inventory the current implementation seams**

Findings:

- `DomainConfig` currently has no typology or feature-catalog sections.
- Default domain packs load through `backend/config/loader.py` and are covered by `backend/tests/config/test_loader.py`.
- `entity_derived_signals` supports current risk scoring but only stores latest metric/value/weight/rationale. It does not carry feature catalog version, transformation version, source refs, or score-run lineage.
- Existing analytics routes use `/analytics/*`, while the PI 1 spec proposes KB-scoped feature routes. Use `/knowledgebases/{knowledge_base_id}/features/catalog` and `/knowledgebases/{knowledge_base_id}/entities/{entity_type}/{entity_id}/features` so KB existence/scope checks are explicit.
- Frontend consumers already use generated contracts plus small hand-written API wrappers in `chili_app/src/api/`.

- [x] **Step 3: Run focused baseline tests**

Run:

```bash
env CHILI_CONFIG_PATH=/home/rdhagan92/chiliAI/backend/config/defaults/medicare_fraud.yaml backend/.venv/bin/python -m pytest backend/tests/config/test_schema.py backend/tests/config/test_loader.py -q
```

Expected: `126 passed`.

## Task 1: Domain Config Typology And Feature Catalog

**Files:**
- Modify: `backend/config/schema.py`
- Modify: `backend/config/defaults/medicare_fraud.yaml`
- Test: `backend/tests/config/test_schema.py`
- Test: `backend/tests/config/test_loader.py`

- [x] **Step 1: Write failing schema tests**

Add tests to `backend/tests/config/test_schema.py`:

```python
def test_typologies_and_feature_catalog_round_trip() -> None:
    payload = _make_config().model_dump(mode="json")
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing spike",
            "description": "Provider billing volume increased beyond peer norms.",
            "entity_types": ["provider"],
            "severity_hint": "high",
            "feature_ids": ["weekly_provider_billing_zscore"],
            "policy_rule_ids": ["billing_thresholds.claim_over_billed"],
        }
    ]
    payload["feature_catalog"] = {
        "version": "cms-fraud-features-v1",
        "features": [
            {
                "id": "weekly_provider_billing_zscore",
                "label": "Weekly provider billing z-score",
                "description": "Peer-normalized weekly billed amount.",
                "value_type": "decimal",
                "entity_types": ["provider"],
                "source_mappings": [
                    {
                        "source_type": "derived_signal",
                        "source_ref": "entity_derived_signals.weekly_provider_billing",
                        "raw_fields": ["billed_amount", "service_date", "provider_npi"],
                    }
                ],
                "peer_dimensions": ["provider"],
                "threshold_hints": {"high": 2.0, "critical": 3.0},
                "transformation_version": "peerstats-zscore-v1",
                "typology_ids": ["billing_spike"],
            }
        ],
    }

    config = DomainConfig.model_validate(payload)

    assert config.typologies[0].id == "billing_spike"
    assert config.feature_catalog.version == "cms-fraud-features-v1"
    assert config.feature_catalog.features[0].source_mappings[0].raw_fields == [
        "billed_amount",
        "service_date",
        "provider_npi",
    ]


def test_typology_rejects_unknown_feature_reference() -> None:
    payload = _make_config().model_dump(mode="json")
    payload["typologies"] = [
        {
            "id": "billing_spike",
            "label": "Billing spike",
            "description": "Provider billing volume increased beyond peer norms.",
            "entity_types": ["alpha"],
            "feature_ids": ["missing_feature"],
        }
    ]
    payload["feature_catalog"] = {"version": "v1", "features": []}

    with pytest.raises(ValidationError, match="Typology 'billing_spike' references unknown feature_id 'missing_feature'"):
        DomainConfig.model_validate(payload)
```

Add a loader test to `backend/tests/config/test_loader.py`:

```python
def test_medicare_fraud_pack_declares_typologies_and_features() -> None:
    cfg = _load_default("medicare_fraud.yaml")

    assert len(cfg.typologies) >= 8
    assert len(cfg.feature_catalog.features) >= 20
    assert {typology.id for typology in cfg.typologies} >= {
        "dmepos_overutilization",
        "billing_spike",
        "peer_outlier",
        "referral_ring_exposure",
        "geographic_anomaly",
        "enrollment_risk",
        "never_provided_service",
        "policy_threshold_exposure",
    }
```

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
env CHILI_CONFIG_PATH=/home/rdhagan92/chiliAI/backend/config/defaults/medicare_fraud.yaml backend/.venv/bin/python -m pytest backend/tests/config/test_schema.py::test_typologies_and_feature_catalog_round_trip backend/tests/config/test_schema.py::test_typology_rejects_unknown_feature_reference backend/tests/config/test_loader.py::test_medicare_fraud_pack_declares_typologies_and_features -q
```

Expected: fail because `DomainConfig` rejects unknown top-level `typologies`/`feature_catalog` or has no matching attributes.

- [x] **Step 3: Add generic config models**

Modify `backend/config/schema.py` before `DomainConfig`:

```python
class FeatureSourceMappingConfig(BaseModel):
    """A source path used to derive a normalized feature value."""

    source_type: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    raw_fields: list[str] = Field(default_factory=list[str])


class FeatureDefinitionConfig(BaseModel):
    """A reusable, domain-neutral feature definition."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    value_type: Literal["boolean", "integer", "decimal", "string", "categorical"] = "decimal"
    entity_types: list[str] = Field(default_factory=list[str])
    source_mappings: list[FeatureSourceMappingConfig] = Field(default_factory=list[FeatureSourceMappingConfig])
    peer_dimensions: list[str] = Field(default_factory=list[str])
    threshold_hints: dict[str, float] = Field(default_factory=dict[str, float])
    transformation_version: str = Field(default="v1", min_length=1)
    typology_ids: list[str] = Field(default_factory=list[str])


class FeatureCatalogConfig(BaseModel):
    """Versioned collection of feature definitions for a domain."""

    version: str = Field(default="v1", min_length=1)
    features: list[FeatureDefinitionConfig] = Field(default_factory=list[FeatureDefinitionConfig])

    @model_validator(mode="after")
    def _validate_unique_feature_ids(self) -> FeatureCatalogConfig:
        ids = [feature.id for feature in self.features]
        if len(set(ids)) != len(ids):
            raise ValueError("FeatureCatalogConfig feature ids must be unique.")
        return self


class FraudTypologyConfig(BaseModel):
    """A versioned fraud-pattern label described by a domain pack."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = ""
    entity_types: list[str] = Field(default_factory=list[str])
    severity_hint: Literal["low", "medium", "high", "critical"] | None = None
    feature_ids: list[str] = Field(default_factory=list[str])
    policy_rule_ids: list[str] = Field(default_factory=list[str])
    playbook_ids: list[str] = Field(default_factory=list[str])
```

Add fields to `DomainConfig`:

```python
typologies: list[FraudTypologyConfig] = Field(default_factory=list[FraudTypologyConfig])
feature_catalog: FeatureCatalogConfig = Field(default_factory=FeatureCatalogConfig)
```

In `DomainConfig._validate_cross_references`, after default sections are populated, validate:

```python
entity_names = {entity.name for entity in self.entities}
feature_ids = {feature.id for feature in self.feature_catalog.features}
typology_ids = {typology.id for typology in self.typologies}

for feature in self.feature_catalog.features:
    for entity_type in feature.entity_types:
        if entity_type not in entity_names:
            raise ValueError(f"Feature '{feature.id}' references unknown entity_type '{entity_type}'.")
    for typology_id in feature.typology_ids:
        if typology_id not in typology_ids:
            raise ValueError(f"Feature '{feature.id}' references unknown typology_id '{typology_id}'.")

for typology in self.typologies:
    for entity_type in typology.entity_types:
        if entity_type not in entity_names:
            raise ValueError(f"Typology '{typology.id}' references unknown entity_type '{entity_type}'.")
    for feature_id in typology.feature_ids:
        if feature_id not in feature_ids:
            raise ValueError(f"Typology '{typology.id}' references unknown feature_id '{feature_id}'.")
```

- [x] **Step 4: Populate Medicare fraud pack**

Add `typologies:` and `feature_catalog:` to `backend/config/defaults/medicare_fraud.yaml`.

Minimum typology IDs:

```yaml
typologies:
  - id: dmepos_overutilization
  - id: billing_spike
  - id: peer_outlier
  - id: referral_ring_exposure
  - id: geographic_anomaly
  - id: enrollment_risk
  - id: never_provided_service
  - id: policy_threshold_exposure
```

Minimum feature IDs:

```yaml
feature_catalog:
  version: cms-fraud-features-v1
  features:
    - id: weekly_provider_billing_zscore
    - id: weekly_provider_claim_count_zscore
    - id: claim_amount_threshold_exposure
    - id: anomalous_claim_score
    - id: provider_referral_outdegree
    - id: provider_referral_indegree
    - id: shared_beneficiary_density
    - id: geographic_state_outlier
    - id: specialty_peer_group_outlier
    - id: beneficiary_chronic_condition_complexity
    - id: beneficiary_high_utilization_count
    - id: facility_concentration_ratio
    - id: repeated_procedure_code_density
    - id: service_date_burstiness
    - id: policy_billing_threshold_hits
    - id: enrollment_age_risk
    - id: never_provided_service_signal
    - id: dmepos_code_exposure
    - id: cross_kb_policy_citation_count
    - id: evidence_pack_confidence
```

Each full feature entry must include `label`, `description`, `value_type`, `entity_types`, at least one
`source_mappings` item, `transformation_version`, and `typology_ids`.

- [x] **Step 5: Run tests to verify GREEN**

Run:

```bash
env CHILI_CONFIG_PATH=/home/rdhagan92/chiliAI/backend/config/defaults/medicare_fraud.yaml backend/.venv/bin/python -m pytest backend/tests/config/test_schema.py::test_typologies_and_feature_catalog_round_trip backend/tests/config/test_schema.py::test_typology_rejects_unknown_feature_reference backend/tests/config/test_loader.py::test_medicare_fraud_pack_declares_typologies_and_features -q
```

Expected: pass.

- [x] **Step 6: Run focused config suite**

Run:

```bash
env CHILI_CONFIG_PATH=/home/rdhagan92/chiliAI/backend/config/defaults/medicare_fraud.yaml backend/.venv/bin/python -m pytest backend/tests/config/test_schema.py backend/tests/config/test_loader.py -q
```

Expected: pass.

Task 1 review notes:

- Spec review approved with no issues.
- Code-quality review found two important validation gaps: duplicate typology IDs and dangling
  `policy_rule_ids`. Added regression tests and validator coverage before moving to Task 2.
- Post-fix verification: `backend/tests/config/test_schema.py backend/tests/config/test_loader.py -q`
  passed with 132 tests; non-CMS pack tests passed with 31 tests.

## Task 2: Backend Feature Catalog Service And KB-Scoped Routes

**Files:**
- Create: `backend/analytics/features/__init__.py`
- Create: `backend/analytics/features/service.py`
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/routers/knowledgebases.py`
- Test: `backend/tests/api/test_knowledgebases_router.py`

- [x] **Step 1: Write failing API tests**

Add tests proving:

- `GET /knowledgebases/{kb_id}/features/catalog` 404s for a missing KB.
- The route returns `catalog_version`, configured typologies, and feature definitions for an existing KB.
- `GET /knowledgebases/{kb_id}/entities/{entity_type}/{entity_id}/features` returns an empty feature-value list for an existing entity when no feature-value repository is installed yet.

- [x] **Step 2: Run tests to verify RED**

Run the new tests only. Expected: 404/route missing or import failures for missing response models.

- [x] **Step 3: Implement service and response models**

Add catalog/value response models to `backend/api/contracts.py` and a small service that reads from `DomainConfig`.
Do not add persistence in this task.

- [x] **Step 4: Implement routes**

Mount the two KB-scoped feature routes in `backend/api/routers/knowledgebases.py`, using the existing knowledge-base repository dependency to reject missing KBs.

- [x] **Step 5: Run focused API tests**

Run the new API tests plus related KB router tests.

Task 2 review notes:

- New tests initially failed with missing route-function attributes, then passed after adding the
  config-backed service, response models, dependency, and routes.
- Existing `TestClient` tests in `backend/tests/api/test_knowledgebases_router.py` hang in this environment
  even for pre-existing tests, so the new tests call route functions directly and verify router registration
  separately.
- Spec review and quality review approved. Post-task verification: focused config/API command passed with
  135 tests; `compileall`, `git diff --check`, and `scripts/backlog_consistency.py --check` passed.

## Task 3: Feature Value Repository Skeleton

**Files:**
- Create: `backend/analytics/features/models.py`
- Create: `backend/analytics/features/protocols.py`
- Create: `backend/analytics/features/adapters/in_memory.py`
- Test: `backend/tests/analytics/features/test_in_memory.py`

- [x] **Step 1: Write failing repository tests**

Cover upsert/list behavior for normalized feature values with source refs, catalog version, transformation version, and optional score-run id.

- [x] **Step 2: Implement minimal in-memory repository**

Keep it independent from risk scoring and persistence. Sprint 2 can wire score-all writes into this seam.

- [x] **Step 3: Run focused repository tests**

Expected: all feature repository tests pass.

Task 3 review notes:

- Repository tests initially failed with `ModuleNotFoundError` for the missing analytics feature adapters,
  then passed after adding the value model, repository protocol, and in-memory adapter.
- Spec re-review approved after adding explicit same-feature `observed_at` ordering coverage and documenting
  that `normalized_value=None` is intentional for raw categorical features.
- Quality review found mixed naive/timezone-aware `observed_at` values could raise during sorting. Fixed by
  normalizing `FeatureValueRecord.observed_at` to UTC and adding a regression test for mixed timestamp inputs.
- Post-task verification: `backend/tests/analytics/features/test_in_memory.py -q` passed with 9 tests and
  `compileall backend/analytics/features` passed.

## Task 4: Frontend API Wrapper And Display Primitives

**Files:**
- Modify: `chili_app/src/api/analytics.ts` or create `chili_app/src/api/features.ts`
- Create: `chili_app/src/components/analytics/TypologyBadge.tsx`
- Create: `chili_app/src/components/analytics/FeatureList.tsx`
- Test: `chili_app/src/components/analytics/__tests__/FeatureList.test.tsx`

- [x] **Step 1: Regenerate contracts**

After Task 2 backend routes are green, run the repo's OpenAPI export and frontend codegen path.

- [x] **Step 2: Write failing component tests**

Test typology badges, feature labels, source refs, and empty states.

- [x] **Step 3: Implement API wrapper and primitives**

Use generated types; no hand-written mirror contract types.

- [x] **Step 4: Run focused frontend tests**

Expected: new Vitest tests pass.

Task 4 review notes:

- Exported backend OpenAPI to `chili_app/openapi.json`, then ran `npm run codegen:api` to refresh
  `chili_app/src/lib/api/schema.ts`.
- Added generated-schema aliases for feature catalog and entity feature values in `chili_app/src/api/contracts.ts`;
  added KB-scoped feature API helpers in `chili_app/src/api/features.ts`.
- Added `TypologyBadge` and `FeatureList` primitives with tests covering typology severity hints, feature labels,
  normalized/raw values, source refs, fallback labels, and empty state.
- Task 4 tests first failed on missing modules, then passed after implementation. Spec review approved.

## Task 5: Workbench Smoke Integration

**Files:**
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Test: `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

- [x] **Step 1: Write failing workbench smoke test**

When risk factors exist for a selected provider and the feature catalog contains matching features, the Signals tab shows typology and feature labels.

- [x] **Step 2: Implement minimal UI integration**

Keep this small. Full cockpit work belongs to `SAFE-CMS-005`.

- [x] **Step 3: Run focused workbench tests**

Expected: relevant page tests pass.

Task 5 review notes:

- Workbench smoke test initially failed because the page did not call feature hooks or render feature values.
- Added `useFeatureCatalog` and `useEntityFeatureValues` at the page level and rendered `FeatureList` inside the
  existing Signals tab under a small Feature values panel.
- Focused frontend verification passed: `npm run test:run -- src/api/__tests__/features.test.ts
  src/components/analytics/__tests__/FeatureList.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`
  passed with 32 tests.

## Task 6: Verification And Closeout

**Files:**
- Modify: `docs/project/planning/backlog.md`
- Modify: `docs/superpowers/plans/2026-08-02-safe-cms-001-typology-feature-layer.md`
- Optional: `.superpowers/sdd/safe-cms-001-task-*.md`

- [x] **Step 1: Run backend gates**

Run focused config/API/feature tests.

- [x] **Step 2: Run frontend gates**

Run focused Vitest tests and frontend build if generated contracts changed.

- [x] **Step 3: Run diff checks**

Run:

```bash
git diff --check
python3 scripts/backlog_consistency.py --check
```

- [x] **Step 4: Record closeout**

Update backlog/status docs with completed tasks, commands, limitations, and next `SAFE-CMS-002` dependencies.

Task 6 closeout notes:

- Backend gate passed: `env CHILI_CONFIG_PATH=/home/rdhagan92/chiliAI/backend/config/defaults/medicare_fraud.yaml
  backend/.venv/bin/python -m pytest backend/tests/analytics/features/test_in_memory.py
  backend/tests/config/test_schema.py backend/tests/config/test_loader.py
  backend/tests/api/test_knowledgebases_router.py::test_feature_catalog_returns_404_for_missing_kb
  backend/tests/api/test_knowledgebases_router.py::test_feature_catalog_returns_domain_config_typologies_and_features
  backend/tests/api/test_knowledgebases_router.py::test_entity_feature_values_return_empty_list_for_existing_kb -q`
  passed with 144 tests.
- Frontend gate passed: `npm run test:run -- src/api/__tests__/features.test.ts
  src/components/analytics/__tests__/FeatureList.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`
  passed with 32 tests.
- Build gate passed: `pnpm build` completed successfully; Vite emitted the existing large-chunk warning.
- Hygiene gates passed: `git diff --check` and `python3 scripts/backlog_consistency.py --check`.
- `SAFE-CMS-002` starts from the feature catalog and repository seam added here: durable score-all should write
  `FeatureValueRecord` rows with catalog version, transformation version, source refs, and score-run lineage.
