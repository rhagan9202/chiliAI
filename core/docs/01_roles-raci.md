# Roles & RACI (Core Governance) — v0.1
File: core/docs/01_roles-raci.md  
Applies to: all domain packs, environments, and deployments.

## 1) Purpose
This document defines governance roles, responsibilities, and decision rights for operating the Program Integrity XAI Accelerator.  
It is designed to support effective, accountable AI governance and lifecycle controls (development, testing, deployment, continuous monitoring), including ongoing testing/validation, performance monitoring, and pause/discontinue actions when performance is not appropriate, consistent with OMB M‑25‑21. 

## 2) Governance model (simple, enforceable)
We operate the accelerator as a **triage-support system** by default:
- AI supports prioritization and investigation.
- Humans make consequential decisions and actions.
- Any expansion toward consequential decision-making triggers high-impact screening and increased controls. 

We use three checkpoints:
- Frame (SME framing + guardrails)
- Validate (evaluation gates + sign-off)
- Operate (monitoring + change control + pause/discontinue) 

## 3) Core roles (definitions)
### 3.1 Product/Accelerator Owner (PAO)
Accountable for:
- Core kit integrity and versioning (templates, indicator contract, eval harness, monitoring)
- Enforcing that gates are completed (C01–C09)
- Ensuring reusable assets and domain packs remain compatible with core

Decision rights:
- Block a release if required artifacts are missing
- Require a change request (C09) for any threshold/model/data changes
- Require evaluation re-run after changes

### 3.2 Program Integrity Operations Lead (PI Ops Lead)
Accountable for:
- Mission outcome and operational use of queues
- Defining investigator capacity and queue priorities (K, SLAs)
- Setting acceptance thresholds in C06 (with investigator input)
- Risk acceptance for triage operations at the lowest appropriate level (where delegated) 

Decision rights:
- Approve go-live for triage-only use (with required sign-offs)
- Pause an indicator if it creates operational harm or risk
- Request policy/ops changes in response to patterns discovered

### 3.3 Investigator Lead (INV Lead)
Accountable for:
- Investigator workflow integration and usability
- Label definitions and consistent labeling guidance
- Explanation usefulness rubric ownership
- Ensuring “evidence bundle” is sufficient for action

Decision rights:
- Reject indicator approval if explanations/evidence are not actionable
- Require changes to reason codes, evidence bundle requirements, and next-step guidance
- Recommend pause if explanation quality degrades

### 3.4 Analytics/ML Lead (AML Lead)
Accountable for:
- Indicator logic implementation (rules/peers/time-series/graph) and scoring pipelines
- Evaluation computations and reporting (P@K proxy, drift, stability)
- Root cause analysis of performance/drift incidents
- Maintaining model card (C04) and technical documentation 

Decision rights:
- Propose threshold/peer/model changes via C09
- Recommend pause for technical risk (drift, data leakage, evidence failure)
- Require holdout and leakage controls per eval harness 

### 3.5 Data Engineering Lead (DE Lead)
Accountable for:
- Data ingestion, freshness, and quality controls
- Feature build pipelines and lineage
- Data quality telemetry and reporting

Decision rights:
- Temporarily halt scoring/case generation if data freshness/quality makes outputs unsafe
- Require remediation before resuming

### 3.6 Security/Privacy Lead (SP Lead)
Accountable for:
- RBAC, audit logging, and evidence access controls
- Review of telemetry and sensitive access patterns
- Privacy constraints on data handling and logging 

Decision rights:
- Restrict access / disable accounts during security incidents
- Block go-live if auditability or access controls are insufficient
- Require changes to logging/telemetry to meet audit requirements

### 3.7 Domain SME(s)
Accountable for:
- Hypotheses, confounders, and operational context
- Reviewing reason codes and “what it does NOT mean” guardrails
- Providing input to acceptance thresholds and failure-mode interpretations

Decision rights:
- Advisory; can escalate concerns to PI Ops Lead/INV Lead.

### 3.8 Change Control Board (CCB) — v0.1 lightweight
Membership:
- PAO (chair), PI Ops Lead, INV Lead, AML Lead, SP Lead (as needed)

Accountable for:
- Reviewing and approving material changes in production
- Ensuring validation evidence exists for changes (C06/C09) 

## 4) RACI matrix (by activity)
Legend: R=Responsible, A=Accountable, C=Consulted, I=Informed

| Activity / Deliverable | PAO | PI Ops | INV Lead | AML Lead | DE Lead | SP Lead | SME |
|---|---|---|---|---|---|---|---|
| C01 Use-case Canvas (frame) | R | A | C | C | I | C | R |
| C02 Indicator Builder (draft indicators) | A | R | R | C | C | I | R |
| Domain pack schema/feature dictionary | A | C | C | R | R | C | C |
| Data provenance (C05) | C | I | I | A | R | C | I |
| High-impact screening (C03) | R | A | C | C | I | A | C |
| Eval plan & acceptance (C06) | A | R | R | R | C | C | C |
| Run evaluation + report | C | I | C | A | R | I | C |
| Go-live checklist (C07) | R | A | C | C | C | A | I |
| Monitoring dashboards & drift checks | A | C | C | R | R | C | I |
| Weekly ops review (C08) | R | A | R | C | C | C | C |
| Change request (C09) creation | A | C | C | R | C | C | I |
| Change approval (production) | A | A | A | C | C | A | I |
| Pause indicator (ops risk) | C | A | C | R | C | C | I |
| Pause indicator (security/privacy) | I | I | I | I | I | A | I |
| Resume indicator | R | A | C | R | C | A | I |

## 5) Decision rights (clear and testable)
### 5.1 Go-live decision (triage-only)
Required sign-offs:
- PI Ops Lead (A)
- SP Lead (A for access/audit readiness)
- PAO (R to confirm artifacts exist)
- INV Lead (C; can block for usability)
- AML Lead (C; can block for evaluation integrity)

### 5.2 Pause/discontinue (indicator or whole queue)
Triggers:
- Performance drop below threshold
- Drift alert + usability drop
- Evidence missing spike
- Data freshness breach
- Security anomaly

Authority:
- PI Ops Lead may pause any indicator for operational risk
- SP Lead may pause access / disable systems for security risk
- PAO may block releases and require rollback if governance violated

Requirement:
- Every pause must be logged (change log) with rationale and remediation plan. 

### 5.3 Scope expansion toward consequential decision-making
If any use case moves beyond triage support:
- Complete/refresh C03 determination
- Require independent review and stronger controls proportionate to risk, consistent with M‑25‑21 high-impact AI practices. 

## 6) Meeting cadence (v0.1)
- Weekly Ops Review (C08): PI Ops + INV + AML + PAO (SP as needed)
- CCB (change approval): biweekly or ad hoc for production changes
- Security/Privacy review: monthly (access dashboard) or per incident

## 7) Minimum artifact enforcement
No indicator may be marked `approved` unless:
- C02 completed, including evidence bundle and reason codes
- C06 acceptance criteria met and signed
- C04 model card updated with limitations
- Monitoring metrics exist for volume, precision proxy, drift, explanation usefulness
- Pause/discontinue policy is executable (manual acceptable in v0.1)

This enforces ongoing testing/validation and continuous monitoring expectations. 
