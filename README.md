# Program Integrity XAI Accelerator (v0.1)

A reusable, domain-pack-based accelerator for detecting anomalous patterns and potential fraud/waste/abuse schemes across healthcare claims and enrollment data, while keeping humans meaningfully in the loop (triage support; not automated enforcement).  
This repo is structured to be lifecycle-ready: Frame → Detect/Explain → Validate → Operate, with evaluation gates, monitoring, and a pause/discontinue mechanism.

---

## Why this exists

Program integrity work is capacity-limited and evidence-sensitive. This accelerator standardizes:
- What an “indicator” is and what it must output (scores + reason codes + evidence bundle pointers + next steps).
- How humans validate and improve it (investigator review + structured feedback + evaluation gates).
- How it stays safe and stable (monitoring, drift checks, incident response, and governed change control).

---

## What this repo contains

### Core Kit (reusable across domains)

Core Kit components are meant to be used together; templates are just the “forms” that record decisions made while using docs/eval/monitoring/UI.

- `core/docs/` (build/run + contracts + governance)
  - Overview, roles/RACI, delivery playbook, indicator contract, explainability spec, evaluation harness guidance, monitoring/ops guidance, governance/change control, security/privacy, reference architectures, release/versioning.
- `core/templates/` (C01–C09 “decision artifacts”)
  - Use-case canvas, indicator builder, high-impact screening, model card, data provenance, eval plan/acceptance, go-live checklist, weekly ops review, change request.
- `core/eval/` (evaluation assets)
  - Test set format, scoring rubric, explanation quality rubric, evaluation report template.
- `core/monitoring/` (operate safely)
  - Telemetry contract, dashboards spec, drift checks, incident runbook, pause/discontinue policy.
- `core/ui/` (human-in-the-loop workflow spec)
  - Screen specs, fields dictionary, and (optional) API contract for integrations.

### Domain packs (use-case specific)

Each folder under `domain-packs/` is a deployable module that defines:
- `schema.md`: Domain entity/event model.
- `feature_dictionary.md`: Canonical feature families + windows + drift monitoring set.
- `evidence_bundle_spec.md`: What must be shown to investigators + completeness rules.
- `indicators.v0.1.md`: Indicator library (reason codes, thresholds/logic, next steps).
- `eval_dataset_spec.md`: Sampling + labeling instructions tailored to the domain.
- `README.md`: How to run this domain pack and what it’s for.

v0.1 domain packs:
- `domain-packs/medicareffsclaims/`
- `domain-packs/marketplaceagentbrokerenrollment/`
- `domain-packs/medicaiddentalvisionclaims/`

---

## How to use the components (end-to-end)

### 1) Frame (SME + ops alignment)
Use:
- `core/docs/00overview.md` + `core/docs/01roles-raci.md` to align responsibilities, scope, and guardrails.
- `core/ui/fieldsdictionary.md` + `core/ui/screensspec.md` to ensure the workflow captures evidence, feedback, approvals, and audit fields.

Record:
- `core/templates/C01use-case-canvas.md` (decision supported, downstream action, harms, guardrails, success criteria).

Output:
- A configured use-case instance (usecaseid/usecaseversion) pointing at one domain pack.

### 2) Configure indicators (domain pack → indicator contract)
Use:
- `core/docs/03indicator-contract.md` to implement every indicator with the same output fields (score, reason codes, evidence pointers, next steps, monitoring hooks).
- `core/docs/04explainability-spec.md` to ensure local/temporal/network explanations are evidence-linked and usable.
- `domain-packs/<pack>/indicators.v0.1.md` + `domain-packs/<pack>/feature_dictionary.md` + `domain-packs/<pack>/evidence_bundle_spec.md` to implement scoring + evidence assembly per indicator.

Record:
- `core/templates/C02indicator-builder.md` for each indicator promoted beyond “draft.”

Output:
- A scoring job that produces (a) queues and (b) evidence bundles consistent with the contract.

### 3) Validate (evaluation gates + investigator labeling)
Use:
- `core/eval/` assets to build the test set, run evaluation, and standardize results (Precision@K proxy, explanation usefulness, evidence adequacy, stability).
- `domain-packs/<pack>/eval_dataset_spec.md` for domain-specific sampling and labeling guidance.

Record:
- `core/templates/C06eval-plan-acceptance.md` (thresholds + acceptance gates) and `core/templates/C04model-card-xai.md` (limitations + intended use).
- If needed: `core/templates/C03high-impact-ai-screen.md` (triage-only vs consequential scope + added controls).

Output:
- A signed evaluation decision: approve/pilot/pause/revise, with an eval report and change requests for any modifications.

### 4) Go-live (ops + safety readiness)
Use:
- `core/monitoring/telemetrycontract.md` + `core/monitoring/dashboardsspec.md` to instrument throughput, quality, drift, evidence missingness, and governance activity.
- `core/monitoring/driftchecks.md` + `core/monitoring/incidentrunbook.md` for response procedures when data shifts or quality drops.
- `core/monitoring/pausediscontinuepolicy.md` to stop indicators safely when performance is not appropriate.

Record:
- `core/templates/C07go-live-checklist.md` and schedule `core/templates/C08weekly-ops-review.md`.

Output:
- A production pilot with monitoring, weekly review cadence, and change control enforced.

### 5) Operate (monitor → tune → govern)
Use:
- Dashboards + drift checks weekly; treat investigator feedback as the primary signal for precision proxy and explanation usefulness.
- `core/templates/C09change-request.md` for any change to thresholds, peer groups, evidence requirements, features, or models (with rollback plan + validation).

Output:
- A governed iteration loop that improves top-K usefulness without silently changing behavior.

---

## Repo layout (suggested)

- `core/docs/`
- `core/templates/`
- `core/eval/`
- `core/monitoring/`
- `core/ui/`
- `domain-packs/`
- `code-starters/` (optional notebooks/pipelines/IaC skeletons; implementation-dependent)

---

## Definition of Done (v0.1)

A use case is “live” only when:
- Data provenance is documented and approved (`core/templates/C05data-provenance.md`).
- Each approved indicator has reason codes, evidence requirements, and next steps documented (`core/templates/C02indicator-builder.md`) and implemented per the contract.
- Evaluation gates are met and signed (`core/templates/C06eval-plan-acceptance.md`) including explanation usefulness and evidence adequacy.
- Monitoring dashboards and drift checks are running (`core/monitoring/`) and weekly ops review is scheduled (`core/templates/C08weekly-ops-review.md`).
- Change control + pause/discontinue path is usable (`core/templates/C09change-request.md` + `core/monitoring/pausediscontinuepolicy.md`).

---

## Quick start (10 business days)

Follow `core/docs/02delivery-playbook.md` to run one domain pack end-to-end with 3–5 indicators first, then scale indicator coverage after feedback is flowing.

---

## Data handling note

This repo is intended for deployment in client-controlled environments. Do not commit PHI/PII or sensitive datasets; use synthetic or de-identified examples only.
