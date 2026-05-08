# ROLES-GUIDE.md
Version: 0.1.0

Purpose
- This is a “where do I look?” index for the Crushing Fraud XAI Accelerator repo: role → tasks → exact files.
- Use it to onboard new team members quickly and to prevent teams from using templates without also using the supporting docs, evaluation assets, monitoring standards, and UI workflow specs.

---

## Repo map (by folder)

- `core/docs/`: How the accelerator works, contracts, governance, security/privacy, and delivery playbook.
- `core/templates/`: C01–C09 artifacts that record decisions (use-case, indicators, evaluation gates, go-live, ops reviews, changes).
- `core/ui/`: Screen specs + fields dictionary for queue/evidence/feedback workflow and governance surfaces.
- `core/eval/`: Rubrics and report templates to run consistent evaluation and produce comparable results.
- `core/monitoring/`: Telemetry, dashboards, drift checks, incident response, and pause/discontinue policy.
- `domain-packs/`: Domain-specific schema, features, evidence bundle specs, indicator libraries, and evaluation dataset specs.
- `code-starters/`: Optional notebooks, pipeline skeletons, and infrastructure-as-code templates to accelerate technical implementation.

---

## Role → tasks → files

### PI Ops Lead (queue owner / risk acceptance)
Tasks
- Define what decision is supported, what action happens next, and what is out-of-scope automation.
- Set pilot success thresholds (Precision@K proxy, queue aging targets) and own go/no-go for operational rollout.
- Chair weekly ops review and authorize pause/resume actions when performance is not appropriate.

Files
- Frame: `core/docs/00_overview.md`, `core/docs/01_roles-raci.md`, `core/templates/C01_use-case-canvas.md`.
- Go-live gate: `core/templates/C06_eval-plan-acceptance.md`, `core/templates/C07_go-live-checklist.md`.
- Operate: `core/templates/C08_weekly-ops-review.md`, `core/monitoring/dashboards_spec.md`, `core/monitoring/pause_discontinue_policy.md`.
- Changes: `core/templates/C09_change-request.md`, `core/docs/07_governance-change-control.md` (or equivalent).

---

### Investigator Lead + Investigators (human validation loop)
Tasks
- Review top-K queues, validate evidence bundles, and submit structured feedback (outcome + reason tags + usefulness).
- Define labeling guidance so “insufficient evidence” is a first-class outcome and not forced into fraud/non-fraud.
- Provide explanation usability feedback that drives indicator tuning and evidence bundle improvements.

Files
- Workflow: `core/ui/screens_spec.md`, `core/ui/fields_dictionary.md`.
- Evidence + explainability expectations: `core/docs/04_explainability-spec.md`, `domain-packs/<pack>/evidence_bundle_spec.md`.
- Labeling + evaluation: `domain-packs/<pack>/eval_dataset_spec.md`, `core/templates/C06_eval-plan-acceptance.md`, `core/eval/explanation_quality_rubric.md`.
- Weekly feedback loop: `core/templates/C08_weekly-ops-review.md`.

---

### Data/ML Lead (features, scoring, evaluation execution)
Tasks
- Implement indicator scoring against the indicator contract and produce evidence-linked explanations.
- Build evaluation datasets (time-sliced/stratified), compute metrics, and produce evaluation reports for approvals.
- Monitor drift and performance signals; propose recalibration or pause when needed.

Files
- Contracts: `core/docs/03_indicator-contract.md`, `core/docs/04_explainability-spec.md`.
- Domain implementation: `domain-packs/<pack>/schema.md`, `domain-packs/<pack>/feature_dictionary.md`, `domain-packs/<pack>/indicators.md`.
- Evaluation: `core/eval/` (scoring rubric + report template), `domain-packs/<pack>/eval_dataset_spec.md`, `core/templates/C06_eval-plan-acceptance.md`.
- Monitoring + drift: `core/monitoring/telemetry_contract.md`, `core/monitoring/drift_checks.md`, `core/monitoring/dashboards_spec.md`.
- Changes: `core/templates/C09_change-request.md`, update `core/templates/C04_model-card-xai.md` as behavior changes.
- Implementation starters: `code-starters/notebooks/` (feature building, scoring, explanations).

---

### Data Engineering (pipelines, freshness, quality)
Tasks
- Land source data, enforce quality checks, build feature sets, and publish stable evidence pointers for reproducibility.
- Maintain freshness SLAs that evidence bundle completeness rules depend on.

Files
- Provenance + quality: `core/templates/C05_data-provenance.md`, `core/monitoring/telemetry_contract.md` (data ingest + quality events).
- Domain mapping inputs: `domain-packs/<pack>/schema.md` (logical), plus your local `data_mapping.md` (physical mapping) when you add it.
- Drift/data health: `core/monitoring/drift_checks.md`, `core/monitoring/dashboards_spec.md`.
- Implementation starters: `code-starters/pipelines/` (orchestration skeleton), `code-starters/iac/` (infrastructure templates).

---

### Security/Privacy (RBAC, auditability, sensitive data handling)
Tasks
- Ensure least-privilege access, audit logs for evidence access, and safe telemetry (no inappropriate PII/PHI in logs).
- Review high-impact screening when scope changes and verify pause/discontinue controls are operational.

Files
- Security posture: `core/docs/08_security-privacy.md` (or equivalent).
- High-impact / scope: `core/templates/C03_high-impact-ai-screen.md`.
- Audit + access monitoring: `core/monitoring/telemetry_contract.md`, `core/monitoring/dashboards_spec.md` (Access Audit dashboard), `core/monitoring/incident_runbook.md`.
- Evidence sensitivity: `domain-packs/<pack>/evidence_bundle_spec.md`.

---

### Product/Accelerator Owner (reuse, versioning, release governance)
Tasks
- Keep Core Kit stable and reusable while allowing domain packs to evolve independently.
- Enforce “no go-live without gates” and require change control for any behavior change.
- Own release notes and repo versioning strategy for core + domain packs.

Files
- Delivery + governance: `core/docs/02_delivery-playbook.md`, `core/docs/07_governance-change-control.md`.
- Release readiness: `core/templates/C07_go-live-checklist.md`, `core/templates/C09_change-request.md`.
- Ops loop: `core/templates/C08_weekly-ops-review.md`, `core/monitoring/pause_discontinue_policy.md`.

---

## “I need to…” quick pointers

- Add a new use case in an existing domain pack:
  - Start with `core/templates/C01_use-case-canvas.md`, then select `domain-packs/<pack>/` artifacts, then configure indicators using `core/templates/C02_indicator-builder.md`.

- Add a new indicator safely:
  - Read `core/docs/03_indicator-contract.md` + `core/docs/04_explainability-spec.md`, update `domain-packs/<pack>/indicators.md`, implement features from `domain-packs/<pack>/feature_dictionary.md`, and document via `core/templates/C02_indicator-builder.md`. Use `code-starters/notebooks/` as implementation templates.

- Run a pilot evaluation:
  - Follow `domain-packs/<pack>/eval_dataset_spec.md` + `core/templates/C06_eval-plan-acceptance.md`, score with the indicator contract outputs, and publish results using `core/eval/` report template + rubrics.

- Go live:
  - Complete `core/templates/C07_go-live-checklist.md`, ensure monitoring is implemented per `core/monitoring/` and schedule `core/templates/C08_weekly-ops-review.md`.

- Tune thresholds / change peer groups:
  - File `core/templates/C09_change-request.md`, run a mini-eval per `core/templates/C06_eval-plan-acceptance.md`, and update the model card `core/templates/C04_model-card-xai.md`.

- Pause an indicator:
  - Follow `core/monitoring/pause_discontinue_policy.md`, log the action via governance telemetry/change log, and record the decision in the next `core/templates/C08_weekly-ops-review.md`.

- Set up technical infrastructure:
  - Use `code-starters/iac/` for cloud infrastructure templates, `code-starters/pipelines/` for orchestration patterns, and `code-starters/notebooks/` for prototyping and development workflows.
