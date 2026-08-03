# CMS Fraud + Agentic Analytics SAFe Surge Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for implementation sprints and `superpowers:executing-plans` for checklist execution. Each sprint below is intentionally written as a self-contained feature plan, but workers must read the Program Guardrails, Shared Definition of Done, Dependency Map, and the sprint immediately before their assigned sprint before changing code.

**Date:** 2026-07-30
**Status:** planning baseline
**Scope:** 20 sprints, one sprint per high-impact feature from the CMS fraud detection and explainability product review
**Primary use case:** CMS fraud, waste, and abuse detection for provider, beneficiary, claims, enrollment, graph, policy, evidence, case, and RAG workflows
**Product objective:** Move chiliAI toward an industry-leading modular analytics and AI platform where users can build trustworthy, explainable, agentic workflows over knowledge graphs, data sources, analytics capabilities, and connectors.

## 1. Executive Summary

This surge is planned as a SAFe-style delivery train: 5 Program Increments (PIs), each containing 4 sprints. Each sprint delivers one of the 20 prioritized features from the design review. The ordering intentionally builds from analytical substrate, to investigator experience, to governance and explainability, to user-authored agent workflows, to platform scale and operational polish.

The plan assumes the existing chiliAI strengths remain the foundation:

- Knowledge-base scoped ingestion, records, graph, vector, analytics, monitoring, cases, policy, and RAG surfaces.
- Existing CMS fraud workbench direction: peer-group z-scores, risk scoring, graph visualization, explainability packs, policy intelligence, alerts, cases, and dashboard surfaces.
- Generated frontend API contracts as the source of truth for backend-visible model changes.
- Route-backed UI state where it improves reproducibility, deep links, and analyst handoff.
- Durable event/workflow behavior for ingestion and analytics fan-out.

The core delivery principle is: every sprint must improve the CMS fraud use case while adding reusable platform capability. CMS-specific labels, typologies, rules, and workflows belong in domain packs and configuration; reusable execution, provenance, workflow, connector, governance, and UI primitives belong in shared modules.

## 2. External Market And Mission Inputs

These inputs anchor the product direction and must be refreshed before PI planning and major demos:

- CMS DASG identifies fraud trends through subject matter collaboration, data mining, behavioral analytics, network analytics, predictive analytics, and machine learning.
- GAO-26-107799 describes CMS and UPIC analytic patterns including billing spikes, peer-to-peer analysis, risk scoring, predictive analytics, unstructured machine learning, rules-based models, geographic provider analyses, and peer network mapping. GAO also emphasizes that analytics generate investigative leads and evidence roadmaps rather than final determinations by themselves.
- CMS current fraud priorities include DMEPOS, ACA Marketplace, home health, hospice, enrollment moratoria, and program-integrity ROI reporting.

Planning implication: chiliAI should not merely score records. It must support lead generation, triage, evidence collection, action rationale, case progression, and auditability.

## 3. SAFe Structure

### 3.1 Portfolio Epics

| Epic | Intent | Success Signal |
|---|---|---|
| E1 CMS fraud analytics foundation | Make CMS fraud typologies, features, scoring, read models, provenance, and peer analytics production-grade. | Analysts trust scores because they can inspect features, cohorts, evidence, and lineage. |
| E2 Investigator operating system | Make Alert Feed, Investigation Workbench, Case Management, evidence navigation, and dashboards feel like one workflow. | A fraud analyst can move from lead to evidence to case decision without context loss. |
| E3 Explainable governance | Make every recommendation explainable, contestable, auditable, and versioned. | Every score, narrative, action, and override has an owner, evidence, and reason trail. |
| E4 Agentic workflow platform | Let users compose workflows over domain capabilities, tools, KG context, sources, approvals, and analytics safely. | Users can author and run KB-scoped workflows without engineers adding custom code per workflow. |
| E5 Enterprise-grade adaptable platform | Make connectors, readiness, visual system, model governance, and evaluation loops reusable across CMS and future domains. | New domains plug in via packs, connectors, models, and workflow templates instead of forks. |

### 3.2 Capabilities

| Capability | Sprints |
|---|---|
| Fraud signal layer | 1, 2, 3, 11, 12 |
| Evidence and explainability | 4, 7, 9, 10, 16, 20 |
| Analyst workflow UX | 5, 6, 8, 18, 19 |
| Domain and workflow authoring | 13, 14, 15 |
| Data source and connector platform | 17 |

### 3.3 Program Increment Cadence

| PI | Sprints | Theme | System Demo |
|---|---:|---|---|
| PI 1 | 1-4 | Analytics foundation | CMS provider risk scoring with persisted read model and inspectable evidence provenance. |
| PI 2 | 5-8 | Investigator workflow | Cockpit, queue, citations, and case dossier form one analyst path. |
| PI 3 | 9-12 | Governance and peer intelligence | Audit ledger, contestable explainability, cohorts, and identity resolution harden decisions. |
| PI 4 | 13-16 | Agentic workflow runway | Playbooks, user-authored flows, capability registry, and RAG contract closure enable safe orchestration. |
| PI 5 | 17-20 | Enterprise platform | Connectors, readiness controls, visual refinement, and model governance make the solution scalable. |

## 4. North-Star Outcomes And Metrics

| Outcome | Metric | Target By Sprint 20 |
|---|---|---|
| Faster triage | Median time from alert open to first disposition | Reduce by 50 percent in demo workflow. |
| Better lead quality | Share of high-priority alerts with at least 3 independent evidence types | 80 percent of high-priority CMS demo alerts. |
| Explainability adequacy | Evidence packs with narrative, citations, feature attributions, and provenance | 95 percent of scored alerts. |
| Workflow reliability | Durable workflow completion or explainable failure | 99 percent for replayable test/demo workflows. |
| Analyst trust | Every score/action has versioned inputs, model version, and reason trail | 100 percent of score-all and case actions. |
| Modularity | CMS-specific concepts isolated to domain packs/config/playbooks | No CMS literals in reusable orchestration primitives except tests/fixtures. |
| UX efficiency | Clicks from alert to cited source and Ask AI scoped question | 2 clicks or fewer from primary surfaces. |
| Evaluation maturity | Model/playbook regression suite with accepted baselines | Baselines and drift reports produced per release candidate. |

## 5. Shared Architecture Guardrails

- **Knowledge-base scope first:** every analytics, workflow, RAG, connector, and case action must carry `knowledge_base_id` through API, worker, and persistence boundaries.
- **Generated contract discipline:** any backend Pydantic model or route response consumed by frontend requires OpenAPI export, frontend API codegen, and frontend type/build verification.
- **Domain-pack separation:** fraud typologies, CMS labels, fraud pattern thresholds, connector mappings, prompts, and playbook templates belong in domain packs/configuration unless reuse is proven.
- **Event durability:** score-all, connector sync, derived-signal refresh, evidence generation, and workflow execution must be durable, idempotent, replayable, and observable.
- **Evidence lineage:** all AI summaries, scores, alerts, cases, and workflow actions must trace to data version, source record, graph neighborhood, feature value, prompt/model version, and execution run.
- **Human decision boundary:** analytics and agents recommend, prioritize, explain, and prepare actions; they do not silently take irreversible administrative action.
- **Safety-first ingestion:** never delete old data until replacement ingest and event publication are durable.
- **No hidden local-only state:** cross-page analyst state should be route-backed or persisted when it affects handoff, audit, replay, or reproducibility.
- **Capability registry over ad hoc imports:** workflow/tool execution must discover typed capabilities through a registry, not direct cross-module calls.
- **Fallbacks are explicit:** model, connector, SHAP, LLM, and workflow failures must degrade with visible status, logs, and audit events rather than silent omission.

## 6. Shared Definition Of Ready

A sprint is ready only when:

- The sprint card below has an assigned owner and reviewer.
- Expected affected backend modules, frontend surfaces, contracts, data models, and migrations have been mapped.
- Risk spikes are completed or timeboxed with explicit fallback decisions.
- Test strategy identifies unit, integration, contract, and browser coverage.
- Feature flags/config defaults are decided.
- Dependencies from prior sprints are accepted or a documented shim exists.

## 7. Shared Definition Of Done

A sprint is done only when:

- User-facing capability is implemented or the sprint is explicitly marked design-only.
- Backend tests cover core services, persistence, API contracts, and failure paths for touched modules.
- Frontend tests cover state, route behavior, accessibility-critical interactions, and empty/error states for touched views.
- OpenAPI and generated frontend API code are regenerated for contract changes.
- `git diff --check` is clean.
- Recommended gates pass for touched areas: backend `pytest`, backend `pyright`, backend `ruff`, frontend `npm run build`, frontend `npm run lint`, focused Vitest, and Playwright where UI changed.
- Demo evidence is captured in the sprint closeout: commands run, data used, screenshots or browser notes for UI, known limitations, and next sprint handoff.
- Documentation/runbook updates exist for new operator-visible behavior.

## 8. Dependency Map

| Sprint | Depends On | Unlocks |
|---:|---|---|
| 1 | Existing CMS domain pack and records ingest | 2, 3, 4, 6, 11, 13, 20 |
| 2 | 1, workflow/event substrate | 3, 4, 6, 9, 20 |
| 3 | 1, 2 | 5, 6, 11, 18 |
| 4 | 1, 2, 3 | 7, 8, 9, 10, 16 |
| 5 | 3, 4 | 6, 7, 8, 18, 19 |
| 6 | 3, 5 | 8, 9 |
| 7 | 4, 5 | 8, 10, 16 |
| 8 | 4, 5, 7 | 9, 10, 14 |
| 9 | 4, 8 | 10, 14, 20 |
| 10 | 4, 7, 9 | 14, 20 |
| 11 | 1, 3 | 12, 13, 20 |
| 12 | 1, 11 | 3, 6, 8, 11 |
| 13 | 1, 4, 11, 12 | 14, 15, 20 |
| 14 | 13, 15 readiness spike | 16, 17, 20 |
| 15 | 1, 4, 13 | 14, 16, 17 |
| 16 | 4, 7, 14, 15 | 20 |
| 17 | 15, ingestion durability patterns | 18, 20 |
| 18 | 3, 5, 17 | 19 |
| 19 | 5, 6, 7, 18 | 20 |
| 20 | 1-19 | Release candidate |

## 9. Risk Register And ROAM

| ID | Risk | Impact | Response | Owner |
|---|---|---|---|---|
| R1 | CMS-specific feature work leaks into shared workflow/runtime modules. | High | Use domain-pack schema boundaries and code review checklist; require reusable module names to be domain-neutral. | Architecture reviewer |
| R2 | Score-all workflows overload graph/vector/SQL stores on large KBs. | High | Add bounded batching, resumable cursors, per-stage caps, load tests, and cancellation. | Backend lead |
| R3 | Evidence provenance becomes too expensive to persist/query. | High | Persist normalized references and compact derived snapshots; benchmark reads before UI depends on them. | Data lead |
| R4 | UX becomes visually richer but slower for repeated analyst work. | Medium | Browser performance budgets, dense scanning layouts, keyboardable queue/case transitions. | Frontend lead |
| R5 | LLM narratives hallucinate or overstate findings. | High | Citation-first prompt contract, deterministic fallback, confidence labels, review queue, and contest flow. | Explainability lead |
| R6 | Connectors import unsafe or inconsistent source records. | High | Connector manifests, schema validation, quarantine states, replayable receipts, and bounded streaming. | Ingestion lead |
| R7 | User-authored workflows bypass RBAC/audit. | High | Typed capability registry, policy checks at every tool boundary, append-only execution ledger. | Platform lead |
| R8 | Generated API contract drift breaks frontend late in the surge. | Medium | Contract regen required per sprint; fail DoD when handwritten mirror types are used. | Full-stack reviewer |
| R9 | Model governance arrives too late to influence scoring design. | Medium | Add model version/provenance fields in early sprints even before full eval loops. | Analytics lead |
| R10 | The demo path passes while non-CMS domains regress. | Medium | Keep housing/alternate domain smoke tests for registry, readiness, and workbench rendering. | QA lead |

ROAM status at baseline: R2, R3, R5, R7 are unresolved and require sprint-level spikes. R1, R6, R8, R10 are owned by explicit guardrails. R4 and R9 are accepted with mitigation.

## 10. PI Objectives

### PI 1 Objectives

- Deliver a versioned CMS fraud typology and feature layer.
- Make score-all execution durable, observable, and replayable.
- Create production risk read models for UI/API consumers.
- Persist full evidence provenance for every score and alert.

### PI 2 Objectives

- Deliver a unified Fraud Investigation Cockpit.
- Upgrade Alert Feed into an analyst-grade queue.
- Make citations navigable to records, graph nodes, policies, and source documents.
- Deliver case dossiers that preserve evidence, chronology, decisions, and exports.

### PI 3 Objectives

- Add investigator-grade audit ledger coverage.
- Make explanations contestable and reviewable.
- Add cohort and peer-analysis APIs that expose benchmark context.
- Resolve CMS provider/beneficiary/source identities consistently.

### PI 4 Objectives

- Introduce versioned fraud playbooks.
- Add user-authored workflow definitions.
- Add a typed capability/tool registry.
- Close RAG streaming/filter/citation contract gaps.

### PI 5 Objectives

- Add first-class pull connectors.
- Add global KB/domain/readiness controls.
- Refine the enterprise visual system.
- Add model governance and evaluation loops.

## 11. Sprint Plans

### Sprint 1: CMS Fraud Typology And Feature Layer (`SAFE-CMS-001`)

**Feature goal:** Define a versioned CMS fraud typology and reusable feature catalog that can drive scoring, explanations, policies, workflows, dashboards, and workflow templates.

**User value:** Analysts can understand what kind of fraud pattern a lead represents and which normalized features produced it.

**Key stories:**

- `SAFE-CMS-001A`: As an analyst, I can see a fraud typology label such as DMEPOS overutilization, billing spike, peer outlier, referral-ring exposure, geographic anomaly, enrollment risk, or never-provided service risk.
- `SAFE-CMS-001B`: As a domain admin, I can version feature definitions in a CMS domain pack without editing analytics runtime code.
- `SAFE-CMS-001C`: As a reviewer, I can trace feature values back to raw fields, derived signal jobs, and transformation versions.
- `SAFE-CMS-001D`: As a platform engineer, I can reuse the feature catalog schema for non-CMS domains.

**Architecture scope:** Extend domain pack schema with fraud typologies, feature definitions, feature provenance, threshold hints, peer dimensions, and source mappings. Keep CMS labels/config in the CMS pack; reusable code should handle generic `typology`, `feature`, `feature_value`, and `source_ref` concepts.

**UX scope:** Add feature and typology display primitives for later use in Alert Queue, Cockpit, Case Dossier, and Explainability panels. This sprint can ship minimal UI behind existing workbench surfaces.

**Data and contract work:** Add typed backend models for feature definitions and normalized feature values. Expose read endpoints scoped by KB and entity. Regenerate frontend contracts.

**Derisking spikes:** Validate current CMS record schemas and derived signal store can represent the minimum typology list. Identify whether feature values belong in existing `entity_derived_signals` or a new versioned table.

**Acceptance criteria:**

- Versioned CMS typology and feature catalog exists and validates at config load.
- At least 8 CMS fraud typologies and 20 feature definitions are represented.
- Feature values include source lineage and transformation version.
- Non-CMS domain packs can omit CMS typologies without errors.

**Verification:** Domain config tests, analytics feature service tests, contract tests, OpenAPI/codegen, and a UI smoke test showing typology + feature labels for a sample provider.

### Sprint 2: Durable Score-All Workflows (`SAFE-CMS-002`)

**Feature goal:** Make score-all analytics a durable, restartable, observable workflow that can score every eligible entity in a KB.

**User value:** Operators can refresh risk scores for a CMS KB without manual scripts or silent partial failures.

**Key stories:**

- `SAFE-CMS-002A`: As an operator, I can start a KB-scoped score-all run and see queued, running, completed, failed, canceled, and replayed states.
- `SAFE-CMS-002B`: As an analyst, I can trust score freshness because the UI exposes score run timestamp and version.
- `SAFE-CMS-002C`: As an engineer, I can replay failed score batches without duplicating alerts.
- `SAFE-CMS-002D`: As a compliance reviewer, I can audit who started a run and which model/config version was used.

**Architecture scope:** Add durable workflow records, per-entity batch cursors, idempotency keys, cancellation, retry policy, and event publication. Reuse existing coordinator/event bus patterns.

**UX scope:** Add score-all action and run status to KB readiness/operations surfaces; do not overload the investigator UI with operator controls.

**Data and contract work:** Persist score run, batch, stage, counts, errors, model version, feature catalog version, and timing. Expose run status API and events for UI refresh.

**Derisking spikes:** Benchmark score-all on the 1 percent TN CMS subset and estimate full subset caps. Decide batch size and lock strategy.

**Acceptance criteria:**

- Score-all runs survive process restart and resume or fail with a replayable state.
- Re-running the same job does not duplicate alerts or evidence packs.
- Run status is visible through API and UI.
- Score freshness metadata is attached to risk read models.

**Verification:** Workflow service tests, repository tests, idempotency tests, failure/replay tests, focused API tests, and one local score-all run against seeded/demo CMS data.

### Sprint 3: Production Risk Read Models (`SAFE-CMS-003`)

**Feature goal:** Create fast, queryable risk read models for providers, beneficiaries, organizations, cohorts, alerts, and dashboard rollups.

**User value:** Analysts get responsive alert lists, dashboard metrics, and entity summaries without waiting for on-demand graph or JSONB aggregation.

**Key stories:**

- `SAFE-CMS-003A`: As an analyst, I can sort and filter provider risk by severity, typology, cohort, trend, status, and score age.
- `SAFE-CMS-003B`: As a dashboard user, I can see stable rollups sourced from persisted projections.
- `SAFE-CMS-003C`: As a developer, I can change score internals without breaking UI shape because read contracts are explicit.
- `SAFE-CMS-003D`: As an operator, I can rebuild projections when upstream data changes.

**Architecture scope:** Add risk projection tables or materialized views with versioned updater services. Keep writes event-driven and rebuildable.

**UX scope:** Refactor current score consumers to read from explicit API helpers/hooks instead of assembling local shapes from multiple endpoints.

**Data and contract work:** Add paginated and filterable risk endpoints. Include `knowledge_base_id`, entity identity, score, severity, top typologies, evidence pack refs, case status, and score freshness.

**Derisking spikes:** Compare SQL projection vs materialized view. Validate indexes with realistic filters.

**Acceptance criteria:**

- Alert Queue and Dashboard can use the read model without ad hoc aggregation.
- Projection rebuild is idempotent.
- API supports pagination, sorting, and filters needed for Sprint 6.
- Read model includes enough metadata to explain freshness and source versions.

**Implementation status 2026-08-03:** `SAFE-CMS-003` landed in scoped slices:
projection domain/service/API/dashboard consumer, followed by durable Postgres
`risk_projections` storage, repository-backed rebuild source, KB cleanup purge, and live
`risk.scored` projection writes. Later lifecycle fan-in can enrich alert/case/evidence refs,
but the production read-model storage and rebuild seam are no longer the open DoD gap.

**Verification:** Repository/query tests, migration tests, API pagination/filter tests, frontend hook tests, and performance smoke with demo data.

### Sprint 4: Persist Full Evidence Provenance (`SAFE-CMS-004`)

**Feature goal:** Persist normalized provenance for scores, alerts, evidence packs, citations, narratives, graph context, source records, model versions, prompts, and workflow runs.

**User value:** Every recommendation can be defended, reviewed, replayed, and exported.

**Key stories:**

- `SAFE-CMS-004A`: As an analyst, I can see exactly which records, claims, graph edges, policies, and feature values support an alert.
- `SAFE-CMS-004B`: As a reviewer, I can replay or compare evidence generated under different model/playbook versions.
- `SAFE-CMS-004C`: As an auditor, I can export evidence lineage without querying raw databases manually.
- `SAFE-CMS-004D`: As a workflow agent, I can cite evidence IDs rather than embedding unsupported text.

**Architecture scope:** Add provenance models and service methods that normalize references across record, graph, vector, policy, feature, model, prompt, and workflow domains.

**UX scope:** Add provenance badges and expandable details to evidence components. Full navigation is Sprint 7.

**Data and contract work:** Evidence references must include type, ID, label, source system, source version, transformation version, confidence, and route target where applicable.

**Derisking spikes:** Size evidence references for high-volume entities; evaluate deduplication and retention strategy.

**Acceptance criteria:**

- Evidence packs persist structured references instead of only free-text reasoning.
- Provenance survives contract serialization and frontend rendering.
- Existing evidence packs remain backward compatible.
- All AI-generated narratives carry input evidence refs and model/prompt versions.

**Verification:** Shared type tests, API mapper tests, migration/backcompat tests, evidence service tests, contract regen, and UI evidence panel smoke.

### Sprint 5: Unified Fraud Investigation Cockpit (`SAFE-CMS-005`)

**Feature goal:** Create a single workbench surface that combines entity profile, graph neighborhood, risk timeline, typology summary, evidence, policy signals, peer context, RAG chat launch, and case actions.

**User value:** Analysts stop stitching together dashboard, alerts, graph, evidence, policy, and RAG pages manually.

**Key stories:**

- `SAFE-CMS-005A`: As an analyst, I can open a provider and immediately see risk, graph, evidence, peer context, and case status.
- `SAFE-CMS-005B`: As an analyst, I can deep-link to an investigation state with KB, entity, alert, case, and selected evidence.
- `SAFE-CMS-005C`: As a supervisor, I can inspect the same cockpit state an analyst used when making a decision.
- `SAFE-CMS-005D`: As a non-CMS domain user, I get a domain-adapted cockpit using domain labels.

**Architecture scope:** Compose existing APIs first; add backend aggregation only where read-model gaps cause unacceptable latency or contract complexity.

**UX scope:** Dense operational layout, not a landing page. Primary first viewport should show entity, risk, current alert/case state, graph/evidence region, and action rail.

**Data and contract work:** Prefer route-backed state such as `/investigation/:entityId?kb=...&alert=...&case=...&evidence=...`.

**Derisking spikes:** Prototype layout at desktop and tablet widths. Verify graph and evidence do not fight for space.

**Acceptance criteria:**

- A CMS alert can open directly into the cockpit with correct KB/entity context.
- The cockpit renders useful empty states for missing graph, evidence, policy, or case data.
- It supports domain labels from config.
- No text overlaps at mobile, tablet, or desktop breakpoints.

**Verification:** Component tests for route parsing and empty states, Playwright for alert-to-cockpit navigation, accessibility checks for main actions, and screenshot review.

### Sprint 6: Upgrade Alert Feed To Analyst Queue (`SAFE-CMS-006`)

**Feature goal:** Transform the current Alert Feed into a high-throughput queue for triage, assignment, filtering, severity calibration, bulk operations, SLA awareness, and evidence preview.

**User value:** Analysts and supervisors can work CMS leads like a production investigation queue.

**Key stories:**

- `SAFE-CMS-006A`: As an analyst, I can filter by typology, severity, cohort, score freshness, status, assignee, and case state.
- `SAFE-CMS-006B`: As a supervisor, I can assign alerts and see aging/SLA risk.
- `SAFE-CMS-006C`: As an analyst, I can preview top evidence without leaving the queue.
- `SAFE-CMS-006D`: As a reviewer, I can understand suppression/dedup decisions.

**Architecture scope:** Build queue API on Sprint 3 read models and Sprint 4 evidence refs. Add assignment/status events if missing.

**UX scope:** Table/list hybrid optimized for scanning. Avoid large decorative cards; use density, columns, badges, keyboard focus, and persistent filters.

**Data and contract work:** Add queue-specific endpoint or query parameters for status, assignment, typology, severity, date, cohort, and evidence availability.

**Derisking spikes:** Validate current alert projection supports assignment and SLA fields; if not, add minimal projection extension.

**Acceptance criteria:**

- Queue supports saved URL state for filters and selected alert.
- Evidence preview links to cockpit/evidence detail.
- Bulk status changes are confirmed and audited.
- Empty and error states distinguish no data, no matching filters, and unavailable backend.

**Verification:** API filter tests, frontend table/filter tests, route state tests, keyboard navigation checks, and Playwright alert triage flow.

### Sprint 7: Citation-First Navigable Evidence (`SAFE-CMS-007`)

**Feature goal:** Make every evidence citation navigable to its concrete source: record, document chunk, graph node/edge, policy rule, feature value, workflow run, or model output.

**User value:** Analysts can verify claims quickly instead of trusting a narrative summary.

**Key stories:**

- `SAFE-CMS-007A`: As an analyst, I can click a citation and land on the exact source context.
- `SAFE-CMS-007B`: As a reviewer, I can distinguish raw evidence from derived/model-generated evidence.
- `SAFE-CMS-007C`: As a RAG user, I can ask questions scoped to selected evidence refs.
- `SAFE-CMS-007D`: As a developer, I can add new evidence types without rewriting citation rendering.

**Architecture scope:** Create a citation target resolver with typed source categories and route builders. Keep it shared across evidence panels, RAG, cockpit, and case dossier.

**UX scope:** Use compact citation chips, source-type icons, hover/focus previews, and side-panel detail. Avoid hiding citations under collapsed summaries.

**Data and contract work:** Standardize citation target payload and expose resolver endpoints only where frontend cannot build route from contract safely.

**Derisking spikes:** Inventory current citation shapes and route coverage. Identify source types without a stable route.

**Acceptance criteria:**

- Every evidence reference type has a deterministic render state.
- Unsupported/legacy refs render as non-clickable with reason text.
- RAG launches include shallow scalar filters compatible with backend contract.
- Citations preserve KB scope.

**Verification:** Citation helper tests, evidence component tests, RAG launch tests, route target tests, and Playwright click-through from evidence to source.

### Sprint 8: Case Dossiers (`SAFE-CMS-008`)

**Feature goal:** Build a durable case dossier that aggregates alert history, evidence, narrative, typologies, source documents, graph context, analyst notes, actions, decisions, and export-ready summaries.

**User value:** The case object becomes the authoritative investigation record.

**Key stories:**

- `SAFE-CMS-008A`: As an analyst, I can promote an alert into a case with evidence and context preserved.
- `SAFE-CMS-008B`: As a supervisor, I can review chronology, decisions, notes, and evidence changes.
- `SAFE-CMS-008C`: As an analyst, I can attach or remove evidence with reason codes.
- `SAFE-CMS-008D`: As an external reviewer, I can receive an export package with cited evidence and audit trail.

**Architecture scope:** Extend durable case models and services rather than keeping dossier state in frontend. Use event history for timeline.

**UX scope:** Case page should prioritize chronology, evidence bundle, decision state, and next actions. Keep notes, tasks, attachments, and exports available without burying evidence.

**Data and contract work:** Add dossier response model with evidence refs, timeline events, notes, status, assignee, related alerts/entities, and export metadata.

**Derisking spikes:** Confirm current `feedback_history` and case promotion contract can evolve without data loss.

**Acceptance criteria:**

- Case dossier opens from Alert Queue and Cockpit with correct route-backed context.
- Evidence additions/removals are audited with user, timestamp, and reason.
- Export package includes citations/provenance and excludes unsupported raw secrets.
- Cross-KB promotion remains blocked.

**Verification:** Case service tests, API tests for promote/update/export, frontend route/component tests, and Playwright alert-to-case-to-dossier flow.

### Sprint 9: Investigator-Grade Audit Ledger (`SAFE-CMS-009`)

**Feature goal:** Add append-only audit coverage for scores, alerts, assignments, case actions, evidence changes, explanations, workflow runs, connector syncs, and user decisions.

**User value:** chiliAI can withstand compliance, supervisory, and legal review of fraud investigation decisions.

**Key stories:**

- `SAFE-CMS-009A`: As an auditor, I can query a complete timeline of material actions for a KB, entity, alert, case, or workflow.
- `SAFE-CMS-009B`: As a supervisor, I can see who changed severity, assignment, status, evidence, or decision.
- `SAFE-CMS-009C`: As a platform engineer, I can add audit events from new modules through a typed API.
- `SAFE-CMS-009D`: As an operator, I can export audit slices for review.

**Architecture scope:** Add audit event model, writer interface, module integration points, query API, retention policy, and export path.

**UX scope:** Add audit timeline panels in case dossier and cockpit; add operator-facing ledger filters if time allows.

**Data and contract work:** Persist actor, action, target, KB, before/after summary, reason, correlation/run ID, timestamp, and source module.

**Derisking spikes:** Decide append-only storage shape and redaction rules for before/after values.

**Acceptance criteria:**

- Material user and system actions emit audit events.
- Audit event writing is failure-visible and does not corrupt primary transactions.
- Ledger queries are KB-scoped and permission-checked.
- Exports include provenance without leaking credentials/secrets.

**Verification:** Audit writer tests, transactional behavior tests, API authorization tests, frontend timeline tests, and export smoke.

### Sprint 10: Contestable Explainability (`SAFE-CMS-010`)

**Feature goal:** Let analysts challenge, annotate, approve, reject, or request regeneration of explanations and feature attributions.

**User value:** Explanations become reviewable artifacts, not one-way AI output.

**Key stories:**

- `SAFE-CMS-010A`: As an analyst, I can mark an explanation as useful, incomplete, misleading, or unsupported.
- `SAFE-CMS-010B`: As an explanation reviewer, I can see challenged explanations and their evidence refs.
- `SAFE-CMS-010C`: As a model owner, I can use challenge data for evaluation and prompt/model improvement.
- `SAFE-CMS-010D`: As an auditor, I can see explanation lifecycle history.

**Architecture scope:** Add explanation review state, feedback reasons, regeneration requests, and linkage to evidence/model/prompt versions.

**UX scope:** Add compact review controls beside narratives and attributions. Avoid generic thumbs-only feedback; require reason categories for negative feedback.

**Data and contract work:** Add explanation feedback models and API. Store feedback in audit ledger and model evaluation dataset queue.

**Derisking spikes:** Define whether regeneration is synchronous, queued, or score-all attached. Default to queued if LLM/SHAP may be slow.

**Acceptance criteria:**

- Analysts can challenge explanations with structured reasons and comments.
- Explanation status is visible in Cockpit and Case Dossier.
- Regeneration preserves prior versions and does not overwrite audit history.
- Feedback exports into Sprint 20 governance/eval pipeline shape.

**Verification:** Explainability service tests, feedback API tests, UI tests for review states, and audit ledger assertions.

### Sprint 11: Cohort And Peer-Analysis APIs (`SAFE-CMS-011`)

**Feature goal:** Expose cohort construction and peer-comparison analytics as first-class APIs and UI components.

**User value:** Risk scores become contextual: analysts can see why a provider is anomalous relative to appropriate peers.

**Key stories:**

- `SAFE-CMS-011A`: As an analyst, I can compare a provider against peers by specialty, geography, service mix, beneficiary mix, and time window.
- `SAFE-CMS-011B`: As a data scientist, I can inspect cohort membership and exclusion logic.
- `SAFE-CMS-011C`: As a domain admin, I can configure cohort definitions in a domain pack.
- `SAFE-CMS-011D`: As a workflow author, I can call peer analysis as a capability.

**Architecture scope:** Build cohort definitions and peer metrics on top of feature catalog and risk read models. Expose generic cohort primitives with CMS pack examples.

**UX scope:** Add peer comparison widgets for Cockpit, Alert Queue preview, and Dashboard drilldowns.

**Data and contract work:** Endpoints for cohort definitions, cohort membership, peer metric distributions, z-score context, and explanations.

**Derisking spikes:** Evaluate performance for high-cardinality peer queries. Add cached projections if live queries exceed budget.

**Acceptance criteria:**

- Peer analysis returns membership criteria, cohort size, metric distribution, entity value, z-score/percentile, and explanation.
- Cohort definitions are versioned and KB-scoped.
- UI communicates small-cohort or low-confidence conditions.
- APIs support workflow/capability registry integration.

**Verification:** Analytics tests, query performance smoke, API contract tests, frontend chart/table tests, and non-CMS domain omission test.

### Sprint 12: CMS Identity Resolution (`SAFE-CMS-012`)

**Feature goal:** Resolve provider, organization, beneficiary, enrollment, claim, address, and source-system identities into canonical graph entities with confidence and merge/split history.

**User value:** Analysts avoid fragmented risk views caused by inconsistent NPIs, addresses, organizations, source records, or claim references.

**Key stories:**

- `SAFE-CMS-012A`: As an analyst, I can see all source identities linked to a canonical provider/entity.
- `SAFE-CMS-012B`: As a data steward, I can review low-confidence merges and split incorrect identities.
- `SAFE-CMS-012C`: As a graph analyst, I can inspect identity edges and confidence.
- `SAFE-CMS-012D`: As a connector owner, I can map incoming identities through a shared resolution API.

**Architecture scope:** Add identity resolution service, canonical entity model, alias/source-ref model, confidence scoring, manual override, and event publication to graph/read models.

**UX scope:** Add identity panel in Cockpit and Dossier with source aliases, confidence, merge/split history, and review state.

**Data and contract work:** Support canonical ID, source IDs, NPI, TIN/organization if available, addresses, beneficiary IDs where permitted, source system, confidence, and decision history.

**Derisking spikes:** Define PII/PHI-safe display/redaction boundaries. Confirm demo data identity fields and legal constraints.

**Acceptance criteria:**

- Ingested records map to canonical entities with source refs.
- Manual merge/split actions are audited.
- Low-confidence matches are reviewable and do not silently affect high-stakes scores unless configured.
- Graph and read models update consistently after identity changes.

**Verification:** Resolver unit tests, ingest integration tests, graph update tests, audit tests, UI review tests, and redaction checks.

### Sprint 13: Versioned Fraud Playbooks (`SAFE-CMS-013`)

**Feature goal:** Add versioned fraud playbooks that define typologies, detection strategy, required evidence, workflow steps, RAG prompts, policy checks, and decision guidance.

**User value:** Organizations can standardize how CMS fraud leads are investigated and adapt playbooks without forking code.

**Key stories:**

- `SAFE-CMS-013A`: As a program lead, I can version and publish CMS fraud playbooks.
- `SAFE-CMS-013B`: As an analyst, I can see which playbook generated or guided an alert/case.
- `SAFE-CMS-013C`: As a workflow author, I can start from playbook templates.
- `SAFE-CMS-013D`: As a reviewer, I can compare decisions across playbook versions.

**Architecture scope:** Add playbook schema, validation, versioning, publication states, compatibility with domain packs, and references from alerts/evidence/cases/workflows.

**UX scope:** Add playbook badges and details to cockpit/cases; add initial management surface if no admin UI exists.

**Data and contract work:** Persist playbook ID/version, status, typologies, feature requirements, evidence checklist, workflow template refs, and prompt/model refs.

**Derisking spikes:** Decide whether playbooks live in static domain config, database, or both. Recommended baseline: config-authored seed plus DB-published versions.

**Acceptance criteria:**

- Playbooks validate before publication.
- Alerts/cases preserve playbook version at creation time.
- Updating a playbook does not mutate historical case meaning.
- CMS playbooks can be exported/imported as domain-pack artifacts.

**Verification:** Schema tests, migration tests, API tests, history/backcompat tests, UI display tests, and one seeded CMS playbook demo.

### Sprint 14: User-Authored Workflow Definitions (`SAFE-CMS-014`)

**Feature goal:** Let users compose agentic workflows over KB data, graph context, analytics capabilities, connectors, policies, approvals, RAG, evidence packs, and case actions.

**User value:** Users can construct repeatable fraud investigation flows without engineering every orchestration path.

**Key stories:**

- `SAFE-CMS-014A`: As a workflow author, I can define steps, inputs, outputs, conditions, retries, approvals, and failure handling.
- `SAFE-CMS-014B`: As an analyst, I can run an approved workflow against a CMS alert, entity, case, or KB.
- `SAFE-CMS-014C`: As an auditor, I can inspect every workflow execution and tool call.
- `SAFE-CMS-014D`: As a platform admin, I can restrict which capabilities a workflow may invoke.

**Architecture scope:** Build workflow definition schema and execution adapter layer over the existing durable workflow/event system. Evaluate Flowise community-code adaptation only as a UI/graph-authoring inspiration or embeddable adapter if license and architecture gates are satisfied; do not make Flowise a hard dependency of chiliAI runtime without an ADR.

**UX scope:** Start with form/schema-based authoring or minimal graph builder if faster; defer polished low-code canvas until capability registry and audit are reliable.

**Data and contract work:** Persist workflow definitions, versions, validation results, execution runs, step states, inputs/outputs, approval gates, and capability refs.

**Derisking spikes:** Prototype one CMS playbook workflow: enrich alert, gather peer context, generate evidence checklist, ask RAG scoped question, draft case note, require human approval.

**Acceptance criteria:**

- Workflow definitions validate statically before execution.
- Executions are KB-scoped, RBAC-checked, auditable, cancelable, and replayable.
- Workflows call capabilities only through the registry.
- Human approval steps block irreversible actions.

**Verification:** Workflow schema tests, execution engine tests, capability permission tests, audit tests, and end-to-end CMS workflow demo.

### Sprint 15: Capability And Tool Registry (`SAFE-CMS-015`)

**Feature goal:** Create a typed registry for analytics, graph, RAG, connector, evidence, case, policy, model, and approval capabilities available to workflows and agents.

**User value:** Workflow authoring is safe, discoverable, modular, and testable.

**Key stories:**

- `SAFE-CMS-015A`: As a workflow author, I can browse available capabilities with input/output schemas and permissions.
- `SAFE-CMS-015B`: As a module owner, I can register a capability without coupling to workflow internals.
- `SAFE-CMS-015C`: As a security admin, I can allow or deny capabilities by role, KB, domain, and environment.
- `SAFE-CMS-015D`: As an agent, I receive typed tool schemas and documented failure modes.

**Architecture scope:** Add registry interfaces, capability manifests, schema validation, permission checks, execution adapter, and observability hooks.

**UX scope:** Add a registry browser for admins/authors. It should show availability, permissions, schema, domain compatibility, and last health check.

**Data and contract work:** Capability metadata: ID, version, module, description, input schema, output schema, side-effect class, permission requirements, domain constraints, health, and examples.

**Derisking spikes:** Register 5 initial capabilities: peer analysis, evidence pack generation, RAG scoped query, case note draft, connector sync status.

**Acceptance criteria:**

- Workflows cannot call unregistered capabilities.
- Side-effecting capabilities require explicit permission and audit.
- Registry supports CMS and non-CMS domain compatibility metadata.
- Capability execution returns typed success/failure envelopes.

**Verification:** Registry unit tests, permission tests, workflow integration tests, API contract tests, and registry UI tests.

### Sprint 16: Close RAG Contract Gaps (`SAFE-CMS-016`)

**Feature goal:** Make RAG filters, streaming, citations, evidence scopes, KB context, and workflow/tool usage consistent across non-streaming chat, streaming chat, contextual launches, and agent workflows.

**User value:** Analysts and workflows ask questions against the intended evidence scope and can trust citations.

**Key stories:**

- `SAFE-CMS-016A`: As an analyst, I can launch Ask AI from alert, evidence, entity, case, policy, or cohort context.
- `SAFE-CMS-016B`: As a workflow author, I can call RAG with a typed scope and receive citation refs.
- `SAFE-CMS-016C`: As a reviewer, I can audit prompt, filters, context, citations, and response model version.
- `SAFE-CMS-016D`: As a frontend developer, I can use one helper surface for streaming and non-streaming RAG.

**Architecture scope:** Unify request/response models for RAG across streaming/non-streaming paths. Preserve shallow scalar filter contract unless backend model changes are explicitly made and codegen follows.

**UX scope:** Add Ask AI launch points that preserve context and avoid surprise scope changes. Show active scope clearly in chat.

**Data and contract work:** Typed RAG scope object, citation response parity, prompt/model version capture, and workflow capability adapter.

**Derisking spikes:** Audit existing RAG routes and frontend helpers for drift. Confirm streaming path forwards filters and citations consistently.

**Acceptance criteria:**

- Streaming and non-streaming RAG honor the same KB/filter/citation contract.
- Contextual launch URLs reproduce the same chat scope on reload.
- RAG outputs can be attached to evidence/case with provenance.
- Workflow RAG calls are auditable and permission-checked.

**Verification:** RAG route tests, streaming tests, frontend helper tests, route reload tests, workflow adapter tests, and Playwright scoped Ask AI flow.

### Sprint 17: First-Class Connectors (`SAFE-CMS-017`)

**Feature goal:** Add a connector framework for scheduled and manual pulls from CMS-like sources, filesystems, object stores, APIs, and partner systems with mapping, validation, quarantine, and replay.

**User value:** Users can keep fraud datasets current without manual uploads and fragile one-off scripts.

**Key stories:**

- `SAFE-CMS-017A`: As a data admin, I can configure a connector with source type, credentials reference, schedule, mapping, and KB target.
- `SAFE-CMS-017B`: As an operator, I can inspect sync runs, counts, failures, quarantined records, and replay controls.
- `SAFE-CMS-017C`: As a compliance reviewer, I can audit what data was pulled, from where, when, and under which mapping version.
- `SAFE-CMS-017D`: As a domain pack author, I can provide connector mapping templates.

**Architecture scope:** Add connector manifests, credential-reference handling, sync workflow, source adapters, validation/quarantine, receipts, idempotent upsert, and event publication.

**UX scope:** Connector management should show source health, last sync, next sync, schema status, quarantine, and actions.

**Data and contract work:** Persist connector definition, mapping version, sync run, source cursor, receipt, quarantine reason, and emitted ingest batch correlation.

**Derisking spikes:** Implement one local filesystem or object-store connector and one HTTP pull connector stub before broad adapter work.

**Acceptance criteria:**

- Connector sync publishes the same durable ingestion events as manual uploads.
- Failed syncs preserve prior data and provide replay/quarantine paths.
- Credentials are referenced, not exposed in API/UI/audit exports.
- Connector mapping is domain-pack compatible.

**Verification:** Connector adapter tests, workflow tests, ingestion integration tests, quarantine tests, API/UI tests, and bounded streaming tests.

### Sprint 18: Global KB, Domain, And Readiness Control (`SAFE-CMS-018`)

**Feature goal:** Provide a persistent global selector/control plane for active KB, domain, data readiness, analytics freshness, connector status, and workflow availability.

**User value:** Users understand what dataset/domain they are operating in and whether analytics are ready before making decisions.

**Key stories:**

- `SAFE-CMS-018A`: As an analyst, I can see and switch active KB/domain from primary app surfaces.
- `SAFE-CMS-018B`: As an operator, I can see readiness blockers for ingestion, graph, embeddings, analytics, connectors, and workflows.
- `SAFE-CMS-018C`: As a workflow author, I can see which capabilities are available for the selected KB/domain.
- `SAFE-CMS-018D`: As a reviewer, I can verify no page silently uses the wrong ready KB.

**Architecture scope:** Add a readiness aggregation API if current page-local checks are insufficient. Keep state URL-backed where workflow handoff needs reproducibility.

**UX scope:** Persistent app-level control, compact status indicators, readiness detail popover/panel, and clear disabled states for unavailable actions.

**Data and contract work:** Readiness response should include KB status, domain pack, source ingest state, graph state, vector state, analytics freshness, connector state, workflow/capability state, and warnings.

**Derisking spikes:** Inventory current page-level KB selection logic and identify inconsistent assumptions.

**Acceptance criteria:**

- Dashboard, Cockpit, Alert Queue, RAG, Cases, Policy, Connectors, and Workflows agree on active KB/domain context.
- Readiness blockers explain what action is unavailable and how to fix it.
- URL reload preserves context for investigation workflows.
- No-ready-KB state is explicit and tested.

**Verification:** Readiness API tests, frontend context/provider tests, route reload tests, cross-page Playwright smoke, and non-CMS domain smoke.

### Sprint 19: Enterprise Visual Design Refinement (`SAFE-CMS-019`)

**Feature goal:** Refine the UI into a cohesive enterprise analytics product with dense information design, consistent components, accessibility, responsive behavior, and domain-adapted styling.

**User value:** chiliAI feels credible, usable, and efficient for repeated analyst workflows.

**Key stories:**

- `SAFE-CMS-019A`: As an analyst, I can scan high-density risk/evidence/case information without visual clutter.
- `SAFE-CMS-019B`: As a keyboard user, I can navigate queue, cockpit, citations, tabs, and case actions accessibly.
- `SAFE-CMS-019C`: As a product owner, I can see consistent design language across Dashboard, Alert Queue, Cockpit, Cases, RAG, Policy, Connectors, and Workflows.
- `SAFE-CMS-019D`: As a developer, I can reuse documented components instead of recreating styling per page.

**Architecture scope:** Consolidate shared UI primitives and layout tokens. Avoid broad framework churn unless existing primitives cannot meet accessibility/responsiveness needs.

**UX scope:** Prioritize operational clarity: smaller headings in tools, stable dimensions, no nested cards, restrained palette, consistent icon buttons, clear status badges, and no overlapping text.

**Data and contract work:** Minimal unless component props reveal contract cleanup needs.

**Derisking spikes:** Run screenshots across core pages at desktop/tablet/mobile. Inventory repeated UI patterns and component duplication.

**Acceptance criteria:**

- Core CMS workflow pages share layout, typography, spacing, and status semantics.
- Text does not overlap or overflow in primary supported viewports.
- Keyboard and screen-reader affordances are tested for major controls.
- Visual changes do not hide analytical density behind marketing-style sections.

**Verification:** Component tests for shared primitives, Playwright screenshots, accessibility checks, frontend build/lint, and manual screenshot review.

### Sprint 20: Model Governance And Evaluation Loops (`SAFE-CMS-020`)

**Feature goal:** Add model, scoring, playbook, prompt, workflow, and connector evaluation loops with baselines, regression checks, drift reports, approval gates, and release evidence.

**User value:** The platform can improve models and workflows without losing trust, traceability, or operational control.

**Key stories:**

- `SAFE-CMS-020A`: As a model owner, I can register model/scoring/playbook versions with metadata and evaluation baselines.
- `SAFE-CMS-020B`: As a reviewer, I can compare new runs against accepted baselines before release.
- `SAFE-CMS-020C`: As an analyst lead, I can see whether challenged explanations or false positives are improving.
- `SAFE-CMS-020D`: As an auditor, I can trace which version influenced each alert/case decision.

**Architecture scope:** Add governance registry, eval datasets, metrics, baseline approval, drift reports, model/playbook/prompt/workflow version linkage, and release evidence generation.

**UX scope:** Add governance dashboard for model/playbook health, current production versions, pending approvals, drift, and feedback trends.

**Data and contract work:** Persist version records, eval runs, metric results, baseline decisions, drift summaries, approval state, and affected alerts/cases.

**Derisking spikes:** Define initial CMS eval set from demo data and investigator feedback. Choose metrics appropriate for lead-generation, not claim-denial automation.

**Acceptance criteria:**

- Every score, explanation, workflow recommendation, and playbook-guided action references versions.
- Eval runs compare candidate vs baseline and produce persisted reports.
- Challenged explanations and dispositions feed evaluation datasets.
- Release candidate cannot promote model/playbook changes without recorded approval.

**Verification:** Governance service tests, eval runner tests, API tests, UI dashboard tests, audit linkage tests, and release-candidate report generation.

## 12. Program-Level Backlog Traceability

| Sprint | Feature | Primary Module Areas | Primary Demo Moment |
|---:|---|---|---|
| 1 | CMS fraud typology/feature layer | domain config, analytics, shared types | Provider has named fraud patterns and feature values. |
| 2 | Durable score-all workflows | workflow, analytics, monitoring | Operator launches/replays score-all. |
| 3 | Production risk read models | persistence, analytics API, dashboard | Alert Queue loads fast filtered risk rows. |
| 4 | Persist full evidence provenance | evidence, explainability, shared refs | Evidence pack shows source lineage. |
| 5 | Unified Fraud Investigation Cockpit | workbench, graph, evidence, cases | One page tells the whole provider story. |
| 6 | Analyst Alert Queue | alerts, risk read API, UI | Analyst triages assigned high-risk leads. |
| 7 | Citation-first evidence | evidence, RAG helpers, routing | Analyst clicks citation to source. |
| 8 | Case dossiers | cases, evidence, exports | Alert becomes durable review package. |
| 9 | Audit ledger | audit, all action modules | Supervisor sees material action trail. |
| 10 | Contestable explainability | explainability, feedback, governance | Analyst challenges an unsupported narrative. |
| 11 | Cohort/peer APIs | peerstats, cohorts, charts | Provider compared against correct peers. |
| 12 | CMS identity resolution | ingest, graph, entities | Aliases merge into canonical provider. |
| 13 | Versioned fraud playbooks | domain packs, policy, workflows | DMEPOS playbook guides investigation. |
| 14 | User-authored workflows | workflow runtime, agents, approvals | User runs alert investigation workflow. |
| 15 | Capability/tool registry | platform registry, permissions | Workflow builder discovers safe tools. |
| 16 | RAG contract closure | RAG API, streaming, citations | Ask AI uses exact evidence scope. |
| 17 | First-class connectors | ingestion, connectors, schedules | Connector sync refreshes KB data. |
| 18 | Global KB/readiness control | app shell, KB API, readiness | User sees active KB and blockers. |
| 19 | Enterprise visual refinement | frontend system, accessibility | Core workflow feels cohesive and dense. |
| 20 | Governance/eval loops | evals, governance, audit | Release report proves version quality. |

## 13. Agent/Human Operating Model

Each sprint should use the same operating structure:

- **Planner:** reads this master plan, current sprint card, prior sprint closeout, and relevant specs; confirms scope and creates task checklist.
- **Explorer agent:** inventories real routes, services, schemas, UI components, persistence models, and tests before implementation.
- **Worker agent(s):** implement task-by-task with failing tests first where code changes are required.
- **Reviewer agent:** reviews diffs for behavioral regressions, contract drift, missing tests, domain leakage, audit/provenance gaps, and UX regressions.
- **QA/controller:** runs verification gates, browser checks, and demo script updates. Docker/browser/live-stack verification stays in the main/controller session.

Minimum handoff artifact per sprint:

- Branch/worktree name and base commit.
- Story IDs completed.
- Files changed by category: backend, frontend, contracts, migrations, docs.
- Commands run and results.
- Browser/demo evidence if UI changed.
- Known limitations.
- Next sprint dependencies that became unblocked or changed.

## 14. Program Ceremonies

| Ceremony | Cadence | Required Output |
|---|---|---|
| PI Planning | Before each 4-sprint PI | PI objectives, capacity, dependencies, ROAM update, demo target. |
| Sprint Planning | Start of each sprint | Sprint checklist, owner/reviewer assignment, DoR confirmation. |
| Architecture Sync | Twice per sprint | Decisions on schema, contracts, workflows, provenance, and domain-pack boundaries. |
| Product/UX Review | Mid-sprint and pre-demo | Screenshots, interaction notes, acceptance feedback. |
| System Demo | End of each PI | Working end-to-end CMS scenario and evidence capture. |
| Inspect And Adapt | End of each PI | Metrics review, defect trends, risk update, backlog adjustment. |

## 15. Release Strategy

- **PI 1 release candidate:** backend-visible foundation only; acceptable if UX is minimal but inspectable.
- **PI 2 release candidate:** analyst workflow demo; acceptable if workflow authoring is not yet available.
- **PI 3 release candidate:** governance and explainability review demo; acceptable if connector automation is not yet available.
- **PI 4 release candidate:** agentic workflow preview; must be permissioned, audited, and KB-scoped before any broad use.
- **PI 5 release candidate:** enterprise demo baseline; must include release evidence, eval reports, docs, and runbooks.

No release candidate should be promoted if:

- A score, explanation, case decision, workflow action, or connector sync lacks required KB scope.
- Frontend uses handwritten mirror API types for changed backend contracts.
- A user-authored workflow can call an unregistered or unauthorized capability.
- Evidence/provenance cannot support the demo's main fraud findings.
- UI changes create overlapping text or inaccessible primary controls on supported viewports.

## 16. Planning Artifact Checklist

Before implementation starts, create or update:

- `docs/superpowers/specs/` design/spec note for each PI or high-risk sprint.
- `docs/project/planning/backlog.md` entries for `SAFE-CMS-001` through `SAFE-CMS-020`.
- Sprint closeout template under the appropriate planning/runbook location if one does not already exist.
- Domain-pack ADR for CMS fraud typology/playbook schema.
- Workflow architecture ADR before adopting or embedding any Flowise-derived authoring component.
- Risk register updates after every PI.
- Demo script and validation checklist by the end of each PI.

## 17. Immediate Next Steps

- [x] Confirm whether Sprint 1 starts from current branch or a dedicated surge branch/worktree.
  - Formalization happened on `fix/normalize-kb-query-param` on 2026-08-02. Sprint 1 implementation should
    start from a dedicated surge branch/worktree after the read-only inventory, for example
    `feat/safe-cms-pi1-foundation`.
- [x] Create backlog rows for `SAFE-CMS-001` through `SAFE-CMS-020`.
  - Added to `docs/project/planning/backlog.md` on 2026-08-02.
- [x] Draft PI 1 implementation specs for Sprints 1-4.
  - Added `docs/superpowers/specs/2026-08-02-safe-cms-pi1-analytics-foundation-design.md`.
- [ ] Run a fresh route/API/component inventory before Sprint 1 implementation.
- [ ] Select demo KB/data subset and expected CMS fraud scenarios.
- [ ] Assign owner/reviewer/QA roles for PI 1.
