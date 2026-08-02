# SAFE-CMS PI 1 — Analytics Foundation Implementation Spec

> Scope: `SAFE-CMS-001` through `SAFE-CMS-004`
> Source plan: `docs/superpowers/plans/2026-07-30-cms-fraud-ai-safe-agile-20-sprint-surge.md`
> Formalized: 2026-08-02
> Branch context at formalization: `fix/normalize-kb-query-param`

## 1. Objective

PI 1 turns the July 30 CMS fraud review into a schedulable foundation: fraud typologies, reusable feature
definitions, durable score-all execution, production risk read models, and structured evidence provenance. The
target outcome is backend-visible and inspectable. It is acceptable if the PI 1 UI is minimal, but every new
contract must be KB-scoped, versioned where needed, and reusable outside CMS.

## 2. Baseline Rulings

1. CMS-specific labels and thresholds belong in the CMS domain pack. Shared backend services and frontend
   primitives use generic concepts such as feature, typology, source reference, risk projection, run, and
   provenance.
2. `entity_derived_signals` is the first candidate for feature values only if it can carry feature catalog
   version, transformation version, source refs, and score-run lineage without weakening existing analytics
   paths. If not, add a dedicated versioned feature-value table.
3. Score-all execution is an operator workflow, not an investigator screen. The UI should expose run state and
   score freshness where analysts need trust, while start/cancel/replay controls live in KB operations or
   readiness surfaces.
4. Risk read models are projections, not source of truth. They must be rebuildable and idempotent from stored
   score runs, feature values, alerts, cases, evidence packs, and graph metadata.
5. Evidence provenance is structured data first. Free-text reasoning can reference provenance IDs, but cannot be
   the only durable explanation path.
6. Any changed backend contract requires OpenAPI export and frontend API code generation before frontend work is
   considered complete.

## 3. Cross-Sprint Architecture

### 3.1 Domain Pack Schema

Extend the domain configuration schema with optional, domain-neutral sections:

- `typologies`: versioned definitions with `id`, `label`, `description`, `entity_types`, `severity_hint`,
  `feature_ids`, optional `policy_rule_ids`, and optional `playbook_ids`.
- `feature_catalog`: versioned definitions with `id`, `label`, `description`, `value_type`, `entity_types`,
  `source_mappings`, `peer_dimensions`, `threshold_hints`, `transformation_version`, and `provenance_notes`.
- `risk_projection_views`: optional domain labels and display hints for projection fields.

The Medicare fraud pack should define at least eight typologies and 20 feature definitions in Sprint 1. Other
packs can omit these sections and continue loading without warnings.

### 3.2 Persistence Model

PI 1 needs four persistence families:

| Family | Purpose | Minimum fields |
|--------|---------|----------------|
| Feature values | Durable normalized feature observations. | `knowledge_base_id`, `entity_type`, `entity_id`, `feature_id`, `value`, `normalized_value`, `catalog_version`, `transformation_version`, `source_refs`, `observed_at`, `score_run_id`. |
| Score runs | Durable score-all execution state. | `id`, `knowledge_base_id`, `status`, `requested_by`, `idempotency_key`, `model_version`, `catalog_version`, `started_at`, `finished_at`, `counts`, `error_summary`. |
| Risk projections | Fast read surfaces for alert queue, dashboard, entity summaries, and cohort queries. | `knowledge_base_id`, `entity_type`, `entity_id`, `risk_score`, `severity`, `top_typologies`, `top_features`, `evidence_pack_id`, `case_status`, `score_run_id`, `scored_at`, `source_versions`. |
| Evidence provenance | Structured lineage for recommendations and narratives. | `knowledge_base_id`, `evidence_pack_id`, `reference_type`, `reference_id`, `label`, `source_system`, `source_version`, `transformation_version`, `confidence`, `route_target`, `metadata`. |

Migration tests should prove new tables can be created on a clean database and that existing evidence packs and
alerts deserialize with default empty provenance fields.

### 3.3 API Surface

Proposed endpoint families, subject to route inventory before implementation:

- `GET /knowledgebases/{kb_id}/features/catalog`
- `GET /knowledgebases/{kb_id}/entities/{entity_type}/{entity_id}/features`
- `POST /knowledgebases/{kb_id}/score-runs`
- `GET /knowledgebases/{kb_id}/score-runs/{run_id}`
- `POST /knowledgebases/{kb_id}/score-runs/{run_id}/replay`
- `POST /knowledgebases/{kb_id}/score-runs/{run_id}/cancel`
- `GET /knowledgebases/{kb_id}/risk/entities`
- `GET /knowledgebases/{kb_id}/risk/entities/{entity_type}/{entity_id}`
- `GET /knowledgebases/{kb_id}/evidence-packs/{evidence_pack_id}/provenance`

All routes must enforce KB scoping through existing dependency patterns and must not expose cross-KB joins.

### 3.4 Frontend Surface

PI 1 frontend work is deliberately narrow:

- Feature and typology display primitives usable by the later cockpit, queue, case dossier, and evidence viewer.
- KB operations/readiness run controls for score-all status.
- Risk projection hooks and table/query helpers that later screens can reuse.
- Evidence provenance badges and expandable metadata in existing evidence panels.

No new large cockpit layout belongs in PI 1; that is `SAFE-CMS-005`.

## 4. Sprint 1 Spec: `SAFE-CMS-001`

**Goal:** Define a versioned CMS fraud typology and feature catalog that can drive scoring, explanations,
policies, workflows, dashboards, and future workflow templates.

**Implementation slices:**

- Add optional typology and feature catalog schema to domain config validation.
- Populate the CMS fraud pack with at least eight typologies and 20 feature definitions.
- Add backend models and service methods to read validated typologies/features by KB/domain.
- Decide, with tests, whether feature values extend `entity_derived_signals` or require a new table.
- Expose feature catalog and entity feature-value read APIs.
- Add frontend primitives for typology badges, feature lists, and source-lineage labels.

**Acceptance expansion:**

- CMS fraud pack validates with versioned typologies/features.
- Non-CMS packs load with no typology or feature-catalog sections.
- Feature values carry source refs and transformation version.
- A sample provider can show typology and feature labels through API and frontend smoke coverage.

**Verification gates:**

- Domain config schema tests for CMS and non-CMS packs.
- Feature service tests for catalog lookup and entity feature values.
- API contract tests for KB scoping and missing-KB behavior.
- OpenAPI export and frontend codegen.
- Focused frontend test for typology and feature rendering.

## 5. Sprint 2 Spec: `SAFE-CMS-002`

**Goal:** Make score-all analytics a durable, restartable, observable workflow that can score every eligible
entity in a KB.

**Implementation slices:**

- Add score-run and score-batch persistence with status transitions for queued, running, completed, failed,
  canceled, and replayed states.
- Add idempotency keys so repeated start/replay requests do not duplicate alerts or evidence packs.
- Add batch cursoring, retry policy, cancellation checks, and restart-safe run recovery.
- Record model version, feature catalog version, requested user/session, counts, timing, and error summary.
- Publish score-run events through the existing event bus pattern.
- Add KB operations/readiness UI for start, cancel, replay, and status inspection.

**Acceptance expansion:**

- A process restart leaves each active run resumable or explicitly failed with replay guidance.
- Replay targets failed batches without duplicating already completed entity outputs.
- Score freshness metadata is available to risk projections and UI consumers.
- A local score-all run completes against seeded/demo CMS data.

**Verification gates:**

- Repository transition tests.
- Workflow service tests for restart, cancellation, replay, and idempotency.
- API tests for start/status/cancel/replay.
- Event publication tests.
- Focused UI test for run status and disabled/enabled controls.
- Local seeded CMS score-all smoke.

## 6. Sprint 3 Spec: `SAFE-CMS-003`

**Goal:** Create fast, queryable risk read models for providers, beneficiaries, organizations, cohorts, alerts,
and dashboard rollups.

**Implementation slices:**

- Add risk projection persistence or materialized views after comparing query/update costs during the sprint
  inventory.
- Add projection writer services sourced from score runs, alerts, evidence packs, cases, and feature values.
- Add idempotent projection rebuild command/service.
- Expose paginated risk query APIs with filters for severity, typology, cohort, trend, status, and score age.
- Refactor frontend consumers away from ad hoc aggregation into generated API clients and stable hooks.

**Acceptance expansion:**

- Alert queue and dashboard consumers can read projection-backed data.
- Projections rebuild idempotently.
- APIs support the filters needed by `SAFE-CMS-006`.
- Each projection row includes score freshness, source versions, top typologies, and evidence references.

**Verification gates:**

- Migration and repository/query tests.
- Projection rebuild idempotency tests.
- API pagination, sorting, and filter tests.
- Frontend hook tests.
- Performance smoke using demo CMS data and representative filters.

## 7. Sprint 4 Spec: `SAFE-CMS-004`

**Goal:** Persist normalized provenance for scores, alerts, evidence packs, citations, narratives, graph context,
source records, model versions, prompts, and workflow runs.

**Implementation slices:**

- Add shared evidence provenance types and persistence.
- Enrich evidence-pack creation so generated narratives, scores, graph context, policy citations, feature values,
  model versions, prompt versions, and workflow runs can emit structured references.
- Preserve backward compatibility for existing evidence packs with default empty provenance.
- Add provenance response models and API mappers.
- Add frontend provenance badges and expandable metadata to existing evidence panels.

**Acceptance expansion:**

- Evidence packs persist structured refs instead of only free-text reasoning.
- Provenance survives API serialization and generated frontend types.
- Existing packs still deserialize/render.
- AI-generated narratives carry input evidence refs and model/prompt versions.

**Verification gates:**

- Shared type/backcompat tests.
- Evidence service tests.
- API mapper and route tests.
- Migration tests.
- OpenAPI export and frontend codegen.
- Focused UI evidence-panel smoke.

## 8. Required Sprint 1 Inventory

Before implementation begins, run a fresh read-only inventory and attach the findings to the Sprint 1 planning
handoff:

- Current API routes and dependency patterns for KB scoping.
- Analytics services, risk scoring, derived signal storage, alert/evidence-pack creation, and graph metadata paths.
- Domain config schema and all default domain packs.
- Frontend workbench, dashboard, alert, evidence, and KB operations components.
- Existing tests that should be extended rather than bypassed.

The inventory should decide whether feature values extend existing derived-signal storage or get dedicated
tables; that decision should be recorded before the first migration is written.

## 9. PI 1 Review Gates

Each sprint requires:

- Failing tests first for changed behavior.
- Contract regeneration after API/schema changes.
- Focused frontend tests for any rendered surface.
- `git diff --check` before review.
- Backend unit/API tests for touched modules.
- Browser verification for any non-trivial UI change.
- A closeout note with branch, commit, commands, evidence, limitations, and unblocked dependencies.

At the end of PI 1, run a system demo showing: CMS feature catalog loaded, a KB-scoped score-all run completed,
risk projection data queryable, and evidence provenance visible for at least one generated alert.
