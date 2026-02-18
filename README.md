# Crushing Fraud XAI Accelerator (v0.1)

A reusable, domain-pack–based accelerator for detecting anomalous patterns and potential fraud schemes across healthcare claims and enrollment data, while keeping humans meaningfully in the loop.

## Why this exists
This accelerator packages repeatable, explainable AI workflows to:
- Detect anomalies and trends that can be translated into novel program-integrity indicators (starting from Medicare FFS claims as in the CMS “Crushing Fraud” Chili Cook-Off framing). 
- Reduce labor-intensive analytic processes while maintaining effective oversight through human review and auditable governance.

## What it supports (v0.1)
This repo is designed as a **Core Kit + Domain Packs** model:

### Core Kit (reusable across all domains)
- Indicator contract (standard output format: score + reason codes + evidence bundle pointers + next steps)
- Human-in-loop workflow (SME framing → investigator validation → operational monitoring)
- Evaluation harness and go-live gates (testing/validation requirements + acceptance criteria)
- Monitoring & operations (telemetry contract, drift checks, weekly ops review)
- Governance/change control (auditable change log, approvals, pause/discontinue policy)
- UI/UX specifications (common screens + field dictionary)
- Reference architectures (AWS + Azure secure deployment patterns)

### Domain Packs (use-case specific)
- Schema + feature dictionary + indicator library + evidence bundle spec + eval dataset spec

Included domain packs in v0.1:
- Medicare FFS claims (Hospice / Part B / DME style workflows)
- Marketplace enrollment integrity (agent/broker)
- Medicaid claims integrity (dental / vision)

## How the accelerator works (high level)
1) **Frame**: SMEs define the problem, acceptable evidence, and indicator hypotheses.
2) **Detect**: Indicators score entities/events (rules, peer outliers, time-series, graph patterns; models can be added behind the same contract).
3) **Explain**: Every case includes (a) reason codes and (b) an evidence bundle; optional local/network/temporal explanation payloads.
4) **Validate**: Investigators label outcomes and explanation usefulness; feedback drives threshold tuning and quality metrics.
5) **Operate**: Ongoing monitoring detects drift and performance degradation; governance processes control changes and enable pause/discontinue.

## Safety, governance, and “human elements”
This accelerator is designed to support decision-making, not automate enforcement.
Key controls:
- Mandatory human review prior to any consequential action.
- Evaluation gates before go-live, and ongoing testing/validation after go-live.
- Continuous monitoring and an explicit pause/discontinue mechanism when performance is not appropriate.
- Audit logging and change control for thresholds/models/data changes.

(See `/core/docs/` and `/core/templates/` for operational templates and required artifacts.)

## Repo structure
- `/core/` : common docs, templates, UI specs, evaluation, monitoring, governance, reference architectures
- `/domain-packs/` : domain-specific schemas, indicators, evidence bundles, eval dataset specs
- `/code-starters/` : optional starter notebooks/pipeline skeletons/IaC skeletons (implementation dependent)

## Quick start (for a new delivery team)
1) Pick a domain pack under `/domain-packs/`.
2) Run an SME framing workshop and complete:
   - `core/templates/C01_use-case-canvas.md`
   - `core/templates/C02_indicator-builder.md` (5–10 indicators to start)
   - `core/templates/C05_data-provenance.md`
3) Implement the triage workflow (UI or integration) to support:
   - Case queue + evidence bundle viewer + investigator feedback capture
4) Execute evaluation and sign-off:
   - `core/templates/C06_eval-plan-acceptance.md`
   - `core/templates/C07_go-live-checklist.md`
5) Go live with monitoring and weekly ops:
   - `core/templates/C08_weekly-ops-review.md`
   - Change control via `core/templates/C09_change-request.md`

## Definition of Done (v0.1 go-live)
A use case is considered “live” only when:
- Data provenance is documented and approved.
- Indicators have evidence bundles and reason codes.
- Evaluation acceptance criteria are met and signed off.
- Monitoring dashboards are live and weekly ops review is scheduled.
- Change control and pause/discontinue workflow are in place.

## Who should use this repo
- Program integrity operations leads
- Investigators / case reviewers
- Analytics/ML engineers and solution architects
- Security/privacy/governance reviewers

## Contributing and versioning
- Core Kit changes require governance approval and CHANGELOG updates.
- Domain pack changes must preserve the core indicator contract.
- Any threshold/model/data change must be logged via the Change Request template.

## License / data handling note
This repo is intended to be deployed in client-controlled environments.
Do not commit sensitive datasets or PII/PHI. Use synthetic or de-identified examples only.

