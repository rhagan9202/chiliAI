# Program Integrity XAI Accelerator — Core Kit (Overview) v0.1

## Purpose
The Program Integrity XAI Accelerator is a reusable delivery kit for building and operating explainable AI indicators that help program-integrity teams prioritize investigation work across multiple healthcare domains.

The Core Kit standardizes the end-to-end lifecycle: **frame** the problem with SMEs, **validate** outputs with investigators using an evaluation harness, and **operate** safely with monitoring, change control, and pause/discontinue controls.

## What this repo provides (Core Kit + Domain Packs)
### Core Kit (common across all domains)
- Delivery playbook (2-week v0.1 implementation plan)
- Roles/RACI and decision rights (go-live, pause/discontinue, approvals)
- Indicator output contract (standard schema for scores, explanations, evidence bundles, routing)
- Explainability spec (local + temporal + network explanations)
- Evaluation harness (test set format, labeling, metrics, gates)
- Monitoring & ops (telemetry contract, dashboards, drift checks, incident runbook)
- Governance & change control (C09 change requests, approvals, rollback)
- Security & privacy principles (least privilege, auditability, data minimization)
- Reference architectures (Azure + AWS patterns)
- UI/UX spec (screens, fields, workflow integration)

### Domain Packs (use-case specific)
Each domain pack provides:
- Schema and feature dictionary
- Indicator library (starter set + reason codes + next steps)
- Evidence bundle spec
- Evaluation dataset spec

Initial domain packs (v0.1 target):
- Medicare FFS claims (Chili Cook-Off style claims anomaly → indicator workflow)
- Marketplace enrollment integrity (agent/broker misconduct detection)
- Medicaid dental/vision claims integrity

## Design principles
- Human-in-the-loop by design: AI supports triage and investigation; humans make consequential decisions.
- Evidence-linked explainability: every score must link to a reproducible evidence bundle.
- Standardization over bespoke: domain packs extend the core contract; they do not fork it.
- Lifecycle readiness: test/validate before go-live, monitor continuously, and pause/discontinue when needed.

## Quick start (for delivery teams)
1) Choose a domain pack.
2) Run an SME framing session and complete templates:
   - C01 Use-case canvas
   - C02 Indicator builder (3–5 indicators for v0.1)
   - C05 Data provenance
3) Implement the thin-slice workflow:
   - Triage queue → evidence viewer → feedback capture
4) Run evaluation per C06 and sign off go-live per C07.
5) Turn on monitoring and schedule weekly ops review per C08.
6) Enforce change control via C09 for any changes.

## Document map (core/docs)
- 01_roles-raci.md — governance roles and decision rights
- 02_delivery-playbook.md — two-week v0.1 implementation plan
- 03_indicator-contract.md — output contract and required fields
- 04_explainability-spec.md — explanation requirements and payload
- 05_eval-harness.md — evaluation design, gates, and metrics
- 06_monitoring-ops.md — ops cadence, dashboards, drift, alerting
- 07_governance-change-control.md — change taxonomy, approvals, rollback
- 08_security-privacy.md — privacy/security requirements
- 09_reference-architecture_azure.md — Azure reference architecture
- 10_reference-architecture_aws.md — AWS reference architecture
- 11_ui-ux_spec.md — screens, permissions, integrations
- 12_release-and-versioning.md — SemVer rules and release gates

## References (non-exhaustive)
- OMB Memorandum M-25-21 (AI governance, testing/validation, monitoring)
- CMS Crushing Fraud “Chili Cook-Off” materials (claims anomaly → indicator framing)
