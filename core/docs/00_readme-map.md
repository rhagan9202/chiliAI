# /core/docs/00readme-map.md
Version: 0.1.0 [file:1]

Purpose
- This is a “where do I look?” index for the Program Integrity XAI Accelerator repo: role → tasks → exact files. [file:1]
- Use it to onboard new team members quickly and to prevent teams from using templates without also using the supporting docs, evaluation assets, monitoring standards, and UI workflow specs. [file:1]

---

## Repo map (by folder)

- `core/docs/`: How the accelerator works, contracts, governance, security/privacy, and delivery playbook. [file:1]
- `core/templates/`: C01–C09 artifacts that record decisions (use-case, indicators, evaluation gates, go-live, ops reviews, changes). [file:1]
- `core/ui/`: Screen specs + fields dictionary for queue/evidence/feedback workflow and governance surfaces. [file:1]
- `core/eval/`: Rubrics and report templates to run consistent evaluation and produce comparable results. [file:1]
- `core/monitoring/`: Telemetry, dashboards, drift checks, incident response, and pause/discontinue policy. [file:1]
- `domain-packs/`: Domain-specific schema, features, evidence bundle specs, indicator libraries, and evaluation dataset specs. [file:1]

---

## Role → tasks → files

### PI Ops Lead (queue owner / risk acceptance)
Tasks
- Define what decision is supported, what action happens next, and what is out-of-scope automation. [file:1]
- Set pilot success thresholds (Precision@K proxy, queue aging targets) and own go/no-go for operational rollout. [file:1]
- Chair weekly ops review and authorize pause/resume actions when performance is not appropriate. [file:1]

Files
- Frame: `core/docs/00overview.md`, `core/docs/01roles-raci.md`, `core/templates/C01use-case-canvas.md`. [file:1]
- Go-live gate: `core/templates/C06eval-plan-acceptance.md`, `core/templates/C07go-live-checklist.md`. [file:1]
- Operate: `core/templates/C08weekly-ops-review.md`, `core/monitoring/dashboardsspec.md`, `core/monitoring/pausediscontinuepolicy.md`. [file:1]
- Changes: `core/templates/C09change-request.md`, `core/docs/07governance-change-control.md` (or equivalent). [file:1]

---

### Investigator Lead + Investigators (human validation loop)
Tasks
- Review top-K queues, validate evidence bundles, and submit structured feedback (outcome + reason tags + usefulness). [file:1]
- Define labeling guidance so “insufficient evidence” is a first-class outcome and not forced into fraud/non-fraud. [file:1]
- Provide explanation usability feedback that drives indicator tuning and evidence bundle improvements. [file:1]

Files
- Workflow: `core/ui/screensspec.md`, `core/ui/fieldsdictionary.md`. [file:1]
- Evidence + explainability expectations: `core/docs/04explainability-spec.md`, `domain-packs/<pack>/evidence_bundle_spec.md`. [file:1]
- Labeling + evaluation: `domain-packs/<pack>/eval_dataset_spec.md`, `core/templates/C06eval-plan-acceptance.md`, `core/eval/explanationqualityrubric.md`. [file:1]
- Weekly feedback loop: `core/templates/C08weekly-ops-review.md`. [file:1]

---

### Data/ML Lead (features, scoring, evaluation execution)
Tasks
- Implement indicator scoring against the indicator contract and produce evidence-linked explanations. [file:1]
- Build evaluation datasets (time-sliced/stratified), compute metrics, and produce evaluation reports for approvals. [file:1]
- Monitor drift and performance signals; propose recalibration or pause when needed. [file:1]

Files
- Contracts: `core/docs/03indicator-contract.md`, `core/docs/04explainability-spec.md`. [file:1]
- Domain implementation: `domain-packs/<pack>/schema.md`, `domain-packs/<pack>/feature_dictionary.md`, `domain-packs/<pack>/indicators.v0.1.md`. [file:1]
- Evaluation: `core/eval/` (scoring rubric + report template), `domain-packs/<pack>/eval_dataset_spec.md`, `core/templates/C06eval-plan-acceptance.md`. [file:1]
- Monitoring + drift: `core/monitoring/telemetrycontract.md`, `core/monitoring/driftchecks.md`, `core/monitoring/dashboardsspec.md`. [file:1]
- Changes: `core/templates/C09change-request.md`, update `core/templates/C04model-card-xai.md` as behavior changes. [file:1]

---

### Data Engineering (pipelines, freshness, quality)
Tasks
- Land source data, enforce quality checks, build feature sets, and publish stable evidence pointers for reproducibility. [file:1]
- Maintain freshness SLAs that evidence bundle completeness rules depend on. [file:1]

Files
- Provenance + quality: `core/templates/C05data-provenance.md`, `core/monitoring/telemetrycontract.md` (data ingest + quality events). [file:1]
- Domain mapping inputs: `domain-packs/<pack>/schema.md` (logical), plus your local `data_mapping.md` (physical mapping) when you add it. [file:1]
- Drift/data health: `core/monitoring/driftchecks.md`, `core/monitoring/dashboardsspec.md`. [file:1]

---

### Security/Privacy (RBAC, auditability, sensitive data handling)
Tasks
- Ensure least-privilege access, audit logs for evidence access, and safe telemetry (no inappropriate PII/PHI in logs). [file:1]
- Review high-impact screening when scope changes and verify pause/discontinue controls are operational. [file:1]

Files
- Security posture: `core/docs/08security-privacy.md` (or equivalent). [file:1]
- High-impact / scope: `core/templates/C03high-impact-ai-screen.md`. [file:1]
- Audit + access monitoring: `core/monitoring/telemetrycontract.md`, `core/monitoring/dashboardsspec.md` (Access Audit dashboard), `core/monitoring/incidentrunbook.md`. [file:1]
- Evidence sensitivity: `domain-packs/<pack>/evidence_bundle_spec.md`. [file:1]

---

### Product/Accelerator Owner (reuse, versioning, release governance)
Tasks
- Keep Core Kit stable and reusable while allowing domain packs to evolve independently. [file:1]
- Enforce “no go-live without gates” and require change control for any behavior change. [file:1]
- Own release notes and repo versioning strategy for core + domain packs. [file:1]

Files
- Delivery + governance: `core/docs/02delivery-playbook.md`, `core/docs/07governance-change-control.md`. [file:1]
- Release readiness: `core/templates/C07go-live-checklist.md`, `core/templates/C09change-request.md`. [file:1]
- Ops loop: `core/templates/C08weekly-ops-review.md`, `core/monitoring/pausediscontinuepolicy.md`. [file:1]

---

## “I need to…” quick pointers

- Add a new use case in an existing domain pack:
  - Start with `core/templates/C01use-case-canvas.md`, then select `domain-packs/<pack>/` artifacts, then configure indicators using `core/templates/C02indicator-builder.md`. [file:1]

- Add a new indicator safely:
  - Read `core/docs/03indicator-contract.md` + `core/docs/04explainability-spec.md`, update `domain-packs/<pack>/indicators.v0.1.md`, implement features from `domain-packs/<pack>/feature_dictionary.md`, and document via `core/templates/C02indicator-builder.md`. [file:1]

- Run a pilot evaluation:
  - Follow `domain-packs/<pack>/eval_dataset_spec.md` + `core/templates/C06eval-plan-acceptance.md`, score with the indicator contract outputs, and publish results using `core/eval/` report template + rubrics. [file:1]

- Go live:
  - Complete `core/templates/C07go-live-checklist.md`, ensure monitoring is implemented per `core/monitoring/` and schedule `core/templates/C08weekly-ops-review.md`. [file:1]

- Tune thresholds / change peer groups:
  - File `core/templates/C09change-request.md`, run a mini-eval per `core/templates/C06eval-plan-acceptance.md`, and update the model card `core/templates/C04model-card-xai.md`. [file:1]

- Pause an indicator:
  - Follow `core/monitoring/pausediscontinuepolicy.md`, log the action via governance telemetry/change log, and record the decision in the next `core/templates/C08weekly-ops-review.md`. [file:1]
