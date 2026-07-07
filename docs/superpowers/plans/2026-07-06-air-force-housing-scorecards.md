# Air Force Housing Scorecards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt chiliAI into a Department of the Air Force housing executive dashboard with file/export ingestion, configurable UH/MFH scorecards, durable scorecard runs, and a map-led cross-installation operating picture.

**Architecture:** Add a `department_air_force_housing` domain pack, extend `DomainConfig` with a reusable `scorecards` configuration surface, implement a backend `scorecards` capability with deterministic evaluation and persistence, expose `/scorecards` and `/housing` APIs, then add a `/housing` frontend page with an SVG map, ranking table, scorecard readiness, exports, and contextual RAG entry points. V1 uses file/export ingestion and avoids live connectors.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Alembic/Postgres plus in-memory adapters, React 19, TypeScript, TanStack Query, Vite, existing generated OpenAPI workflow, existing records/document ingestion.

---

## File Structure

Create:
- `backend/scorecards/__init__.py` - public scorecard service exports.
- `backend/scorecards/models.py` - internal domain models for template/run/metric state.
- `backend/scorecards/service_models.py` - API/service request and response DTOs.
- `backend/scorecards/protocols.py` - service protocol.
- `backend/scorecards/service.py` - generation/list/detail/export orchestration.
- `backend/scorecards/evaluation.py` - pure deterministic template evaluator.
- `backend/scorecards/exceptions.py` - scorecard-specific errors.
- `backend/scorecards/adapters/__init__.py` - adapter exports.
- `backend/scorecards/adapters/protocols.py` - repository protocol.
- `backend/scorecards/adapters/in_memory.py` - in-memory run repository.
- `backend/scorecards/adapters/postgres.py` - Postgres run repository.
- `backend/api/routers/scorecards.py` - `/scorecards` API.
- `backend/api/routers/housing.py` - `/housing` executive read API.
- `backend/database/migrations/versions/0008_scorecards.py` - persistent scorecard runs.
- `backend/config/defaults/department_air_force_housing.yaml` - domain pack.
- `backend/tests/config/test_air_force_housing_pack.py` - domain pack validation.
- `backend/tests/scorecards/test_evaluation.py` - evaluator unit tests.
- `backend/tests/scorecards/test_service.py` - service orchestration tests.
- `backend/tests/scorecards/test_in_memory_store.py` - repository contract for in-memory.
- `backend/tests/scorecards/test_postgres_store.py` - integration repository contract.
- `backend/tests/api/test_scorecards_router.py` - scorecard route tests.
- `backend/tests/api/test_housing_router.py` - executive housing route tests.
- `chili_app/src/api/scorecards.ts` - scorecards client/hooks.
- `chili_app/src/api/housing.ts` - housing dashboard client/hooks.
- `chili_app/src/api/__tests__/scorecards.test.ts` - scorecards client tests.
- `chili_app/src/api/__tests__/housing.test.ts` - housing client tests.
- `chili_app/src/components/housing/InstallationHealthMap.tsx` - SVG map.
- `chili_app/src/components/housing/InstallationHealthMap.module.css` - map styles.
- `chili_app/src/components/housing/InstallationRankingTable.tsx` - ranking table.
- `chili_app/src/components/housing/ScorecardReadinessPanel.tsx` - readiness panel.
- `chili_app/src/pages/HousingExecutivePage.tsx` - `/housing` page.
- `chili_app/src/pages/__tests__/HousingExecutivePage.test.tsx` - page behavior tests.
- `chili_app/e2e/air-force-housing-scorecards.spec.ts` - upload/generate/map/export/RAG smoke.
- `docs/testing/knowledge_base_fixtures/air_force_housing/README.md` - fixture index.
- `docs/testing/knowledge_base_fixtures/air_force_housing/umd_sample.csv` - sample manpower extract.
- `docs/testing/knowledge_base_fixtures/air_force_housing/bah_sample.csv` - sample allowance extract.
- `docs/testing/knowledge_base_fixtures/air_force_housing/inventory_sample.csv` - sample inventory extract.
- `docs/testing/knowledge_base_fixtures/air_force_housing/market_sample.csv` - sample market extract.
- `docs/testing/knowledge_base_fixtures/air_force_housing/demographics_sample.csv` - sample demographics extract.

Modify:
- `backend/config/schema.py` - add scorecard config models and `DomainConfig.scorecards`.
- `backend/config/README.md` - document the new Air Force housing pack and scorecards section.
- `backend/api/app.py` - include scorecards and housing routers.
- `backend/api/contracts.py` - add frontend-facing response/request models.
- `backend/api/dependencies.py` - compose scorecard repository/service and housing payload helpers.
- `backend/api/_kb_cleanup.py` - delete scorecard runs on KB delete.
- `chili_app/src/api/contracts.ts` - export generated scorecard/housing aliases.
- `chili_app/src/app/router.tsx` - add `/housing`.
- `chili_app/src/components/layout/Sidebar.tsx` - add a `housing` icon mapping.
- `chili_app/src/lib/ragContext.ts` - add housing scorecard launch source fields.
- `docs/testing/DATA.md` - reference Air Force housing fixture set.
- `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts` - regenerated after backend contract changes.

---

### Task 1: Scorecard Config Schema And Air Force Housing Domain Pack

**Files:**
- Modify: `backend/config/schema.py`
- Create: `backend/config/defaults/department_air_force_housing.yaml`
- Create: `backend/tests/config/test_air_force_housing_pack.py`
- Create: `docs/testing/knowledge_base_fixtures/air_force_housing/*.csv`
- Modify: `backend/config/README.md`
- Modify: `docs/testing/DATA.md`

- [ ] **Step 1: Write failing config schema tests**

Create `backend/tests/config/test_air_force_housing_pack.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from config.loader import load_config
from config.schema import DomainConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_PATH = REPO_ROOT / "backend" / "config" / "defaults" / "department_air_force_housing.yaml"


@pytest.fixture()
def config(monkeypatch: pytest.MonkeyPatch) -> DomainConfig:
    monkeypatch.setenv("CHILI_CONFIG_PATH", str(PACK_PATH))
    return load_config()


def test_air_force_housing_pack_loads(config: DomainConfig) -> None:
    assert config.domain.name == "department_air_force_housing"
    assert config.domain.display_name == "Department of the Air Force Housing"
    assert config.capabilities.structured_ingestion is True
    assert config.capabilities.rag_chat is True


def test_housing_entities_and_relationships_are_declared(config: DomainConfig) -> None:
    entity_names = {entity.name for entity in config.entities}
    assert {
        "installation",
        "housing_asset",
        "housing_inventory_snapshot",
        "population_demand_snapshot",
        "allowance_market_snapshot",
        "demographic_snapshot",
        "resident_experience_snapshot",
        "scorecard_run",
    } <= entity_names
    relationship_names = {relationship.name for relationship in config.relationships}
    assert {
        "installation_has_asset",
        "asset_has_inventory_snapshot",
        "installation_has_population_demand",
        "installation_has_market_snapshot",
        "installation_has_demographic_snapshot",
        "scorecard_run_for_installation",
    } <= relationship_names


def test_housing_record_feeds_cover_required_exports(config: DomainConfig) -> None:
    assert config.records is not None
    feeds = {feed.name: feed for feed in config.records.feeds}
    assert {"umd_authorizations", "bah_rates", "housing_inventory", "market_availability", "area_demographics"} <= set(feeds)
    assert feeds["umd_authorizations"].accepted_formats == ["csv", "jsonl"]
    assert feeds["housing_inventory"].allow_extra_fields is True
    for feed in feeds.values():
        assert feed.entities
        assert feed.observations


def test_scorecard_templates_are_configured(config: DomainConfig) -> None:
    template_ids = {template.id for template in config.scorecards.templates}
    assert {"uh_scorecard", "mfh_scorecard"} <= template_ids
    for template in config.scorecards.templates:
        assert template.sections
        assert template.export_formats == ["json", "markdown"]
        for section in template.sections:
            assert section.metrics
            for metric in section.metrics:
                assert metric.inputs
                assert metric.formula.operator in {"ratio", "sum", "mean", "weighted_mean", "latest"}
                assert metric.thresholds.pass_min is not None or metric.thresholds.fail_max is not None


def test_housing_ui_lands_on_housing_page(config: DomainConfig) -> None:
    assert config.ui is not None
    pages = {page.id: page for page in config.ui.navigation.pages} if config.ui.navigation else {}
    assert pages["housing"].route == "/housing"
    assert config.ui.roles["executive"].landing_page == "housing"
```

- [ ] **Step 2: Run the failing config test**

Run:

```bash
uv run --project backend pytest backend/tests/config/test_air_force_housing_pack.py -q
```

Expected: fail because `DomainConfig` has no `scorecards` field and the pack does not exist.

- [ ] **Step 3: Add scorecard config models**

In `backend/config/schema.py`, add below `PolicyRulePack`:

```python
class ScorecardMetricInputConfig(BaseModel):
    """One named input consumed by a configured scorecard metric."""

    name: str
    source: Literal["record_feed", "metric", "graph", "document"]
    ref: str
    field: str | None = None
    filter: dict[str, str | float | int | bool] = Field(default_factory=dict)


class ScorecardFormulaConfig(BaseModel):
    """Bounded scorecard formula; no arbitrary code execution."""

    operator: Literal["ratio", "sum", "mean", "weighted_mean", "latest"]
    numerator: str | None = None
    denominator: str | None = None
    value: str | None = None
    weight: str | None = None


class ScorecardThresholdConfig(BaseModel):
    pass_min: float | None = None
    warn_min: float | None = None
    fail_max: float | None = None
    incomplete_when_missing: bool = True


class ScorecardMetricConfig(BaseModel):
    id: str
    label: str
    description: str = ""
    unit: str = ""
    housing_category: Literal["UH", "MFH", "combined"] = "combined"
    inputs: list[ScorecardMetricInputConfig]
    formula: ScorecardFormulaConfig
    thresholds: ScorecardThresholdConfig
    freshness_days: int = Field(default=90, gt=0)
    required: bool = True


class ScorecardSectionConfig(BaseModel):
    id: str
    label: str
    metrics: list[ScorecardMetricConfig]


class ScorecardTemplateConfig(BaseModel):
    id: str
    name: str
    category: Literal["UH", "MFH", "combined"]
    scope: Literal["enterprise", "majcom", "region", "installation", "market_area"]
    period: Literal["monthly", "quarterly", "annual", "ad_hoc"]
    sections: list[ScorecardSectionConfig]
    export_formats: list[Literal["json", "markdown"]] = Field(default_factory=lambda: ["json", "markdown"])


class ScorecardsConfig(BaseModel):
    templates: list[ScorecardTemplateConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_template_ids(self) -> ScorecardsConfig:
        seen: set[str] = set()
        for template in self.templates:
            if template.id in seen:
                raise ValueError(f"Duplicate scorecard template id: '{template.id}'")
            seen.add(template.id)
            section_ids: set[str] = set()
            for section in template.sections:
                if section.id in section_ids:
                    raise ValueError(f"Duplicate scorecard section id '{section.id}' in template '{template.id}'")
                section_ids.add(section.id)
        return self
```

Then add to `DomainConfig`:

```python
scorecards: ScorecardsConfig = Field(default_factory=ScorecardsConfig)
```

- [ ] **Step 4: Add cross-reference validation for scorecard inputs**

In `DomainConfig._validate_cross_references`, after record feed validation, add:

```python
        feed_names = {feed.name for feed in records_config.feeds}
        for template in self.scorecards.templates:
            for section in template.sections:
                metric_ids: set[str] = set()
                for metric in section.metrics:
                    if metric.id in metric_ids:
                        errors.append(
                            f"Duplicate metric id '{metric.id}' in scorecard section "
                            f"'{section.id}' template '{template.id}'."
                        )
                    metric_ids.add(metric.id)
                    input_names = {metric_input.name for metric_input in metric.inputs}
                    for metric_input in metric.inputs:
                        if metric_input.source == "record_feed" and metric_input.ref not in feed_names:
                            errors.append(
                                f"Scorecard metric '{metric.id}' references unknown "
                                f"records feed '{metric_input.ref}'."
                            )
                    formula_names = {
                        name
                        for name in (
                            metric.formula.numerator,
                            metric.formula.denominator,
                            metric.formula.value,
                            metric.formula.weight,
                        )
                        if name is not None
                    }
                    missing_formula_inputs = formula_names - input_names
                    if missing_formula_inputs:
                        errors.append(
                            f"Scorecard metric '{metric.id}' formula references unknown inputs: "
                            f"{sorted(missing_formula_inputs)}."
                        )
```

- [ ] **Step 5: Add the domain pack**

Create `backend/config/defaults/department_air_force_housing.yaml` with this first pack. Keep it compact; every feed maps an installation and emits an observation:

```yaml
domain:
  name: department_air_force_housing
  display_name: "Department of the Air Force Housing"
  description: "Executive visibility and scorecard automation for accompanied and unaccompanied Air Force housing."

entities:
  - name: installation
    display_label: "Installation"
    icon: building
    natural_key: [installation_id]
    properties:
      installation_id: { type: string, display: "Installation ID", required: true }
      name: { type: string, display: "Name", required: true }
      majcom: { type: string, display: "MAJCOM" }
      state: { type: string, display: "State" }
      latitude: { type: decimal, display: "Latitude" }
      longitude: { type: decimal, display: "Longitude" }
  - name: housing_asset
    display_label: "Housing Asset"
    icon: building
    natural_key: [asset_id]
    properties:
      asset_id: { type: string, display: "Asset ID", required: true }
      installation_id: { type: string, display: "Installation ID", required: true }
      category: { type: enum, display: "Category", enum_values: ["UH", "MFH"], required: true }
      asset_type: { type: string, display: "Asset Type" }
  - name: housing_inventory_snapshot
    display_label: "Inventory Snapshot"
    icon: document
    natural_key: [snapshot_id]
    properties:
      snapshot_id: { type: string, display: "Snapshot ID", required: true }
      installation_id: { type: string, display: "Installation ID", required: true }
      available_units: { type: integer, display: "Available Units", min_value: 0 }
      offline_units: { type: integer, display: "Offline Units", min_value: 0 }
      utilization_rate: { type: decimal, display: "Utilization Rate", min_value: 0, max_value: 1 }
      condition_index: { type: decimal, display: "Condition Index", min_value: 0, max_value: 100 }
      snapshot_date: { type: date, display: "Snapshot Date", required: true }
  - name: population_demand_snapshot
    display_label: "Population Demand Snapshot"
    icon: person
    natural_key: [demand_id]
    properties:
      demand_id: { type: string, display: "Demand ID", required: true }
      installation_id: { type: string, display: "Installation ID", required: true }
      unaccompanied_authorized: { type: integer, display: "Unaccompanied Authorized", min_value: 0 }
      accompanied_authorized: { type: integer, display: "Accompanied Authorized", min_value: 0 }
      snapshot_date: { type: date, display: "Snapshot Date", required: true }
  - name: allowance_market_snapshot
    display_label: "Allowance And Market Snapshot"
    icon: chart
    natural_key: [market_id]
    properties:
      market_id: { type: string, display: "Market ID", required: true }
      installation_id: { type: string, display: "Installation ID", required: true }
      bah_rate: { type: decimal, display: "BAH Rate", min_value: 0 }
      available_rentals: { type: integer, display: "Available Rentals", min_value: 0 }
      affordability_index: { type: decimal, display: "Affordability Index", min_value: 0 }
      snapshot_date: { type: date, display: "Snapshot Date", required: true }
  - name: demographic_snapshot
    display_label: "Demographic Snapshot"
    icon: users
    natural_key: [demographic_id]
    properties:
      demographic_id: { type: string, display: "Demographic ID", required: true }
      installation_id: { type: string, display: "Installation ID", required: true }
      local_population: { type: integer, display: "Local Population", min_value: 0 }
      median_income: { type: decimal, display: "Median Income", min_value: 0 }
      snapshot_date: { type: date, display: "Snapshot Date", required: true }
  - name: resident_experience_snapshot
    display_label: "Resident Experience Snapshot"
    icon: clipboard
    natural_key: [experience_id]
    properties:
      experience_id: { type: string, display: "Experience ID", required: true }
      installation_id: { type: string, display: "Installation ID", required: true }
      satisfaction_score: { type: decimal, display: "Satisfaction Score", min_value: 0, max_value: 100 }
      open_work_orders: { type: integer, display: "Open Work Orders", min_value: 0 }
      snapshot_date: { type: date, display: "Snapshot Date", required: true }
  - name: scorecard_run
    display_label: "Scorecard Run"
    icon: document
    natural_key: [run_id]
    properties:
      run_id: { type: string, display: "Run ID", required: true }
      template_id: { type: string, display: "Template ID", required: true }
      status: { type: string, display: "Status" }

relationships:
  - name: installation_has_asset
    display_label: "Has Asset"
    source: installation
    target: housing_asset
  - name: asset_has_inventory_snapshot
    display_label: "Has Inventory Snapshot"
    source: housing_asset
    target: housing_inventory_snapshot
  - name: installation_has_population_demand
    display_label: "Has Population Demand"
    source: installation
    target: population_demand_snapshot
  - name: installation_has_market_snapshot
    display_label: "Has Market Snapshot"
    source: installation
    target: allowance_market_snapshot
  - name: installation_has_demographic_snapshot
    display_label: "Has Demographic Snapshot"
    source: installation
    target: demographic_snapshot
  - name: scorecard_run_for_installation
    display_label: "Scorecard For Installation"
    source: scorecard_run
    target: installation

capabilities:
  timeseries: true
  gnn: false
  risk_scoring: true
  rag_chat: true
  explainability: true
  structured_ingestion: true
  peer_stats: false

ingestion:
  sources:
    - type: file_upload
      formats: [pdf, docx, txt, csv, json, xlsx]
  chunking:
    strategy: recursive
    chunk_size: 1000
    chunk_overlap: 200
    min_chunk_size: 50

records:
  feeds:
    - name: umd_authorizations
      record_type: umd_authorization
      source: file_upload
      id_field: demand_id
      allow_extra_fields: true
      accepted_formats: [csv, jsonl]
      record_schema:
        demand_id: { type: string, display: "Demand ID", required: true }
        installation_id: { type: string, display: "Installation ID", required: true }
        installation_name: { type: string, display: "Installation Name", required: true }
        majcom: { type: string, display: "MAJCOM" }
        state: { type: string, display: "State" }
        latitude: { type: decimal, display: "Latitude" }
        longitude: { type: decimal, display: "Longitude" }
        unaccompanied_authorized: { type: integer, display: "Unaccompanied Authorized", min_value: 0 }
        accompanied_authorized: { type: integer, display: "Accompanied Authorized", min_value: 0 }
        snapshot_date: { type: date, display: "Snapshot Date", required: true }
      entities:
        - entity_type: installation
          id_field: installation_id
          property_fields:
            installation_id: installation_id
            name: installation_name
            majcom: majcom
            state: state
            latitude: latitude
            longitude: longitude
        - entity_type: population_demand_snapshot
          id_field: demand_id
          property_fields:
            demand_id: demand_id
            installation_id: installation_id
            unaccompanied_authorized: unaccompanied_authorized
            accompanied_authorized: accompanied_authorized
            snapshot_date: snapshot_date
      observations:
        - metric_name: unaccompanied_demand
          entity_type: installation
          score_field: unaccompanied_authorized
          rationale: "Unaccompanied demand from UMD authorization export."
    - name: bah_rates
      record_type: bah_rate
      source: file_upload
      id_field: market_id
      allow_extra_fields: true
      accepted_formats: [csv, jsonl]
      record_schema:
        market_id: { type: string, display: "Market ID", required: true }
        installation_id: { type: string, display: "Installation ID", required: true }
        bah_rate: { type: decimal, display: "BAH Rate", min_value: 0 }
        available_rentals: { type: integer, display: "Available Rentals", min_value: 0 }
        affordability_index: { type: decimal, display: "Affordability Index", min_value: 0 }
        snapshot_date: { type: date, display: "Snapshot Date", required: true }
      entities:
        - entity_type: allowance_market_snapshot
          id_field: market_id
          property_fields:
            market_id: market_id
            installation_id: installation_id
            bah_rate: bah_rate
            available_rentals: available_rentals
            affordability_index: affordability_index
            snapshot_date: snapshot_date
      observations:
        - metric_name: market_pressure
          entity_type: allowance_market_snapshot
          score_field: affordability_index
          rationale: "Market pressure from allowance and rental availability export."
    - name: housing_inventory
      record_type: housing_inventory
      source: file_upload
      id_field: snapshot_id
      allow_extra_fields: true
      accepted_formats: [csv, jsonl]
      record_schema:
        snapshot_id: { type: string, display: "Snapshot ID", required: true }
        asset_id: { type: string, display: "Asset ID", required: true }
        installation_id: { type: string, display: "Installation ID", required: true }
        category: { type: enum, display: "Category", enum_values: ["UH", "MFH"], required: true }
        available_units: { type: integer, display: "Available Units", min_value: 0 }
        offline_units: { type: integer, display: "Offline Units", min_value: 0 }
        utilization_rate: { type: decimal, display: "Utilization Rate", min_value: 0, max_value: 1 }
        condition_index: { type: decimal, display: "Condition Index", min_value: 0, max_value: 100 }
        snapshot_date: { type: date, display: "Snapshot Date", required: true }
      entities:
        - entity_type: housing_asset
          id_field: asset_id
          property_fields:
            asset_id: asset_id
            installation_id: installation_id
            category: category
        - entity_type: housing_inventory_snapshot
          id_field: snapshot_id
          property_fields:
            snapshot_id: snapshot_id
            installation_id: installation_id
            available_units: available_units
            offline_units: offline_units
            utilization_rate: utilization_rate
            condition_index: condition_index
            snapshot_date: snapshot_date
      relationships:
        - relationship_type: asset_has_inventory_snapshot
          source_entity_type: housing_asset
          target_entity_type: housing_inventory_snapshot
      observations:
        - metric_name: housing_condition
          entity_type: housing_inventory_snapshot
          score_field: condition_index
          rationale: "Housing condition index from inventory export."
    - name: market_availability
      record_type: market_availability
      source: file_upload
      id_field: market_id
      allow_extra_fields: true
      accepted_formats: [csv, jsonl]
      record_schema:
        market_id: { type: string, display: "Market ID", required: true }
        installation_id: { type: string, display: "Installation ID", required: true }
        available_rentals: { type: integer, display: "Available Rentals", min_value: 0 }
        affordability_index: { type: decimal, display: "Affordability Index", min_value: 0 }
        snapshot_date: { type: date, display: "Snapshot Date", required: true }
      entities:
        - entity_type: allowance_market_snapshot
          id_field: market_id
          property_fields:
            market_id: market_id
            installation_id: installation_id
            available_rentals: available_rentals
            affordability_index: affordability_index
            snapshot_date: snapshot_date
      observations:
        - metric_name: rental_availability
          entity_type: allowance_market_snapshot
          score_field: available_rentals
          rationale: "Rental availability from market export."
    - name: area_demographics
      record_type: area_demographics
      source: file_upload
      id_field: demographic_id
      allow_extra_fields: true
      accepted_formats: [csv, jsonl]
      record_schema:
        demographic_id: { type: string, display: "Demographic ID", required: true }
        installation_id: { type: string, display: "Installation ID", required: true }
        local_population: { type: integer, display: "Local Population", min_value: 0 }
        median_income: { type: decimal, display: "Median Income", min_value: 0 }
        snapshot_date: { type: date, display: "Snapshot Date", required: true }
      entities:
        - entity_type: demographic_snapshot
          id_field: demographic_id
          property_fields:
            demographic_id: demographic_id
            installation_id: installation_id
            local_population: local_population
            median_income: median_income
            snapshot_date: snapshot_date
      observations:
        - metric_name: demographic_context
          entity_type: demographic_snapshot
          score_field: local_population
          rationale: "Area demographic context from export."

scorecards:
  templates:
    - id: uh_scorecard
      name: "Unaccompanied Housing Scorecard"
      category: UH
      scope: installation
      period: quarterly
      export_formats: [json, markdown]
      sections:
        - id: demand_supply
          label: "Demand And Supply"
          metrics:
            - id: uh_supply_ratio
              label: "UH Supply Ratio"
              description: "Available UH inventory divided by unaccompanied authorized demand."
              unit: ratio
              housing_category: UH
              inputs:
                - { name: supply, source: record_feed, ref: housing_inventory, field: available_units, filter: { category: UH } }
                - { name: demand, source: record_feed, ref: umd_authorizations, field: unaccompanied_authorized }
              formula: { operator: ratio, numerator: supply, denominator: demand }
              thresholds: { pass_min: 1.0, warn_min: 0.9, fail_max: 0.89, incomplete_when_missing: true }
              freshness_days: 90
        - id: condition
          label: "Condition"
          metrics:
            - id: uh_condition_index
              label: "UH Condition Index"
              unit: score
              housing_category: UH
              inputs:
                - { name: condition, source: record_feed, ref: housing_inventory, field: condition_index, filter: { category: UH } }
              formula: { operator: mean, value: condition }
              thresholds: { pass_min: 80, warn_min: 70, fail_max: 69, incomplete_when_missing: true }
              freshness_days: 90
    - id: mfh_scorecard
      name: "Military Family Housing Scorecard"
      category: MFH
      scope: installation
      period: quarterly
      export_formats: [json, markdown]
      sections:
        - id: family_housing_supply
          label: "Family Housing Supply"
          metrics:
            - id: mfh_supply_ratio
              label: "MFH Supply Ratio"
              unit: ratio
              housing_category: MFH
              inputs:
                - { name: supply, source: record_feed, ref: housing_inventory, field: available_units, filter: { category: MFH } }
                - { name: demand, source: record_feed, ref: umd_authorizations, field: accompanied_authorized }
              formula: { operator: ratio, numerator: supply, denominator: demand }
              thresholds: { pass_min: 1.0, warn_min: 0.9, fail_max: 0.89, incomplete_when_missing: true }
              freshness_days: 90
        - id: market_pressure
          label: "Market Pressure"
          metrics:
            - id: mfh_market_affordability
              label: "Market Affordability"
              unit: index
              housing_category: MFH
              inputs:
                - { name: affordability, source: record_feed, ref: market_availability, field: affordability_index }
              formula: { operator: mean, value: affordability }
              thresholds: { pass_min: 80, warn_min: 65, fail_max: 64, incomplete_when_missing: true }
              freshness_days: 90

rag:
  top_k: 5
  expansion_depth: 2
  reranking_enabled: false
  system_prompt_template: "You are an executive housing data assistant for {domain_name}. Cite source rows and documents when answering questions about installations, UH, MFH, scorecards, and data completeness."

alerts:
  thresholds:
    installation:
      housing_health: 0.75

ui:
  default_entity_type: installation
  navigation:
    pages:
      - { id: housing, label: "Housing", route: /housing, capability: risk_scoring }
      - { id: knowledge_bases, label: "Knowledge Bases", route: /knowledge-bases }
      - { id: rag_chat, label: "Ask Housing Data", route: /rag-chat, capability: rag_chat }
      - { id: configuration, label: "Configuration", route: /configuration }
  display_fields:
    installation: { title: name, subtitle: majcom, chips: [state] }
    housing_asset: { title: asset_id, subtitle: category, chips: [installation_id] }
    housing_inventory_snapshot: { title: snapshot_id, subtitle: installation_id, chips: [snapshot_date] }
    population_demand_snapshot: { title: demand_id, subtitle: installation_id, chips: [snapshot_date] }
    allowance_market_snapshot: { title: market_id, subtitle: installation_id, chips: [snapshot_date] }
    demographic_snapshot: { title: demographic_id, subtitle: installation_id, chips: [snapshot_date] }
    resident_experience_snapshot: { title: experience_id, subtitle: installation_id, chips: [snapshot_date] }
    scorecard_run: { title: run_id, subtitle: template_id, chips: [status] }
  roles:
    executive:
      landing_page: housing
      pages: [housing, knowledge_bases, rag_chat, configuration]
      permissions: [view:housing, generate:scorecards]
```

- [ ] **Step 6: Add fixture CSV files**

Create `docs/testing/knowledge_base_fixtures/air_force_housing/umd_sample.csv`:

```csv
demand_id,installation_id,installation_name,majcom,state,latitude,longitude,unaccompanied_authorized,accompanied_authorized,snapshot_date
umd-edwards-2026q1,edwards_afb,Edwards AFB,AFMC,CA,34.9054,-117.8837,1250,820,2026-03-31
umd-eglin-2026q1,eglin_afb,Eglin AFB,AFMC,FL,30.4832,-86.5254,980,1040,2026-03-31
```

Create `docs/testing/knowledge_base_fixtures/air_force_housing/inventory_sample.csv`:

```csv
snapshot_id,asset_id,installation_id,category,available_units,offline_units,utilization_rate,condition_index,snapshot_date
inv-edwards-uh-2026q1,edwards-dorms,edwards_afb,UH,1120,90,0.96,72,2026-03-31
inv-edwards-mfh-2026q1,edwards-family,edwards_afb,MFH,760,25,0.94,84,2026-03-31
inv-eglin-uh-2026q1,eglin-dorms,eglin_afb,UH,1030,35,0.89,88,2026-03-31
inv-eglin-mfh-2026q1,eglin-family,eglin_afb,MFH,910,45,0.91,76,2026-03-31
```

Create `docs/testing/knowledge_base_fixtures/air_force_housing/market_sample.csv`:

```csv
market_id,installation_id,available_rentals,affordability_index,snapshot_date
market-edwards-2026q1,edwards_afb,220,61,2026-03-31
market-eglin-2026q1,eglin_afb,340,78,2026-03-31
```

Create `docs/testing/knowledge_base_fixtures/air_force_housing/bah_sample.csv`:

```csv
market_id,installation_id,bah_rate,available_rentals,affordability_index,snapshot_date
bah-edwards-2026q1,edwards_afb,2500,220,61,2026-03-31
bah-eglin-2026q1,eglin_afb,2100,340,78,2026-03-31
```

Create `docs/testing/knowledge_base_fixtures/air_force_housing/demographics_sample.csv`:

```csv
demographic_id,installation_id,local_population,median_income,snapshot_date
demo-edwards-2026q1,edwards_afb,612000,73100,2026-03-31
demo-eglin-2026q1,eglin_afb,309000,68400,2026-03-31
```

Create `docs/testing/knowledge_base_fixtures/air_force_housing/README.md`:

```markdown
# Air Force Housing Fixtures

Small file/export fixtures for the Department of the Air Force housing scorecard workflow.

- `umd_sample.csv` feeds `umd_authorizations`.
- `inventory_sample.csv` feeds `housing_inventory`.
- `market_sample.csv` feeds `market_availability`.
- `bah_sample.csv` feeds `bah_rates`.
- `demographics_sample.csv` feeds `area_demographics`.

These are synthetic examples for local tests and demos. They are not official Air Force data.
```

- [ ] **Step 7: Run config tests**

Run:

```bash
uv run --project backend pytest backend/tests/config/test_air_force_housing_pack.py backend/tests/config/test_schema.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/config/schema.py backend/config/defaults/department_air_force_housing.yaml backend/tests/config/test_air_force_housing_pack.py docs/testing/knowledge_base_fixtures/air_force_housing docs/testing/DATA.md backend/config/README.md
git commit -m "feat(config): add Air Force housing scorecard domain pack"
```

---

### Task 2: Scorecard Evaluator And Service Models

**Files:**
- Create: `backend/scorecards/models.py`
- Create: `backend/scorecards/service_models.py`
- Create: `backend/scorecards/evaluation.py`
- Create: `backend/scorecards/exceptions.py`
- Create: `backend/scorecards/__init__.py`
- Create: `backend/tests/scorecards/test_evaluation.py`

- [ ] **Step 1: Write evaluator tests**

Create `backend/tests/scorecards/test_evaluation.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timezone

from config.schema import (
    ScorecardFormulaConfig,
    ScorecardMetricConfig,
    ScorecardMetricInputConfig,
    ScorecardSectionConfig,
    ScorecardTemplateConfig,
    ScorecardThresholdConfig,
)
from scorecards.evaluation import ScorecardEvalState, SourceRecord, evaluate_template


def _template() -> ScorecardTemplateConfig:
    return ScorecardTemplateConfig(
        id="uh_scorecard",
        name="UH Scorecard",
        category="UH",
        scope="installation",
        period="quarterly",
        sections=[
            ScorecardSectionConfig(
                id="demand_supply",
                label="Demand And Supply",
                metrics=[
                    ScorecardMetricConfig(
                        id="uh_supply_ratio",
                        label="UH Supply Ratio",
                        inputs=[
                            ScorecardMetricInputConfig(name="supply", source="record_feed", ref="housing_inventory", field="available_units", filter={"category": "UH"}),
                            ScorecardMetricInputConfig(name="demand", source="record_feed", ref="umd_authorizations", field="unaccompanied_authorized"),
                        ],
                        formula=ScorecardFormulaConfig(operator="ratio", numerator="supply", denominator="demand"),
                        thresholds=ScorecardThresholdConfig(pass_min=1.0, warn_min=0.9, fail_max=0.89),
                    )
                ],
            )
        ],
    )


def test_evaluate_ratio_metric_warns_when_under_supply() -> None:
    state = ScorecardEvalState(
        scope_type="installation",
        scope_id="edwards_afb",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        source_records=[
            SourceRecord(feed_name="housing_inventory", record_id="inv-1", observed_at=datetime(2026, 3, 31, tzinfo=timezone.utc), values={"installation_id": "edwards_afb", "category": "UH", "available_units": 1120}),
            SourceRecord(feed_name="umd_authorizations", record_id="umd-1", observed_at=datetime(2026, 3, 31, tzinfo=timezone.utc), values={"installation_id": "edwards_afb", "unaccompanied_authorized": 1250}),
        ],
    )

    result = evaluate_template(_template(), state)

    metric = result.sections[0].metrics[0]
    assert metric.metric_id == "uh_supply_ratio"
    assert metric.value == 0.896
    assert metric.health == "warn"
    assert metric.completeness == "complete"
    assert {citation.source_ref for citation in metric.citations} == {"housing_inventory:inv-1", "umd_authorizations:umd-1"}


def test_missing_required_input_marks_metric_incomplete() -> None:
    state = ScorecardEvalState(
        scope_type="installation",
        scope_id="edwards_afb",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        source_records=[],
    )

    result = evaluate_template(_template(), state)

    metric = result.sections[0].metrics[0]
    assert metric.value is None
    assert metric.health == "incomplete"
    assert metric.completeness == "missing_source"
    assert "housing_inventory" in metric.warnings[0]


def test_stale_input_marks_metric_warning() -> None:
    state = ScorecardEvalState(
        scope_type="installation",
        scope_id="edwards_afb",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        source_records=[
            SourceRecord(feed_name="housing_inventory", record_id="inv-1", observed_at=datetime(2025, 1, 1, tzinfo=timezone.utc), values={"installation_id": "edwards_afb", "category": "UH", "available_units": 1120}),
            SourceRecord(feed_name="umd_authorizations", record_id="umd-1", observed_at=datetime(2026, 6, 30, tzinfo=timezone.utc), values={"installation_id": "edwards_afb", "unaccompanied_authorized": 1250}),
        ],
    )

    result = evaluate_template(_template(), state)

    metric = result.sections[0].metrics[0]
    assert metric.completeness == "stale_source"
    assert metric.health == "warn"
```

- [ ] **Step 2: Run the failing evaluator tests**

Run:

```bash
uv run --project backend pytest backend/tests/scorecards/test_evaluation.py -q
```

Expected: fail because `scorecards` package does not exist.

- [ ] **Step 3: Add scorecard models**

Create `backend/scorecards/models.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from shared.utils import utc_now

ScorecardHealth = Literal["pass", "warn", "fail", "incomplete"]
ScorecardCompleteness = Literal["complete", "missing_source", "stale_source", "formula_error"]
ScorecardRunStatus = Literal["generated", "failed", "superseded"]
ScorecardExportFormat = Literal["json", "markdown"]


class ScorecardCitation(BaseModel):
    source_ref: str
    title: str
    excerpt: str | None = None


class ScorecardMetricResult(BaseModel):
    metric_id: str
    label: str
    value: float | None = None
    unit: str = ""
    health: ScorecardHealth
    completeness: ScorecardCompleteness
    warnings: list[str] = Field(default_factory=lambda: cast(list[str], []))
    citations: list[ScorecardCitation] = Field(default_factory=lambda: cast(list[ScorecardCitation], []))


class ScorecardSectionResult(BaseModel):
    section_id: str
    label: str
    health: ScorecardHealth
    metrics: list[ScorecardMetricResult]


class ScorecardRun(BaseModel):
    id: str
    knowledge_base_id: str
    template_id: str
    template_name: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date
    source_snapshot_hash: str
    status: ScorecardRunStatus = "generated"
    overall_health: ScorecardHealth = "incomplete"
    sections: list[ScorecardSectionResult] = Field(default_factory=lambda: cast(list[ScorecardSectionResult], []))
    export_payloads: dict[ScorecardExportFormat, str] = Field(default_factory=lambda: cast(dict[ScorecardExportFormat, str], {}))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "ScorecardCitation",
    "ScorecardCompleteness",
    "ScorecardExportFormat",
    "ScorecardHealth",
    "ScorecardMetricResult",
    "ScorecardRun",
    "ScorecardRunStatus",
    "ScorecardSectionResult",
]
```

Create `backend/scorecards/exceptions.py`:

```python
from __future__ import annotations


class ScorecardError(Exception):
    """Base exception for scorecard failures."""


class ScorecardTemplateNotFoundError(ScorecardError):
    def __init__(self, template_id: str) -> None:
        super().__init__(f"Scorecard template '{template_id}' was not found.")
        self.template_id = template_id


class ScorecardRunNotFoundError(ScorecardError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"Scorecard run '{run_id}' was not found.")
        self.run_id = run_id


class ScorecardPersistenceError(ScorecardError):
    """Raised when scorecard persistence fails."""
```

- [ ] **Step 4: Add evaluator implementation**

Create `backend/scorecards/evaluation.py` with deterministic, bounded operators:

```python
from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import mean
from typing import cast

from pydantic import BaseModel, Field

from config.schema import ScorecardMetricConfig, ScorecardTemplateConfig
from scorecards.models import (
    ScorecardCitation,
    ScorecardCompleteness,
    ScorecardHealth,
    ScorecardMetricResult,
    ScorecardSectionResult,
)


class SourceRecord(BaseModel):
    feed_name: str
    record_id: str
    observed_at: datetime
    values: dict[str, str | float | int | bool] = Field(default_factory=dict)


class ScorecardEvalState(BaseModel):
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date
    source_records: list[SourceRecord] = Field(default_factory=list)


class ScorecardEvaluationResult(BaseModel):
    template_id: str
    template_name: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date
    overall_health: ScorecardHealth
    sections: list[ScorecardSectionResult]


def evaluate_template(template: ScorecardTemplateConfig, state: ScorecardEvalState) -> ScorecardEvaluationResult:
    sections = [_evaluate_section(section, state) for section in template.sections]
    return ScorecardEvaluationResult(
        template_id=template.id,
        template_name=template.name,
        scope_type=state.scope_type,
        scope_id=state.scope_id,
        period_start=state.period_start,
        period_end=state.period_end,
        overall_health=_combine_health([section.health for section in sections]),
        sections=sections,
    )


def _evaluate_section(section: object, state: ScorecardEvalState) -> ScorecardSectionResult:
    section_id = getattr(section, "id")
    label = getattr(section, "label")
    metrics = [_evaluate_metric(metric, state) for metric in getattr(section, "metrics")]
    return ScorecardSectionResult(
        section_id=section_id,
        label=label,
        health=_combine_health([metric.health for metric in metrics]),
        metrics=metrics,
    )


def _evaluate_metric(metric: ScorecardMetricConfig, state: ScorecardEvalState) -> ScorecardMetricResult:
    selected: dict[str, list[SourceRecord]] = {}
    warnings: list[str] = []
    stale = False
    for metric_input in metric.inputs:
        rows = [
            row
            for row in state.source_records
            if row.feed_name == metric_input.ref and _record_matches(row, metric_input.filter)
        ]
        if not rows:
            warnings.append(f"Missing required source '{metric_input.ref}' for input '{metric_input.name}'.")
        if any(_is_stale(row.observed_at, state.period_end, metric.freshness_days) for row in rows):
            stale = True
            warnings.append(f"Source '{metric_input.ref}' is older than {metric.freshness_days} days.")
        selected[metric_input.name] = rows
    if warnings and any("Missing required source" in warning for warning in warnings):
        return _metric_result(metric, None, "incomplete", "missing_source", warnings, [])
    values = {
        metric_input.name: _input_values(selected[metric_input.name], metric_input.field)
        for metric_input in metric.inputs
    }
    try:
        value = _calculate(metric, values)
    except (KeyError, TypeError, ZeroDivisionError, ValueError) as exc:
        return _metric_result(metric, None, "incomplete", "formula_error", [f"Formula failed: {exc}"], _citations(selected))
    health = _health(metric, value)
    completeness: ScorecardCompleteness = "stale_source" if stale else "complete"
    if stale and health == "pass":
        health = "warn"
    return _metric_result(metric, value, health, completeness, warnings, _citations(selected))


def _record_matches(row: SourceRecord, filters: dict[str, str | float | int | bool]) -> bool:
    return all(row.values.get(key) == expected for key, expected in filters.items())


def _is_stale(observed_at: datetime, period_end: date, freshness_days: int) -> bool:
    end = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)
    observed = observed_at if observed_at.tzinfo is not None else observed_at.replace(tzinfo=timezone.utc)
    return (end - observed).days > freshness_days


def _input_values(rows: list[SourceRecord], field: str | None) -> list[float]:
    if field is None:
        return []
    out: list[float] = []
    for row in rows:
        raw = row.values.get(field)
        if isinstance(raw, bool) or raw is None:
            continue
        if isinstance(raw, (int, float)):
            out.append(float(raw))
        elif isinstance(raw, str):
            out.append(float(raw))
    return out


def _calculate(metric: ScorecardMetricConfig, values: dict[str, list[float]]) -> float:
    formula = metric.formula
    if formula.operator == "ratio":
        numerator = sum(values[cast(str, formula.numerator)])
        denominator = sum(values[cast(str, formula.denominator)])
        return round(numerator / denominator, 3)
    if formula.operator == "sum":
        return round(sum(values[cast(str, formula.value)]), 3)
    if formula.operator == "mean":
        return round(mean(values[cast(str, formula.value)]), 3)
    if formula.operator == "latest":
        series = values[cast(str, formula.value)]
        return round(series[-1], 3)
    if formula.operator == "weighted_mean":
        vals = values[cast(str, formula.value)]
        weights = values[cast(str, formula.weight)]
        total_weight = sum(weights)
        return round(sum(value * weight for value, weight in zip(vals, weights, strict=False)) / total_weight, 3)
    raise ValueError(f"Unsupported formula operator '{formula.operator}'.")


def _health(metric: ScorecardMetricConfig, value: float) -> ScorecardHealth:
    thresholds = metric.thresholds
    if thresholds.fail_max is not None and value <= thresholds.fail_max:
        return "fail"
    if thresholds.pass_min is not None and value >= thresholds.pass_min:
        return "pass"
    return "warn"


def _metric_result(
    metric: ScorecardMetricConfig,
    value: float | None,
    health: ScorecardHealth,
    completeness: ScorecardCompleteness,
    warnings: list[str],
    citations: list[ScorecardCitation],
) -> ScorecardMetricResult:
    return ScorecardMetricResult(
        metric_id=metric.id,
        label=metric.label,
        value=value,
        unit=metric.unit,
        health=health,
        completeness=completeness,
        warnings=warnings,
        citations=citations,
    )


def _citations(selected: dict[str, list[SourceRecord]]) -> list[ScorecardCitation]:
    citations: list[ScorecardCitation] = []
    for feed_name, rows in selected.items():
        for row in rows:
            citations.append(
                ScorecardCitation(
                    source_ref=f"{feed_name}:{row.record_id}",
                    title=f"{feed_name} row {row.record_id}",
                )
            )
    return citations


def _combine_health(values: list[ScorecardHealth]) -> ScorecardHealth:
    if "fail" in values:
        return "fail"
    if "incomplete" in values:
        return "incomplete"
    if "warn" in values:
        return "warn"
    return "pass"
```

- [ ] **Step 5: Add service DTOs**

Create `backend/scorecards/service_models.py`:

```python
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from scorecards.models import ScorecardExportFormat, ScorecardRun, ScorecardRunStatus


class ScorecardGenerateRequest(BaseModel):
    knowledge_base_id: str
    template_id: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date


class ScorecardRunListRequest(BaseModel):
    knowledge_base_id: str
    template_id: str | None = None
    status: ScorecardRunStatus | None = None
    limit: int = 50
    offset: int = 0


class ScorecardTemplateSummary(BaseModel):
    id: str
    name: str
    category: str
    scope: str
    period: str


class ScorecardTemplateListResponse(BaseModel):
    items: list[ScorecardTemplateSummary]


class ScorecardRunListResponse(BaseModel):
    items: list[ScorecardRun]
    total: int


class ScorecardExportResponse(BaseModel):
    run_id: str
    format: ScorecardExportFormat
    content: str
```

Create `backend/scorecards/__init__.py`:

```python
from scorecards.models import ScorecardRun
from scorecards.service import ScorecardService, create_scorecard_service

__all__ = ["ScorecardRun", "ScorecardService", "create_scorecard_service"]
```

- [ ] **Step 6: Run evaluator tests**

Run:

```bash
uv run --project backend pytest backend/tests/scorecards/test_evaluation.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/scorecards backend/tests/scorecards/test_evaluation.py
git commit -m "feat(scorecards): add deterministic scorecard evaluator"
```

---

### Task 3: Scorecard Service, Repository, And Persistence

**Files:**
- Create: `backend/scorecards/adapters/protocols.py`
- Create: `backend/scorecards/adapters/in_memory.py`
- Create: `backend/scorecards/adapters/postgres.py`
- Create: `backend/scorecards/adapters/__init__.py`
- Create: `backend/scorecards/protocols.py`
- Create: `backend/scorecards/service.py`
- Create: `backend/database/migrations/versions/0008_scorecards.py`
- Create: `backend/tests/scorecards/test_in_memory_store.py`
- Create: `backend/tests/scorecards/test_service.py`
- Create: `backend/tests/scorecards/test_postgres_store.py`
- Modify: `backend/api/_kb_cleanup.py`

- [ ] **Step 1: Write repository and service tests**

Create `backend/tests/scorecards/test_in_memory_store.py`:

```python
from __future__ import annotations

from datetime import date

from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.models import ScorecardRun


def _run(run_id: str = "run-1", snapshot: str = "hash-1") -> ScorecardRun:
    return ScorecardRun(
        id=run_id,
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        template_name="UH Scorecard",
        scope_type="installation",
        scope_id="edwards_afb",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        source_snapshot_hash=snapshot,
    )


def test_upsert_reuses_natural_key() -> None:
    repo = InMemoryScorecardRunRepository()
    first = repo.upsert(_run("run-1"))
    second = repo.upsert(_run("run-2"))
    assert second.id == first.id
    assert repo.list(knowledge_base_id="kb-1", limit=10, offset=0)[1] == 1


def test_delete_by_kb_removes_runs() -> None:
    repo = InMemoryScorecardRunRepository()
    repo.upsert(_run())
    assert repo.delete_by_kb("kb-1") == 1
    assert repo.get(knowledge_base_id="kb-1", run_id="run-1") is None
```

Create `backend/tests/scorecards/test_service.py`:

```python
from __future__ import annotations

from datetime import date

from config.schema import DomainConfig
from config.loader import load_config
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.service import ScorecardService


def test_service_lists_templates_from_config() -> None:
    config = load_config("config/defaults/department_air_force_housing.yaml")
    service = ScorecardService(repository=InMemoryScorecardRunRepository(), config=config)
    templates = service.list_templates()
    assert {item.id for item in templates.items} == {"uh_scorecard", "mfh_scorecard"}


def test_service_generates_run_with_export_payloads() -> None:
    config: DomainConfig = load_config("config/defaults/department_air_force_housing.yaml")
    service = ScorecardService(repository=InMemoryScorecardRunRepository(), config=config)
    run = service.generate(
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        scope_type="installation",
        scope_id="edwards_afb",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
    )
    assert run.template_id == "uh_scorecard"
    assert "json" in run.export_payloads
    assert "markdown" in run.export_payloads
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run --project backend pytest backend/tests/scorecards/test_in_memory_store.py backend/tests/scorecards/test_service.py -q
```

Expected: fail because repository and service do not exist.

- [ ] **Step 3: Implement repository protocol and in-memory adapter**

Create `backend/scorecards/adapters/protocols.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from scorecards.models import ScorecardRun, ScorecardRunStatus


@runtime_checkable
class ScorecardRunRepository(Protocol):
    def upsert(self, run: ScorecardRun) -> ScorecardRun: ...
    def get(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun | None: ...
    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        template_id: str | None = None,
        status: ScorecardRunStatus | None = None,
    ) -> tuple[list[ScorecardRun], int]: ...
    def delete_by_kb(self, knowledge_base_id: str) -> int: ...
```

Create `backend/scorecards/adapters/in_memory.py`:

```python
from __future__ import annotations

from scorecards.adapters.protocols import ScorecardRunRepository
from scorecards.models import ScorecardRun, ScorecardRunStatus


class InMemoryScorecardRunRepository:
    def __init__(self) -> None:
        self._by_id: dict[tuple[str, str], ScorecardRun] = {}
        self._natural: dict[tuple[str, str, str, str, str, str], str] = {}

    def upsert(self, run: ScorecardRun) -> ScorecardRun:
        key = _natural_key(run)
        existing_id = self._natural.get(key)
        if existing_id is not None:
            existing = self._by_id[(run.knowledge_base_id, existing_id)]
            return existing
        self._natural[key] = run.id
        self._by_id[(run.knowledge_base_id, run.id)] = run
        return run

    def get(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun | None:
        return self._by_id.get((knowledge_base_id, run_id))

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        template_id: str | None = None,
        status: ScorecardRunStatus | None = None,
    ) -> tuple[list[ScorecardRun], int]:
        items = [
            run
            for (kb_id, _), run in self._by_id.items()
            if kb_id == knowledge_base_id
            and (template_id is None or run.template_id == template_id)
            and (status is None or run.status == status)
        ]
        items.sort(key=lambda run: (run.created_at, run.id), reverse=True)
        return items[offset : offset + limit], len(items)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._by_id if key[0] == knowledge_base_id]
        for key in keys:
            run = self._by_id.pop(key)
            self._natural.pop(_natural_key(run), None)
        return len(keys)


def _natural_key(run: ScorecardRun) -> tuple[str, str, str, str, str, str]:
    return (
        run.knowledge_base_id,
        run.template_id,
        run.scope_type,
        run.scope_id,
        f"{run.period_start.isoformat()}:{run.period_end.isoformat()}",
        run.source_snapshot_hash,
    )


__all__ = ["InMemoryScorecardRunRepository"]
```

Create `backend/scorecards/adapters/__init__.py`:

```python
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.adapters.protocols import ScorecardRunRepository

__all__ = ["InMemoryScorecardRunRepository", "ScorecardRunRepository"]
```

- [ ] **Step 4: Implement service**

Create `backend/scorecards/protocols.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from scorecards.models import ScorecardExportFormat, ScorecardRun
from scorecards.service_models import ScorecardExportResponse, ScorecardRunListResponse, ScorecardTemplateListResponse


@runtime_checkable
class ScorecardServiceProtocol(Protocol):
    def list_templates(self) -> ScorecardTemplateListResponse: ...
    def generate(
        self,
        *,
        knowledge_base_id: str,
        template_id: str,
        scope_type: str,
        scope_id: str,
        period_start: date,
        period_end: date,
    ) -> ScorecardRun: ...
    def list_runs(self, *, knowledge_base_id: str, template_id: str | None, limit: int, offset: int) -> ScorecardRunListResponse: ...
    def get_run(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun | None: ...
    def export_run(self, *, knowledge_base_id: str, run_id: str, format: ScorecardExportFormat) -> ScorecardExportResponse: ...
```

Create `backend/scorecards/service.py`:

```python
from __future__ import annotations

import hashlib
import json
from datetime import date

from config.schema import DomainConfig, ScorecardTemplateConfig
from scorecards.adapters.protocols import ScorecardRunRepository
from scorecards.evaluation import ScorecardEvalState, evaluate_template
from scorecards.exceptions import ScorecardRunNotFoundError, ScorecardTemplateNotFoundError
from scorecards.models import ScorecardExportFormat, ScorecardRun
from scorecards.service_models import ScorecardExportResponse, ScorecardRunListResponse, ScorecardTemplateListResponse, ScorecardTemplateSummary
from shared.utils import generate_id, utc_now


class ScorecardService:
    def __init__(self, *, repository: ScorecardRunRepository, config: DomainConfig) -> None:
        self._repository = repository
        self._config = config

    def list_templates(self) -> ScorecardTemplateListResponse:
        return ScorecardTemplateListResponse(
            items=[
                ScorecardTemplateSummary(
                    id=template.id,
                    name=template.name,
                    category=template.category,
                    scope=template.scope,
                    period=template.period,
                )
                for template in self._config.scorecards.templates
            ]
        )

    def get_template(self, template_id: str) -> ScorecardTemplateConfig:
        for template in self._config.scorecards.templates:
            if template.id == template_id:
                return template
        raise ScorecardTemplateNotFoundError(template_id)

    def generate(
        self,
        *,
        knowledge_base_id: str,
        template_id: str,
        scope_type: str,
        scope_id: str,
        period_start: date,
        period_end: date,
    ) -> ScorecardRun:
        template = self.get_template(template_id)
        snapshot_hash = _source_snapshot_hash(knowledge_base_id, template_id, scope_type, scope_id, period_start, period_end)
        evaluation = evaluate_template(
            template,
            ScorecardEvalState(
                scope_type=scope_type,
                scope_id=scope_id,
                period_start=period_start,
                period_end=period_end,
                source_records=[],
            ),
        )
        now = utc_now()
        run = ScorecardRun(
            id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            template_id=template.id,
            template_name=template.name,
            scope_type=scope_type,
            scope_id=scope_id,
            period_start=period_start,
            period_end=period_end,
            source_snapshot_hash=snapshot_hash,
            overall_health=evaluation.overall_health,
            sections=evaluation.sections,
            export_payloads={},
            created_at=now,
            updated_at=now,
        )
        run.export_payloads["json"] = run.model_dump_json()
        run.export_payloads["markdown"] = _markdown_export(run)
        return self._repository.upsert(run)

    def list_runs(self, *, knowledge_base_id: str, template_id: str | None, limit: int, offset: int) -> ScorecardRunListResponse:
        items, total = self._repository.list(
            knowledge_base_id=knowledge_base_id,
            template_id=template_id,
            limit=limit,
            offset=offset,
        )
        return ScorecardRunListResponse(items=items, total=total)

    def get_run(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun | None:
        return self._repository.get(knowledge_base_id=knowledge_base_id, run_id=run_id)

    def export_run(self, *, knowledge_base_id: str, run_id: str, format: ScorecardExportFormat) -> ScorecardExportResponse:
        run = self.get_run(knowledge_base_id=knowledge_base_id, run_id=run_id)
        if run is None:
            raise ScorecardRunNotFoundError(run_id)
        return ScorecardExportResponse(run_id=run.id, format=format, content=run.export_payloads[format])


def create_scorecard_service(*, repository: ScorecardRunRepository, config: DomainConfig) -> ScorecardService:
    return ScorecardService(repository=repository, config=config)


def _source_snapshot_hash(
    knowledge_base_id: str,
    template_id: str,
    scope_type: str,
    scope_id: str,
    period_start: date,
    period_end: date,
) -> str:
    payload = {
        "knowledge_base_id": knowledge_base_id,
        "template_id": template_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _markdown_export(run: ScorecardRun) -> str:
    lines = [f"# {run.template_name}", "", f"Scope: {run.scope_type} {run.scope_id}", f"Overall health: {run.overall_health}", ""]
    for section in run.sections:
        lines.append(f"## {section.label}")
        lines.append(f"Health: {section.health}")
        for metric in section.metrics:
            value = "incomplete" if metric.value is None else f"{metric.value:g} {metric.unit}".strip()
            lines.append(f"- {metric.label}: {value} ({metric.health})")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 5: Add Postgres migration and adapter**

Create `backend/database/migrations/versions/0008_scorecards.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_scorecards"
down_revision: str | None = "0007_case_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE scorecard_runs (
            run_id               text        NOT NULL,
            knowledge_base_id    text        NOT NULL,
            template_id          text        NOT NULL,
            template_name        text        NOT NULL,
            scope_type           text        NOT NULL,
            scope_id             text        NOT NULL,
            period_start         date        NOT NULL,
            period_end           date        NOT NULL,
            source_snapshot_hash text        NOT NULL,
            status               text        NOT NULL,
            overall_health       text        NOT NULL,
            sections             jsonb       NOT NULL,
            export_payloads      jsonb       NOT NULL,
            created_at           timestamptz NOT NULL,
            updated_at           timestamptz NOT NULL,
            PRIMARY KEY (knowledge_base_id, run_id),
            UNIQUE (
                knowledge_base_id, template_id, scope_type, scope_id,
                period_start, period_end, source_snapshot_hash
            )
        )
        """
    )
    op.execute("CREATE INDEX scorecard_runs_kb_template_idx ON scorecard_runs (knowledge_base_id, template_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scorecard_runs")
```

Create `backend/scorecards/adapters/postgres.py` following `policy/adapters/postgres.py`: serialize `sections` and `export_payloads` as JSONB, `INSERT ... ON CONFLICT DO NOTHING` for the natural key, and `SELECT` the existing row when conflict occurs. The row-to-model function must validate sections with `ScorecardSectionResult.model_validate(item)`.

- [ ] **Step 6: Add KB cleanup hook**

In `backend/api/_kb_cleanup.py`, import the scorecard repository dependency and add it to the cleanup sequence:

```python
from scorecards.adapters.protocols import ScorecardRunRepository
```

Add dependency:

```python
scorecard_repository: ScorecardRunRepository = Depends(get_scorecard_run_repository),
```

Call:

```python
scorecard_repository.delete_by_kb(kb_id)
```

- [ ] **Step 7: Run service/repository tests**

Run:

```bash
uv run --project backend pytest backend/tests/scorecards/test_in_memory_store.py backend/tests/scorecards/test_service.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/scorecards backend/tests/scorecards backend/database/migrations/versions/0008_scorecards.py backend/api/_kb_cleanup.py
git commit -m "feat(scorecards): persist generated scorecard runs"
```

---

### Task 4: Scorecards And Housing APIs

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/app.py`
- Create: `backend/api/routers/scorecards.py`
- Create: `backend/api/routers/housing.py`
- Create: `backend/tests/api/test_scorecards_router.py`
- Create: `backend/tests/api/test_housing_router.py`

- [ ] **Step 1: Write API tests**

Create `backend/tests/api/test_scorecards_router.py`:

```python
from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.scorecards import router
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.service import ScorecardService
from config.loader import load_config
from api.dependencies import get_scorecard_service


def _service() -> ScorecardService:
    return ScorecardService(
        repository=InMemoryScorecardRunRepository(),
        config=load_config("config/defaults/department_air_force_housing.yaml"),
    )


def test_lists_scorecard_templates() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_scorecard_service] = _service
    client = TestClient(app)

    response = client.get("/scorecards/templates")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {"uh_scorecard", "mfh_scorecard"}


def test_generates_and_exports_scorecard_run() -> None:
    service = _service()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_scorecard_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/scorecards/runs",
        json={
            "knowledge_base_id": "kb-1",
            "template_id": "uh_scorecard",
            "scope_type": "installation",
            "scope_id": "edwards_afb",
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
        },
    )

    assert response.status_code == 200
    run_id = response.json()["id"]
    export = client.get(f"/scorecards/runs/{run_id}/export?knowledge_base_id=kb-1&format=markdown")
    assert export.status_code == 200
    assert "UH Scorecard" in export.json()["content"]
```

Create `backend/tests/api/test_housing_router.py`:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.housing import router


def test_housing_overview_returns_executive_kpis() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/housing/overview?period_start=2026-01-01&period_end=2026-03-31")

    assert response.status_code == 200
    payload = response.json()
    assert payload["installations_total"] >= 0
    assert "uh_readiness" in payload
    assert "mfh_readiness" in payload


def test_housing_installations_returns_map_rows() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/housing/installations?period_start=2026-01-01&period_end=2026-03-31")

    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)
```

- [ ] **Step 2: Run failing API tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_scorecards_router.py backend/tests/api/test_housing_router.py -q
```

Expected: fail because routes and dependencies do not exist.

- [ ] **Step 3: Add API contract models**

In `backend/api/contracts.py`, add:

```python
from datetime import date
```

Add models:

```python
class ScorecardGenerateRequest(BaseModel):
    knowledge_base_id: str
    template_id: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date


class ScorecardTemplateSummaryResponse(BaseModel):
    id: str
    name: str
    category: str
    scope: str
    period: str


class ScorecardTemplateListResponse(BaseModel):
    items: list[ScorecardTemplateSummaryResponse] = Field(default_factory=list)


class ScorecardCitationResponse(BaseModel):
    source_ref: str
    title: str
    excerpt: str | None = None


class ScorecardMetricResultResponse(BaseModel):
    metric_id: str
    label: str
    value: float | None = None
    unit: str
    health: Literal["pass", "warn", "fail", "incomplete"]
    completeness: Literal["complete", "missing_source", "stale_source", "formula_error"]
    warnings: list[str] = Field(default_factory=list)
    citations: list[ScorecardCitationResponse] = Field(default_factory=list)


class ScorecardSectionResultResponse(BaseModel):
    section_id: str
    label: str
    health: Literal["pass", "warn", "fail", "incomplete"]
    metrics: list[ScorecardMetricResultResponse] = Field(default_factory=list)


class ScorecardRunResponse(BaseModel):
    id: str
    knowledge_base_id: str
    template_id: str
    template_name: str
    scope_type: str
    scope_id: str
    period_start: date
    period_end: date
    source_snapshot_hash: str
    status: Literal["generated", "failed", "superseded"]
    overall_health: Literal["pass", "warn", "fail", "incomplete"]
    sections: list[ScorecardSectionResultResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ScorecardRunListResponse(BaseModel):
    items: list[ScorecardRunResponse] = Field(default_factory=list)
    total: int = Field(ge=0)


class ScorecardExportResponse(BaseModel):
    run_id: str
    format: Literal["json", "markdown"]
    content: str


class HousingOverviewResponse(BaseModel):
    installations_total: int = Field(ge=0)
    critical_installations: int = Field(ge=0)
    watch_installations: int = Field(ge=0)
    supply_gap: float
    uh_readiness: float = Field(ge=0.0, le=1.0)
    mfh_readiness: float = Field(ge=0.0, le=1.0)
    stale_sources: int = Field(ge=0)
    missing_sources: int = Field(ge=0)


class HousingInstallationMapItem(BaseModel):
    installation_id: str
    name: str
    majcom: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    health: Literal["pass", "warn", "fail", "incomplete"]
    marker_size: float = Field(ge=0.0)
    supply_gap: float
    uh_readiness: float = Field(ge=0.0, le=1.0)
    mfh_readiness: float = Field(ge=0.0, le=1.0)
    missing_sources: list[str] = Field(default_factory=list)


class HousingInstallationListResponse(BaseModel):
    items: list[HousingInstallationMapItem] = Field(default_factory=list)
```

- [ ] **Step 4: Add dependencies**

In `backend/api/dependencies.py`, import:

```python
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.adapters.postgres import PostgresScorecardRunRepository
from scorecards.adapters.protocols import ScorecardRunRepository
from scorecards.service import ScorecardService
```

Add to `__all__`: `get_scorecard_run_repository`, `get_scorecard_service`.

Add functions:

```python
def get_scorecard_run_repository(request: Request) -> ScorecardRunRepository:
    def build() -> ScorecardRunRepository:
        provider = get_connection_provider()
        return (
            InMemoryScorecardRunRepository()
            if provider is None
            else PostgresScorecardRunRepository(provider)
        )

    return _memoize_config_derived(
        request.app,
        "scorecard_run_repository",
        build,
        guard=lambda value: isinstance(value, ScorecardRunRepository),
    )


def get_scorecard_service(
    repository: ScorecardRunRepository = Depends(get_scorecard_run_repository),
    config: DomainConfig = Depends(get_domain_config),
) -> ScorecardService:
    return ScorecardService(repository=repository, config=config)
```

- [ ] **Step 5: Add scorecards router**

Create `backend/api/routers/scorecards.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.contracts import ScorecardExportResponse, ScorecardGenerateRequest, ScorecardRunListResponse, ScorecardRunResponse, ScorecardTemplateListResponse
from api.dependencies import get_scorecard_service
from api.middleware.rbac import require_role
from scorecards.exceptions import ScorecardRunNotFoundError, ScorecardTemplateNotFoundError
from scorecards.models import ScorecardExportFormat, ScorecardRun
from scorecards.service import ScorecardService

router = APIRouter(prefix="/scorecards", tags=["scorecards"])


@router.get("/templates", response_model=ScorecardTemplateListResponse, dependencies=[Depends(require_role("viewer"))])
async def list_scorecard_templates(service: ScorecardService = Depends(get_scorecard_service)) -> ScorecardTemplateListResponse:
    return ScorecardTemplateListResponse(items=[item.model_dump() for item in service.list_templates().items])


@router.post("/runs", response_model=ScorecardRunResponse, dependencies=[Depends(require_role("analyst"))])
async def generate_scorecard_run(payload: ScorecardGenerateRequest, service: ScorecardService = Depends(get_scorecard_service)) -> ScorecardRun:
    try:
        return service.generate(
            knowledge_base_id=payload.knowledge_base_id,
            template_id=payload.template_id,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
        )
    except ScorecardTemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs", response_model=ScorecardRunListResponse, dependencies=[Depends(require_role("viewer"))])
async def list_scorecard_runs(
    knowledge_base_id: str = Query(..., min_length=1),
    template_id: str | None = Query(default=None),
    limit: int = Query(default=50, gt=0, le=500),
    offset: int = Query(default=0, ge=0),
    service: ScorecardService = Depends(get_scorecard_service),
) -> object:
    return service.list_runs(knowledge_base_id=knowledge_base_id, template_id=template_id, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=ScorecardRunResponse, dependencies=[Depends(require_role("viewer"))])
async def get_scorecard_run(run_id: str, knowledge_base_id: str = Query(...), service: ScorecardService = Depends(get_scorecard_service)) -> ScorecardRun:
    run = service.get_run(knowledge_base_id=knowledge_base_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scorecard run not found.")
    return run


@router.get("/runs/{run_id}/export", response_model=ScorecardExportResponse, dependencies=[Depends(require_role("viewer"))])
async def export_scorecard_run(
    run_id: str,
    knowledge_base_id: str = Query(...),
    format: ScorecardExportFormat = Query(...),
    service: ScorecardService = Depends(get_scorecard_service),
) -> object:
    try:
        return service.export_run(knowledge_base_id=knowledge_base_id, run_id=run_id, format=format)
    except ScorecardRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 6: Add housing router with deterministic empty read model**

Create `backend/api/routers/housing.py`:

```python
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from api.contracts import HousingInstallationListResponse, HousingOverviewResponse
from api.middleware.rbac import require_role

router = APIRouter(prefix="/housing", tags=["housing"])


@router.get("/overview", response_model=HousingOverviewResponse, dependencies=[Depends(require_role("viewer"))])
async def get_housing_overview(
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> HousingOverviewResponse:
    return HousingOverviewResponse(
        installations_total=0,
        critical_installations=0,
        watch_installations=0,
        supply_gap=0,
        uh_readiness=0,
        mfh_readiness=0,
        stale_sources=0,
        missing_sources=0,
    )


@router.get("/installations", response_model=HousingInstallationListResponse, dependencies=[Depends(require_role("viewer"))])
async def list_housing_installations(
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> HousingInstallationListResponse:
    return HousingInstallationListResponse(items=[])
```

This returns a safe empty model first. Later tasks can replace it with scorecard/records-backed aggregation without changing the frontend API shape.

- [ ] **Step 7: Register routers**

In `backend/api/app.py`, import and include:

```python
from api.routers.housing import router as housing_router
from api.routers.scorecards import router as scorecards_router
```

Add before `auth_router`:

```python
app.include_router(scorecards_router)
app.include_router(housing_router)
```

- [ ] **Step 8: Run API tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_scorecards_router.py backend/tests/api/test_housing_router.py backend/tests/api/test_policy_registry.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/api/routers/scorecards.py backend/api/routers/housing.py backend/tests/api/test_scorecards_router.py backend/tests/api/test_housing_router.py
git commit -m "feat(api): expose housing scorecard routes"
```

---

### Task 5: Frontend Contracts And API Clients

**Files:**
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`
- Modify: `chili_app/src/api/contracts.ts`
- Create: `chili_app/src/api/scorecards.ts`
- Create: `chili_app/src/api/housing.ts`
- Create: `chili_app/src/api/__tests__/scorecards.test.ts`
- Create: `chili_app/src/api/__tests__/housing.test.ts`

- [ ] **Step 1: Regenerate API contracts**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api
```

Expected: `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts` change to include `/scorecards/*` and `/housing/*`.

- [ ] **Step 2: Write frontend API client tests**

Create `chili_app/src/api/__tests__/scorecards.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'

import { generateScorecardRun, getScorecardTemplates, scorecardRunsQueryKey } from '../scorecards'

vi.mock('../client', () => ({
  apiFetch: vi.fn((path: string) => Promise.resolve({ path, items: [] })),
}))

describe('scorecards api', () => {
  it('lists templates', async () => {
    const result = await getScorecardTemplates()
    expect(result).toEqual({ path: '/scorecards/templates', items: [] })
  })

  it('builds stable run query keys', () => {
    expect(scorecardRunsQueryKey({ knowledgeBaseId: 'kb-1', templateId: 'uh_scorecard' })).toEqual([
      'scorecards',
      'runs',
      { knowledgeBaseId: 'kb-1', templateId: 'uh_scorecard' },
    ])
  })

  it('generates runs through the scorecards endpoint', async () => {
    const result = await generateScorecardRun({
      knowledge_base_id: 'kb-1',
      template_id: 'uh_scorecard',
      scope_type: 'installation',
      scope_id: 'edwards_afb',
      period_start: '2026-01-01',
      period_end: '2026-03-31',
    })
    expect(result).toEqual({ path: '/scorecards/runs', items: [] })
  })
})
```

Create `chili_app/src/api/__tests__/housing.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'

import { getHousingInstallations, getHousingOverview, housingInstallationsQueryKey } from '../housing'

vi.mock('../client', () => ({
  apiFetch: vi.fn((path: string) => Promise.resolve({ path, items: [] })),
}))

describe('housing api', () => {
  it('loads overview for a period', async () => {
    const result = await getHousingOverview({ periodStart: '2026-01-01', periodEnd: '2026-03-31' })
    expect(result).toEqual({ path: '/housing/overview?period_start=2026-01-01&period_end=2026-03-31', items: [] })
  })

  it('loads map rows for a period', async () => {
    const result = await getHousingInstallations({ periodStart: '2026-01-01', periodEnd: '2026-03-31' })
    expect(result).toEqual({ path: '/housing/installations?period_start=2026-01-01&period_end=2026-03-31', items: [] })
  })

  it('builds stable installations query keys', () => {
    expect(housingInstallationsQueryKey({ periodStart: '2026-01-01', periodEnd: '2026-03-31' })).toEqual([
      'housing',
      'installations',
      { periodStart: '2026-01-01', periodEnd: '2026-03-31' },
    ])
  })
})
```

- [ ] **Step 3: Run failing client tests**

Run:

```bash
cd chili_app && ./node_modules/.bin/vitest run src/api/__tests__/scorecards.test.ts src/api/__tests__/housing.test.ts
```

Expected: fail because API clients do not exist.

- [ ] **Step 4: Add contract aliases**

In `chili_app/src/api/contracts.ts`, add:

```ts
export type ScorecardTemplateSummaryResponse = Schemas['ScorecardTemplateSummaryResponse']
export type ScorecardTemplateListResponse = RequireFields<Schemas['ScorecardTemplateListResponse'], 'items'>
export type ScorecardGenerateRequest = Schemas['ScorecardGenerateRequest']
export type ScorecardRunResponse = RequireFields<Schemas['ScorecardRunResponse'], 'sections'>
export type ScorecardRunListResponse = RequireFields<Schemas['ScorecardRunListResponse'], 'items'>
export type ScorecardExportResponse = Schemas['ScorecardExportResponse']
export type HousingOverviewResponse = Schemas['HousingOverviewResponse']
export type HousingInstallationMapItem = RequireFields<Schemas['HousingInstallationMapItem'], 'missing_sources'>
export type HousingInstallationListResponse = RequireFields<Schemas['HousingInstallationListResponse'], 'items'>
```

- [ ] **Step 5: Add API clients**

Create `chili_app/src/api/scorecards.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  ScorecardExportResponse,
  ScorecardGenerateRequest,
  ScorecardRunListResponse,
  ScorecardRunResponse,
  ScorecardTemplateListResponse,
} from './contracts'

export type ScorecardRunFilters = {
  knowledgeBaseId: string
  templateId?: string
}

export const scorecardTemplatesQueryKey = ['scorecards', 'templates'] as const

export function scorecardRunsQueryKey(filters: ScorecardRunFilters | null) {
  return ['scorecards', 'runs', filters] as const
}

export function scorecardRunQueryKey(knowledgeBaseId: string | null, runId: string | null) {
  return ['scorecards', 'run', knowledgeBaseId, runId] as const
}

export function getScorecardTemplates(): Promise<ScorecardTemplateListResponse> {
  return apiFetch<ScorecardTemplateListResponse>('/scorecards/templates')
}

export function getScorecardRuns(filters: ScorecardRunFilters): Promise<ScorecardRunListResponse> {
  const params = new URLSearchParams({ knowledge_base_id: filters.knowledgeBaseId })
  if (filters.templateId) params.set('template_id', filters.templateId)
  return apiFetch<ScorecardRunListResponse>(`/scorecards/runs?${params}`)
}

export function getScorecardRun(knowledgeBaseId: string, runId: string): Promise<ScorecardRunResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<ScorecardRunResponse>(`/scorecards/runs/${encodeURIComponent(runId)}?${params}`)
}

export function generateScorecardRun(payload: ScorecardGenerateRequest): Promise<ScorecardRunResponse> {
  return apiFetch<ScorecardRunResponse>('/scorecards/runs', { method: 'POST', body: JSON.stringify(payload) })
}

export function exportScorecardRun(knowledgeBaseId: string, runId: string, format: 'json' | 'markdown'): Promise<ScorecardExportResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId, format })
  return apiFetch<ScorecardExportResponse>(`/scorecards/runs/${encodeURIComponent(runId)}/export?${params}`)
}

export function useScorecardTemplates() {
  return useQuery({ queryKey: scorecardTemplatesQueryKey, queryFn: getScorecardTemplates })
}

export function useScorecardRuns(filters: ScorecardRunFilters | null) {
  return useQuery({
    queryKey: scorecardRunsQueryKey(filters),
    queryFn: () => getScorecardRuns(filters ?? { knowledgeBaseId: '' }),
    enabled: Boolean(filters?.knowledgeBaseId),
  })
}

export function useGenerateScorecardRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: generateScorecardRun,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scorecards'] })
      void queryClient.invalidateQueries({ queryKey: ['housing'] })
    },
  })
}
```

Create `chili_app/src/api/housing.ts`:

```ts
import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { HousingInstallationListResponse, HousingOverviewResponse } from './contracts'

export type HousingPeriodFilters = {
  periodStart: string
  periodEnd: string
}

export function housingOverviewQueryKey(filters: HousingPeriodFilters | null) {
  return ['housing', 'overview', filters] as const
}

export function housingInstallationsQueryKey(filters: HousingPeriodFilters | null) {
  return ['housing', 'installations', filters] as const
}

function periodParams(filters: HousingPeriodFilters) {
  return new URLSearchParams({ period_start: filters.periodStart, period_end: filters.periodEnd })
}

export function getHousingOverview(filters: HousingPeriodFilters): Promise<HousingOverviewResponse> {
  return apiFetch<HousingOverviewResponse>(`/housing/overview?${periodParams(filters)}`)
}

export function getHousingInstallations(filters: HousingPeriodFilters): Promise<HousingInstallationListResponse> {
  return apiFetch<HousingInstallationListResponse>(`/housing/installations?${periodParams(filters)}`)
}

export function useHousingOverview(filters: HousingPeriodFilters | null) {
  return useQuery({
    queryKey: housingOverviewQueryKey(filters),
    queryFn: () => getHousingOverview(filters ?? { periodStart: '', periodEnd: '' }),
    enabled: Boolean(filters?.periodStart && filters?.periodEnd),
  })
}

export function useHousingInstallations(filters: HousingPeriodFilters | null) {
  return useQuery({
    queryKey: housingInstallationsQueryKey(filters),
    queryFn: () => getHousingInstallations(filters ?? { periodStart: '', periodEnd: '' }),
    enabled: Boolean(filters?.periodStart && filters?.periodEnd),
  })
}
```

- [ ] **Step 6: Run frontend API tests**

Run:

```bash
cd chili_app && ./node_modules/.bin/vitest run src/api/__tests__/scorecards.test.ts src/api/__tests__/housing.test.ts
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts chili_app/src/api/scorecards.ts chili_app/src/api/housing.ts chili_app/src/api/__tests__/scorecards.test.ts chili_app/src/api/__tests__/housing.test.ts
git commit -m "feat(app): add housing scorecard API clients"
```

---

### Task 6: Map-Led Housing Executive Page

**Files:**
- Create: `chili_app/src/components/housing/InstallationHealthMap.tsx`
- Create: `chili_app/src/components/housing/InstallationHealthMap.module.css`
- Create: `chili_app/src/components/housing/InstallationRankingTable.tsx`
- Create: `chili_app/src/components/housing/ScorecardReadinessPanel.tsx`
- Create: `chili_app/src/pages/HousingExecutivePage.tsx`
- Create: `chili_app/src/pages/__tests__/HousingExecutivePage.test.tsx`
- Modify: `chili_app/src/app/router.tsx`
- Modify: `chili_app/src/components/layout/Sidebar.tsx`
- Modify: `chili_app/src/lib/ragContext.ts`

- [ ] **Step 1: Write page test**

Create `chili_app/src/pages/__tests__/HousingExecutivePage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { HousingExecutivePage } from '../HousingExecutivePage'

vi.mock('../../api/housing', () => ({
  useHousingOverview: () => ({
    isLoading: false,
    isError: false,
    data: {
      installations_total: 2,
      critical_installations: 1,
      watch_installations: 1,
      supply_gap: 210,
      uh_readiness: 0.78,
      mfh_readiness: 0.64,
      stale_sources: 1,
      missing_sources: 2,
    },
  }),
  useHousingInstallations: () => ({
    isLoading: false,
    isError: false,
    data: {
      items: [
        {
          installation_id: 'edwards_afb',
          name: 'Edwards AFB',
          majcom: 'AFMC',
          state: 'CA',
          latitude: 34.9054,
          longitude: -117.8837,
          health: 'fail',
          marker_size: 210,
          supply_gap: 130,
          uh_readiness: 0.71,
          mfh_readiness: 0.43,
          missing_sources: ['market_availability'],
        },
      ],
    },
  }),
}))

vi.mock('../../api/scorecards', () => ({
  useScorecardTemplates: () => ({
    isLoading: false,
    isError: false,
    data: { items: [{ id: 'uh_scorecard', name: 'UH Scorecard', category: 'UH', scope: 'installation', period: 'quarterly' }] },
  }),
  useScorecardRuns: () => ({ isLoading: false, isError: false, data: { items: [], total: 0 } }),
  useGenerateScorecardRun: () => ({ mutate: vi.fn(), isPending: false }),
}))

describe('HousingExecutivePage', () => {
  it('renders a map-led executive operating picture', async () => {
    render(
      <MemoryRouter>
        <HousingExecutivePage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Housing Supply Health' })).toBeInTheDocument()
    expect(screen.getByLabelText('Installation health map')).toBeInTheDocument()
    expect(screen.getByText('Edwards AFB')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Edwards AFB/i }))
    expect(screen.getByText('Missing sources')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ask about this installation/i })).toHaveAttribute('href', expect.stringContaining('/rag-chat'))
  })
})
```

- [ ] **Step 2: Run failing page test**

Run:

```bash
cd chili_app && ./node_modules/.bin/vitest run src/pages/__tests__/HousingExecutivePage.test.tsx
```

Expected: fail because page and components do not exist.

- [ ] **Step 3: Add SVG map component**

Create `chili_app/src/components/housing/InstallationHealthMap.tsx`:

```tsx
import type { HousingInstallationMapItem } from '../../api/contracts'
import styles from './InstallationHealthMap.module.css'

type InstallationHealthMapProps = {
  items: HousingInstallationMapItem[]
  selectedId: string | null
  onSelect: (installationId: string) => void
}

const HEALTH_CLASS = {
  pass: styles.pass,
  warn: styles.warn,
  fail: styles.fail,
  incomplete: styles.incomplete,
} as const

export function InstallationHealthMap({ items, selectedId, onSelect }: InstallationHealthMapProps) {
  const withCoordinates = items.filter((item) => item.latitude !== null && item.longitude !== null)
  const missingCoordinates = items.filter((item) => item.latitude === null || item.longitude === null)

  return (
    <div className={styles.root}>
      <svg aria-label="Installation health map" className={styles.map} role="img" viewBox="0 0 960 520">
        <rect className={styles.land} x="70" y="70" width="760" height="340" rx="42" />
        {withCoordinates.map((item) => {
          const x = longitudeToX(item.longitude ?? 0)
          const y = latitudeToY(item.latitude ?? 0)
          const radius = Math.max(8, Math.min(28, 8 + item.marker_size / 20))
          const selected = item.installation_id === selectedId
          return (
            <foreignObject height={radius * 2 + 8} key={item.installation_id} width={radius * 2 + 8} x={x - radius - 4} y={y - radius - 4}>
              <button
                aria-label={`${item.name} ${item.health} health`}
                className={`${styles.marker} ${HEALTH_CLASS[item.health]} ${selected ? styles.selected : ''}`}
                onClick={() => onSelect(item.installation_id)}
                style={{ height: radius * 2, width: radius * 2 }}
                type="button"
              />
            </foreignObject>
          )
        })}
      </svg>
      {missingCoordinates.length > 0 ? (
        <div className={styles.missing}>
          <strong>Location missing</strong>
          {missingCoordinates.map((item) => <span key={item.installation_id}>{item.name}</span>)}
        </div>
      ) : null}
    </div>
  )
}

function longitudeToX(longitude: number) {
  return 120 + ((longitude + 125) / 59) * 700
}

function latitudeToY(latitude: number) {
  return 390 - ((latitude - 24) / 26) * 280
}
```

Create `chili_app/src/components/housing/InstallationHealthMap.module.css`:

```css
.root {
  display: grid;
  gap: 0.75rem;
}

.map {
  min-height: 22rem;
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 8px;
  background: #0f172a;
}

.land {
  fill: #1f2937;
  stroke: rgba(226, 232, 240, 0.32);
}

.marker {
  border: 2px solid rgba(255, 255, 255, 0.92);
  border-radius: 999px;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.32);
  cursor: pointer;
}

.pass { background: #22c55e; }
.warn { background: #f59e0b; }
.fail { background: #ef4444; }
.incomplete { background: #94a3b8; }

.selected {
  outline: 3px solid #38bdf8;
  outline-offset: 2px;
}

.missing {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.875rem;
}
```

- [ ] **Step 4: Add table and readiness components**

Create `chili_app/src/components/housing/InstallationRankingTable.tsx`:

```tsx
import type { HousingInstallationMapItem } from '../../api/contracts'

type Props = {
  items: HousingInstallationMapItem[]
  selectedId: string | null
  onSelect: (installationId: string) => void
}

export function InstallationRankingTable({ items, selectedId, onSelect }: Props) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Installation</th>
          <th>Health</th>
          <th>Supply Gap</th>
          <th>UH Ready</th>
          <th>MFH Ready</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr aria-selected={item.installation_id === selectedId} key={item.installation_id}>
            <td>
              <button className="link-button" onClick={() => onSelect(item.installation_id)} type="button">
                {item.name}
              </button>
            </td>
            <td>{item.health}</td>
            <td>{item.supply_gap}</td>
            <td>{Math.round(item.uh_readiness * 100)}%</td>
            <td>{Math.round(item.mfh_readiness * 100)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```

Create `chili_app/src/components/housing/ScorecardReadinessPanel.tsx`:

```tsx
import type { ScorecardTemplateSummaryResponse } from '../../api/contracts'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'

export function ScorecardReadinessPanel({ templates }: { templates: ScorecardTemplateSummaryResponse[] }) {
  return (
    <Card>
      <div className="metric-stack">
        <strong>Scorecard Readiness</strong>
        {templates.map((template) => (
          <div className="metric-row" key={template.id}>
            <span className="metric-row__label">{template.name}</span>
            <Chip label={template.category} tone="info" />
          </div>
        ))}
      </div>
    </Card>
  )
}
```

- [ ] **Step 5: Add page**

Create `chili_app/src/pages/HousingExecutivePage.tsx`:

```tsx
import { MapPin } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useHousingInstallations, useHousingOverview } from '../api/housing'
import { useScorecardTemplates } from '../api/scorecards'
import { InstallationHealthMap } from '../components/housing/InstallationHealthMap'
import { InstallationRankingTable } from '../components/housing/InstallationRankingTable'
import { ScorecardReadinessPanel } from '../components/housing/ScorecardReadinessPanel'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { KpiCard } from '../components/ui/KpiCard'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function HousingExecutivePage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const period = useMemo(() => ({ periodStart: '2026-01-01', periodEnd: '2026-03-31' }), [])
  const overviewQuery = useHousingOverview(period)
  const installationsQuery = useHousingInstallations(period)
  const templatesQuery = useScorecardTemplates()

  if (overviewQuery.isLoading || installationsQuery.isLoading || templatesQuery.isLoading) {
    return <LoadingState label="Loading housing operating picture" />
  }
  if (overviewQuery.isError || installationsQuery.isError || templatesQuery.isError) {
    return <ErrorState description="Housing dashboard data could not be loaded." />
  }

  const overview = overviewQuery.data
  const items = installationsQuery.data?.items ?? []
  const selected = items.find((item) => item.installation_id === selectedId) ?? items[0] ?? null

  return (
    <section className="page-grid">
      <SectionHeader
        eyebrow="Executive operating picture"
        subtitle="Cross-installation housing supply health, UH/MFH readiness, and scorecard evidence."
        title="Housing Supply Health"
      />
      {overview ? (
        <div className="dashboard-kpis">
          <KpiCard color="#ef4444" icon={MapPin} label="Critical installations" value={String(overview.critical_installations)} />
          <KpiCard color="#f59e0b" icon={MapPin} label="Watch installations" value={String(overview.watch_installations)} />
          <KpiCard color="#38bdf8" icon={MapPin} label="Supply gap" value={String(overview.supply_gap)} />
          <KpiCard color="#22c55e" icon={MapPin} label="UH readiness" value={`${Math.round(overview.uh_readiness * 100)}%`} />
          <KpiCard color="#a855f7" icon={MapPin} label="MFH readiness" value={`${Math.round(overview.mfh_readiness * 100)}%`} />
        </div>
      ) : null}
      {items.length === 0 ? (
        <EmptyState title="No installation data" description="Upload Air Force housing exports to populate the map." />
      ) : (
        <div className="dashboard-panels">
          <Card>
            <InstallationHealthMap items={items} selectedId={selected?.installation_id ?? null} onSelect={setSelectedId} />
          </Card>
          <Card>
            {selected ? (
              <div className="metric-stack">
                <strong>{selected.name}</strong>
                <div className="metric-row"><span className="metric-row__label">Health</span><span>{selected.health}</span></div>
                <div className="metric-row"><span className="metric-row__label">Supply gap</span><span>{selected.supply_gap}</span></div>
                <div className="metric-row"><span className="metric-row__label">Missing sources</span><span>{selected.missing_sources.length}</span></div>
                <Link to={`/rag-chat?q=${encodeURIComponent(`Why is ${selected.name} ${selected.health} for housing health?`)}`}>Ask about this installation</Link>
              </div>
            ) : null}
          </Card>
        </div>
      )}
      <ScorecardReadinessPanel templates={templatesQuery.data?.items ?? []} />
      <Card>
        <InstallationRankingTable items={items} selectedId={selected?.installation_id ?? null} onSelect={setSelectedId} />
      </Card>
    </section>
  )
}
```

- [ ] **Step 6: Route and nav wiring**

In `chili_app/src/app/router.tsx`, import and add route:

```tsx
import { HousingExecutivePage } from '../pages/HousingExecutivePage'
```

```tsx
{ path: 'housing', element: withPageBoundary(<HousingExecutivePage />) },
```

In `chili_app/src/components/layout/Sidebar.tsx`, import `MapPinned` from `lucide-react` and add:

```ts
housing: MapPinned,
```

- [ ] **Step 7: Run page test**

Run:

```bash
cd chili_app && ./node_modules/.bin/vitest run src/pages/__tests__/HousingExecutivePage.test.tsx
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add chili_app/src/components/housing chili_app/src/pages/HousingExecutivePage.tsx chili_app/src/pages/__tests__/HousingExecutivePage.test.tsx chili_app/src/app/router.tsx chili_app/src/components/layout/Sidebar.tsx chili_app/src/lib/ragContext.ts
git commit -m "feat(app): add map-led housing executive dashboard"
```

---

### Task 7: End-To-End Wiring, Verification, And Documentation

**Files:**
- Create: `chili_app/e2e/air-force-housing-scorecards.spec.ts`
- Modify: `docs/testing/DATA.md`
- Modify: `backend/config/README.md`
- Modify: `README.md` if adding a short domain-pack mention is useful.

- [ ] **Step 1: Add Playwright smoke**

Create `chili_app/e2e/air-force-housing-scorecards.spec.ts`:

```ts
import { expect, test } from '@playwright/test'

test('Air Force housing dashboard renders map and scorecard actions', async ({ page }) => {
  await page.goto('/housing')
  await expect(page.getByRole('heading', { name: 'Housing Supply Health' })).toBeVisible()
  await expect(page.getByLabel('Installation health map')).toBeVisible()
  await expect(page.getByText('Scorecard Readiness')).toBeVisible()
})
```

- [ ] **Step 2: Add docs**

In `backend/config/README.md`, add `department_air_force_housing.yaml` to the shipped packs list:

```markdown
- `department_air_force_housing.yaml` - executive Air Force housing health and configurable UH/MFH scorecard automation. Uses file/export feeds for UMD, BAH, inventory, market, and demographic data.
```

In `docs/testing/DATA.md`, add the Air Force housing fixture directory and feed mapping.

- [ ] **Step 3: Run backend verification**

Run:

```bash
uv run --project backend pytest backend/tests/config/test_air_force_housing_pack.py backend/tests/scorecards backend/tests/api/test_scorecards_router.py backend/tests/api/test_housing_router.py -q
uv run --project backend pyright backend/scorecards backend/api/routers/scorecards.py backend/api/routers/housing.py backend/tests/scorecards backend/tests/api/test_scorecards_router.py backend/tests/api/test_housing_router.py
uv run --project backend ruff check backend/scorecards backend/api/routers/scorecards.py backend/api/routers/housing.py backend/tests/scorecards backend/tests/api/test_scorecards_router.py backend/tests/api/test_housing_router.py
```

Expected: all pass.

- [ ] **Step 4: Run frontend verification**

Run:

```bash
cd chili_app && ./node_modules/.bin/vitest run src/api/__tests__/scorecards.test.ts src/api/__tests__/housing.test.ts src/pages/__tests__/HousingExecutivePage.test.tsx
cd chili_app && npm run build
```

Expected: all pass.

- [ ] **Step 5: Run generated contract drift check**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api
git diff --exit-code chili_app/openapi.json chili_app/src/lib/api/schema.ts
```

Expected: no diff after committed generated files.

- [ ] **Step 6: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 7: Commit final docs/e2e**

```bash
git add chili_app/e2e/air-force-housing-scorecards.spec.ts docs/testing/DATA.md backend/config/README.md README.md
git commit -m "test(e2e): cover Air Force housing dashboard smoke"
```

---

## Self-Review

Spec coverage:
- Domain pack and file/export ingestion are covered by Task 1.
- Configurable UH/MFH scorecard templates are covered by Task 1 and Task 2.
- Reusable scorecards backend module is covered by Tasks 2 and 3.
- `/scorecards` and `/housing` APIs are covered by Task 4.
- Generated frontend contracts and typed clients are covered by Task 5.
- Map-led executive UX is covered by Task 6.
- Verification and docs are covered by Task 7.

Scope notes:
- V1 uses an SVG map component to avoid adding a map dependency before license review.
- Housing aggregate APIs start with a safe empty read model in Task 4, then frontend wiring can land against stable contracts. A follow-up plan should replace empty aggregation with records/scorecard-backed calculations once scorecard source data extraction from raw records is implemented.
- PDF export, live connectors, approval workflow, predictive optimization, and remediation casework stay outside this plan.

Execution order:
1. Task 1 freezes configuration and fixtures.
2. Tasks 2-3 build the scorecard core.
3. Task 4 exposes backend API contracts.
4. Task 5 regenerates frontend contracts.
5. Task 6 builds the executive UI.
6. Task 7 runs complete verification.
