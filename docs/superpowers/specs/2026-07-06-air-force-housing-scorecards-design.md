# Department of the Air Force Housing Scorecards Design

> Status: Draft for user review (2026-07-06)
> Branch: `af_housing`
> Goal: Rapidly adapt chiliAI into an executive, cross-installation housing health platform for Department of the Air Force accompanied and unaccompanied housing, with configurable UH and MFH scorecard generation.

## 1. Problem And Context

Department of the Air Force housing leaders need a cross-installation operating picture for the health of accompanied and unaccompanied housing supply. The system must combine manpower demand, allowance/cost signals, local market availability, demographics, housing inventory, policy requirements, and scorecard templates into a governed executive reporting workflow.

The platform should directly support rapid report generation and information retrieval. It should automate configurable NDAA-mandated UH and MFH scorecards without hardcoding scorecard sections, thresholds, or required sources in application code.

Public oversight context supports this direction. GAO reported that DOD lacked reliable barracks condition data and complete funding visibility, and recommended improved condition assessment, funding, and oversight practices. GAO also reported oversight gaps in privatized military housing management. These sources are not treated as the official UH/MFH scorecard templates; the templates remain governed domain inputs.

Sources:
- GAO-23-105797, "Military Barracks: Poor Living Conditions Undermine Quality of Life and Readiness": https://www.gao.gov/products/gao-23-105797
- GAO-20-281, "Military Housing: DOD Needs to Strengthen Oversight and Clarify Its Role in the Management of Privatized Housing": https://www.gao.gov/products/gao-20-281

## 2. Product Scope

V1 is an executive cross-installation housing health product. The primary user is a housing, civil engineering, manpower, or senior staff user comparing installations, commands, housing categories, and scorecard readiness. The first release should not depend on live system connectors. It should ingest file/export data, validate it, calculate KPIs, produce configurable UH/MFH scorecard runs, and support RAG over policy, scorecard definitions, uploaded narrative, and source documentation.

The product should answer:
- Where is housing supply misaligned with authorized or eligible demand?
- Which installations have the highest UH and MFH risk?
- Which scorecard sections are complete, stale, missing, or failing thresholds?
- What source data supports each KPI?
- Can required UH/MFH scorecard packages be generated without manual spreadsheet assembly?
- Can an executive ask natural-language questions and retrieve cited source evidence?

V1 does not prioritize case-level remediation tracking, live connectors, real-time streaming alerts, or predictive housing optimization. Existing Alert Feed, Investigation Workbench, and Case Management routes may remain available to analysts, but the Air Force housing workflow should not depend on them.

## 3. Recommended Approach

Use approach 2: domain pack plus reusable scorecard/report module.

The Air Force housing adoption should be built as:
1. A `department_air_force_housing` domain pack.
2. A reusable `scorecards` backend capability.
3. A map-led executive dashboard at `/housing`.
4. Configurable UH and MFH scorecard templates.
5. File/export ingestion first, with direct system connectors deferred.

This avoids an Air Force-specific fork while making scorecard generation a first-class platform capability instead of a dashboard-only workaround or RAG-only report prompt.

## 4. Domain Model

Add an Air Force housing domain pack with these core entities:

| Entity | Purpose |
| --- | --- |
| `installation` | Primary executive rollup unit: base, command, region, geography, mission category. |
| `housing_asset` | Dormitory, unit, building, family housing project, privatized project, lease pool, or other housing asset depending on source granularity. |
| `housing_inventory_snapshot` | Beds/units, offline count, utilization, condition, capacity date, category, and source freshness. |
| `population_demand_snapshot` | UMD/manpower demand, grade mix, accompanied/unaccompanied split, dependent-status assumptions, and projected demand. |
| `allowance_market_snapshot` | BAH rate, rental availability, affordability, vacancy, commute, and market area indicators. |
| `demographic_snapshot` | Local household, population, income, dependency, and area context. |
| `resident_experience_snapshot` | Survey, complaint, maintenance, or satisfaction signals when available. |
| `scorecard_template` | Configurable scorecard sections, formulas, thresholds, required sources, and export profile. |
| `scorecard_run` | Generated scorecard for a period and scope, with metric values, completeness, citations, export payloads, and provenance. |

Representative relationships:
- `installation_has_asset`: installation to housing asset.
- `asset_has_inventory_snapshot`: housing asset to inventory snapshot.
- `installation_has_population_demand`: installation to demand snapshot.
- `installation_has_market_snapshot`: installation to allowance/market snapshot.
- `installation_has_demographic_snapshot`: installation to demographic snapshot.
- `scorecard_run_for_installation`: scorecard run to installation.
- `scorecard_run_uses_source_snapshot`: scorecard run to source snapshot/document reference.

## 5. File/Export Ingestion

V1 uses file/export ingestion only.

Structured feeds should be declared in `DomainConfig.records.feeds` and should accept CSV, XLSX, JSON, or JSONL exports as appropriate:
- UMD/manpower authorization extracts.
- BAH/rental allowance tables.
- Housing inventory and condition exports.
- Local market availability exports.
- Demographic extracts.
- Resident experience or maintenance/work-order exports when available.

Documents should use existing knowledge-base document ingestion:
- NDAA language and statutory excerpts.
- DAF/DoD policy and guidance.
- UH/MFH scorecard instructions.
- SOPs, memos, PDFs, and narrative justifications.
- Source reports used as scorecard evidence.

Scorecard templates should be uploaded or edited as YAML/JSON through Config Manager. The template schema should be part of domain configuration so changing a scorecard section, threshold, formula, or required source is a config change, not a code change.

Data quality behavior:
- Good rows ingest even when some rows are rejected.
- Rejected rows are visible in receipt/review surfaces.
- Every accepted row preserves source lineage.
- Missing required sources mark dependent KPIs incomplete.
- Stale sources mark dependent KPIs warning.
- Unknown/incomplete values must not be represented as zero.

## 6. Scorecards Configuration

Add a generic `scorecards` section to `DomainConfig`.

Proposed template fields:
- `id`, `name`, `category`: for example `uh_scorecard` and `mfh_scorecard`.
- `scope`: enterprise, MAJCOM, region, installation, market area.
- `period`: monthly, quarterly, annual, or ad hoc.
- `sections`: demand, supply, condition, utilization, cost/BAH, market pressure, resident experience, compliance, or other configured groups.
- `metrics`: formula, required source feeds, rollup method, thresholds, display unit, health bands, and evidence requirements.
- `evidence_requirements`: required source types, freshness windows, minimum completeness, and citation rules.
- `export_profile`: JSON and Markdown in v1; PDF can follow after the content contract stabilizes.

Each scorecard metric should define:
- `id`, `label`, `description`.
- `formula`: bounded expression over named metric inputs.
- `inputs`: references to record feeds, graph metrics, current metrics, or source documents.
- `rollup`: sum, average, weighted average, count, min, max, ratio, or configured band aggregation.
- `thresholds`: pass, warn, fail, incomplete.
- `required`: whether missing evidence blocks section completeness.
- `freshness_days`: maximum source age before warning.

Avoid arbitrary executable formulas in v1. Use a bounded expression language or enumerated formula operators so templates are configurable but safe.

## 7. Scorecards Backend Capability

Create a reusable backend module:

```text
backend/scorecards/
  __init__.py
  models.py
  service_models.py
  protocols.py
  service.py
  evaluation.py
  exceptions.py
  adapters/
    protocols.py
    in_memory.py
    postgres.py
```

Responsibilities:
- Validate scorecard templates from domain config.
- Evaluate templates against records, metrics, graph state, and source citations.
- Persist durable scorecard runs.
- Produce export-ready payloads.
- Provide API models for list/detail/generate/export routes.

The evaluator should produce a durable `ScorecardRun` with:
- calculated metric values by section;
- rollup totals by installation and housing category;
- completeness status for each required source;
- stale/missing source warnings;
- cited source rows/documents for every metric;
- generated narrative summary for executive review;
- export payloads that can be re-downloaded without recalculation.

Natural identity for idempotent generation:

```text
(template_id, period_start, period_end, scope_type, scope_id, source_snapshot_hash)
```

The evaluator should be deterministic. Formula failures should be isolated to the affected metric and section, not fail the entire scorecard run.

## 8. API Surface

Add scorecard routes under `/scorecards`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/scorecards/templates` | List configured scorecard templates from the active domain pack. |
| `GET` | `/scorecards/templates/{template_id}` | Return one template with section/metric metadata. |
| `POST` | `/scorecards/runs` | Generate or reuse a scorecard run for template, period, scope, and source snapshot. |
| `GET` | `/scorecards/runs` | List scorecard runs by template, period, scope, and status. |
| `GET` | `/scorecards/runs/{run_id}` | Return full scorecard run detail, metric evidence, warnings, and narrative. |
| `GET` | `/scorecards/runs/{run_id}/export?format=json\|markdown` | Return stored export payload. |

Add housing executive routes only where the dashboard needs aggregated read models not naturally represented by scorecard runs:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/housing/overview` | Enterprise rollup KPIs for the selected period. |
| `GET` | `/housing/installations` | Map/list rows with health band, coordinates, size metric, and readiness. |
| `GET` | `/housing/installations/{installation_id}` | Installation executive summary for the side panel. |

Backend-consumed Pydantic changes must follow the repo's generated-contract workflow: export OpenAPI, regenerate frontend API types, and update typed clients.

## 9. Executive UX

Add `/housing` as the domain landing page for the Air Force housing pack. The page should be map-led.

Primary first-screen object:
- geographic map of installations;
- marker color = selected health band;
- marker size = selected magnitude such as supply gap or impacted population;
- filters for MAJCOM/region, installation type, accompanied/unaccompanied, period, data freshness, and risk band;
- view modes for combined health, UH health, MFH health, supply gap, utilization, condition, BAH/market pressure, scorecard readiness, and source completeness.

Marker click opens an installation side panel with:
- top housing KPIs;
- demand/supply gap;
- UH readiness;
- MFH readiness;
- market pressure;
- missing/stale source list;
- scorecard actions;
- RAG action scoped to installation, period, scorecard, and source set.

Supporting views:
- installation ranking table below or beside the map;
- scorecard readiness table by UH/MFH template and period;
- scorecard run detail with section pass/warn/fail/incomplete states;
- export actions;
- contextual RAG entry point for "Ask Housing Data."

The UI should remain dense, operational, and executive-oriented. It should avoid marketing-style hero layouts.

## 10. Map Component

The map should be a first-class component, not a decorative graphic.

Required v1 behaviors:
- render all configured installations with latitude/longitude;
- color markers by selected health dimension;
- size markers by selected magnitude;
- show hover tooltip with installation, command, health, and top gap;
- open side panel on marker click;
- support table-map synchronized selection;
- handle missing coordinates by listing those installations in a "location missing" section instead of dropping them silently.

Implementation options for planning:
- Use a proven map library if license policy allows it.
- If dependency/license constraints block a map library, start with a lightweight projected SVG/Canvas U.S. map plus plotted coordinates for v1.
- Keep the domain data contract independent of the rendering library.

## 11. RAG And Information Retrieval

Use existing RAG chat as a contextual retrieval surface. The housing dashboard and scorecard run detail should launch RAG with shallow filters:
- `installation_id`;
- `period`;
- `template_id`;
- `run_id`;
- `source_feed`;
- `housing_category`: UH, MFH, combined.

Typical supported questions:
- "Why is this installation critical?"
- "What source data supports the UH readiness score?"
- "Which installations are missing market availability data?"
- "Explain the MFH scorecard failures for this quarter."
- "What changed since the previous reporting period?"

RAG responses must cite source rows, documents, scorecard sections, or policy documents where available. If evidence is missing, the answer should say the selected scorecard scope lacks evidence rather than infer facts.

## 12. Delivery Phases

### Phase 1: Domain Pack And Static Executive Demo

Create the Air Force housing domain pack, representative feed schemas, sample data, map-led dashboard shell, and configurable UH/MFH template examples. Goal: show the target executive experience with sample-backed data.

### Phase 2: Real File/Export Ingestion

Wire UMD, BAH, housing inventory, market, demographic, and template uploads through existing records/document ingestion. Add validation, rejected-row reporting, data freshness, and source completeness. Goal: uploaded files drive installation KPIs.

### Phase 3: Scorecard Module

Add `scorecards` service, repository, evaluator, API, and frontend scorecard run detail/export flow. Goal: generate durable UH/MFH scorecard runs with evidence and completeness.

### Phase 4: Map-Led Executive Operating Picture

Make `/housing` the domain landing page. Add map markers, filters, health bands, installation side panel, ranking table, scorecard readiness, and RAG launch context. Goal: leadership can see enterprise housing health and drill into scorecard evidence.

### Phase 5: Hardening

Add historical trend comparison, source snapshot versioning, role-based approval/release states, PDF export if needed, and production auth/audit posture. Goal: recurring official report production.

## 13. Governance And Audit

Treat UMD, BAH, inventory, market, demographics, resident experience, and policy documents as separately versioned source snapshots.

Every KPI and scorecard section should expose:
- source feed/document;
- source snapshot ID;
- source freshness;
- completeness;
- formula ID/version;
- template ID/version;
- generated timestamp;
- actor;
- warning/error state.

Scorecard run lifecycle can start simple:
- `generated`;
- `superseded`;
- `failed`.

Later release-state hardening can add:
- `draft`;
- `reviewed`;
- `approved`;
- `released`;
- `superseded`.

Raw uploaded files and accepted/rejected row reports must be preserved for audit and rerun.

## 14. Error Handling

Rules:
- Bad rows do not block good rows.
- Missing required source feeds mark affected metrics incomplete.
- Stale source feeds mark affected metrics warning.
- Unknown values are not coerced to zero.
- Formula failures are isolated to affected metric/section.
- Scorecard generation can return partial runs only when the template allows incomplete sections.
- Export downloads use stored payloads from the run; they do not recalculate silently.
- RAG answers must cite evidence or state that evidence is missing.

## 15. Testing And Verification

Backend:
- Config tests for `department_air_force_housing` pack.
- Config tests for UH/MFH scorecard templates.
- Unit tests for scorecard formula evaluation, rollups, thresholds, freshness, completeness, and idempotency key generation.
- Repository contract tests for in-memory and Postgres scorecard runs.
- API tests for templates, run generation, run list/detail, and export.
- Records ingestion tests for representative UMD, BAH, housing inventory, market, and demographic feeds.

Frontend:
- API client tests for scorecard and housing overview endpoints.
- Page tests for `/housing` map filters, table selection, side panel, readiness states, and export actions.
- Accessibility tests for marker selection and keyboard navigation fallback through the ranking table.

End-to-end:
- Upload sample exports.
- Generate UH and MFH scorecards.
- Verify map marker health and size reflect generated KPI/readiness data.
- Open scorecard run detail.
- Export JSON/Markdown.
- Launch RAG from selected installation/run and verify cited answer.

Verification commands should follow repo convention:
- backend pytest for changed modules;
- backend pyright for changed files/modules;
- frontend Vitest for changed API/page components;
- `npm run build` in `chili_app`;
- OpenAPI export/codegen when API contracts change;
- `git diff --check`.

## 16. Acceptance Criteria

- Air Force housing domain pack validates without code changes to core config loading.
- File/export ingestion supports representative UMD, BAH, housing inventory, market, and demographic feeds.
- UH/MFH scorecard templates are configurable in YAML/JSON.
- Scorecard generation produces durable runs with values, health bands, completeness, warnings, citations, and export payloads.
- `/housing` provides a map-led executive operating picture across installations.
- Marker color and size reflect selected health/magnitude dimensions.
- Installation side panel links to scorecard run detail and contextual RAG.
- Every KPI exposes source freshness and completeness.
- Missing/stale data is visible and cannot silently pass as healthy.
- E2E sample flow proves upload to scorecard to map to export to cited RAG answer.

## 17. Open Risks

- Exact UH/MFH scorecard templates and metric definitions may be controlled or internal; v1 mitigates this by making templates configurable.
- Map library selection may introduce dependency or license constraints; keep the data contract independent of rendering library.
- Formula expressiveness must be sufficient for scorecards without becoming unsafe arbitrary code.
- Source exports may vary by command or system; the feed design should include explicit schema versions and rejected-row reports.
- PDF export may become a hard requirement; keep v1 export payloads stable so PDF generation can be added as a renderer later.
