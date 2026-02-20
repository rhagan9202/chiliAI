# Crushing Fraud XAI Accelerator (v0.1)

A reusable, domain-pack-based accelerator for detecting anomalous patterns and potential fraud/waste/abuse schemes across healthcare claims, enrollment and entities, while keeping humans centric in the process (triage support; not automated enforcement).  
This repo is structured to be lifecycle-ready: Frame → Detect/Explain → Validate → Operate, with evaluation gates, monitoring, and a pause/discontinue mechanism.

---

## Why this exists

- **Enable Repeatable Productization**: To shift from one-off AI pilots to repeatable, productized AI solutions across HHS
- **Optimize for Cross-Domain Repeatability**: To ensure consistency and efficiency by standardizing:
  - Potential "indicator" and what it must output (scores, reason codes, evidence bundle pointers) 
  - How humans validate and improve it (investigator review + structured feedback + evaluation gates).
  - How it stays safe and stable (monitoring, drift checks, incident response, and governed change control).
- **Ensure Governance and Compliance**: To provide procurement and governance-ready artifacts by default, aligning with federal AI governance expectations (e.g., risk classification, test/validation plans, post-deployment monitoring, data rights required in OMB M-25-21 and M-25-22), as well as agency-wide guidance (HHS AI strategy, CMS AI Playbook)
- **Future-Ready Design**: To be easily adaptable for future advancements, allowing capabilities to translate into Agent Skills to automate certain or most steps over time

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
  - Screen specs, fields dictionary, navigation flow, and (optional) API contract for integrations.

### Domain packs (use-case specific)

Each folder under `domain-packs/` is a deployable module that defines:
- `schema.md`: Domain entity, relationship, and event model.
- `feature_dictionary.md`: Canonical feature families + windows + drift monitoring set.
- `evidence_bundle_spec.md`: What must be shown to investigators + completeness rules.
- `indicators.md`: Indicator library (reason codes, thresholds/logic, next steps).
- `eval_dataset_spec.md`: Sampling + labeling instructions tailored to the domain.
- `README.md`: How to run this domain pack and what it’s for.

v0.1 domain packs:
- `domain-packs/medicare_ffs_claims/`
- `domain-packs/marketplace_agent_broker_enrollment/`
- `domain-packs/medicaid_dental_vision_claims/`
- `domain-packs/dmepos_suppliers_risks/`

### Code starters (implementation scaffolding)

Optional templates and skeletons to accelerate technical implementation. These are not prescriptive and can be adapted to your stack and cloud provider.

- `code-starters/notebooks/` (exploratory and prototyping)
  - Feature building, indicator scoring, and explanation generation notebooks ready to customize per domain pack.
- `code-starters/pipelines/` (production orchestration)
  - Pipeline skeleton for scheduling and monitoring batch scoring jobs.
- `code-starters/iac/` (infrastructure as code)
  - Terraform skeleton for deploying compute, storage, and monitoring resources on cloud platforms.

---

## How to use the components (end-to-end)

### 1) Frame (SME + ops alignment)
**Use**:
- `core/docs/00_overview.md` + `core/docs/01_roles-raci.md` to align responsibilities, scope, and guardrails.
- `core/ui/fields_dictionary.md` + `core/ui/screens_spec.md` to ensure the workflow captures evidence, feedback, approvals, and audit fields.

**Record**:
- `core/templates/C01_use-case-canvas.md` (decision supported, downstream action, harms, guardrails, success criteria).

**Output**:
- A configured use-case instance (usecaseid/usecaseversion) pointing at one domain pack.

### 2) Configure indicators (domain pack → indicator contract)
**Use**:
- `core/docs/03_indicator-contract.md` to implement every indicator with the same output fields (score, reason codes, evidence pointers, next steps, monitoring hooks).
- `core/docs/04_explainability-spec.md` to ensure local/temporal/network explanations are evidence-linked and usable.
- `domain-packs/<pack>/indicators.md` + `domain-packs/<pack>/feature_dictionary.md` + `domain-packs/<pack>/evidence_bundle_spec.md` to implement scoring + evidence assembly per indicator.

**Record**:
- `core/templates/C02_indicator-builder.md` for each indicator promoted beyond "draft."

**Output**:
- A scoring job that produces (a) queues and (b) evidence bundles consistent with the contract.

### 3) Validate (evaluation gates + investigator labeling)
**Use**:
- `core/eval/` assets to build the test set, run evaluation, and standardize results (Precision@K proxy, explanation usefulness, evidence adequacy, stability).
- `domain-packs/<pack>/eval_dataset_spec.md` for domain-specific sampling and labeling guidance.

**Record**:
- `core/templates/C06_eval-plan-acceptance.md` (thresholds + acceptance gates) and `core/templates/C04_model-card-xai.md` (limitations + intended use).
- If needed: `core/templates/C03_high-impact-ai-screen.md` (triage-only vs consequential scope + added controls).

**Output**:
- A signed evaluation decision: approve/pilot/pause/revise, with an eval report and change requests for any modifications.

### 4) Go-live (ops + safety readiness)
**Use**:
- `core/monitoring/telemetry_contract.md` + `core/monitoring/dashboards_spec.md` to instrument throughput, quality, drift, evidence missingness, and governance activity.
- `core/monitoring/drift_checks.md` + `core/monitoring/incident_runbook.md` for response procedures when data shifts or quality drops.
- `core/monitoring/pause_discontinue_policy.md` to stop indicators safely when performance is not appropriate.

**Record**:
- `core/templates/C07_go-live-checklist.md` and schedule `core/templates/C08_weekly-ops-review.md`.

**Output**:
- A production pilot with monitoring, weekly review cadence, and change control enforced.

### 5) Operate (monitor → tune → govern)
**Use**:
- Dashboards + drift checks weekly; treat investigator feedback as the primary signal for precision proxy and explanation usefulness.
- `core/templates/C09_change-request.md` for any change to thresholds, peer groups, evidence requirements, features, or models (with rollback plan + validation).

**Output**:
- A governed iteration loop that improves top-K usefulness without silently changing behavior.

---

## Definition of Done (v0.1)

A use case is “live” only when:
- Data provenance is documented and approved (`core/templates/C05_data-provenance.md`).
- Each approved indicator has reason codes, evidence requirements, and next steps documented (`core/templates/C02_indicator-builder.md`) and implemented per the contract.
- Evaluation gates are met and signed (`core/templates/C06_eval-plan-acceptance.md`) including explanation usefulness and evidence adequacy.
- Monitoring dashboards and drift checks are running (`core/monitoring/`) and weekly ops review is scheduled (`core/templates/C08_weekly-ops-review.md`).
- Change control + pause/discontinue path is usable (`core/templates/C09_change-request.md` + `core/monitoring/pause_discontinue_policy.md`).

---

## Quick start (10 business days)

Follow `core/docs/02_delivery-playbook.md` to run one domain pack end-to-end with 3–5 indicators first, then scale indicator coverage after feedback is flowing.

---

## Data handling note

This repo is intended for deployment in client-controlled environments. Do not commit PHI/PII or sensitive datasets; use synthetic or de-identified examples only.
