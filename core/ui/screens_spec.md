# Core UI Screens Specification (v0.1)

Purpose: Define the minimum set of UI screens, user stories, navigation flow, role-based permissions, required actions, and validations for the Program Integrity XAI Accelerator Core UI, reusable across all domain packs.
This UI is a triage-support system by default: it prioritizes review work, shows evidence-linked explanations, captures structured human feedback, and enforces governance (eval gates, monitoring, change control, pause/discontinue).
The UI MUST avoid language implying automated enforcement (e.g., “fraud confirmed”) and MUST make “triage support, not a final decision” visible in relevant surfaces.

Applies to: Core Kit UI across domain packs (e.g., Medicare FFS claims, Marketplace agent/broker enrollment integrity, Medicaid dental/vision claims) with a consistent workflow and contracts.

---

## 1) Personas and roles

Primary personas (v0.1):
- PI Ops Lead (queue owner, operational risk acceptance, can pause indicators for operational risk).
- Investigator (case reviewer, evidence viewer, structured feedback submitter).
- Investigator Lead (quality owner, can block go-live for usability, reads health/governance).
- Analytics/ML (indicator/model owner, runs eval and drift jobs, proposes changes via change control).
- Security/Privacy (audit owner, controls sensitive evidence access, can pause for security risk).
- Admin (user/role management, configuration plumbing; limited business decision rights in v0.1).
- Viewer (read-only, restricted; optional in v0.1).

Notes on governance decision rights: go-live requires defined sign-offs, and every pause/discontinue must be logged with rationale and remediation plan.

---

## 2) Navigation and flows

### 2.1 Global navigation shell
Global elements (all screens):
- Header: app title, environment badge (dev/test/prod), tenant/program selector (if multi-tenant), user menu (profile/role/sign out).
- Left nav (role-filtered): Use-case Canvas, Indicator Builder, Risk Dashboard, Triage Queue, Indicator Health, Governance Change Log, Pause/Resume Controls, Security Audit (SP only), Admin (Admin only).
- Global search: entityId, caseId, externalCaseRef (if integrated).

### 2.2 Primary workflow (Frame → Validate → Operate)
Flow A — Frame (configure the use case): Use-case Canvas (UC01) → Indicator Builder (IND01/IND02) → (optional) Risk screening linkages (C03 template alignment).
Flow B — Validate (pre-go-live / continuous validation): Triage Queue (QUEUE01) → Case + Evidence Viewer (CASE01) → Feedback Panel (FB01) → Indicator Health (HLTH01) and Governance Log (GOV01) for evaluation and sign-off.
Flow C — Operate (post-go-live): Monitor Indicator Health (HLTH01) → Create Change Requests (GOV02) → Approve/Reject → Deploy/rollback → Pause/Resume/Retire (CTRL01) when triggers occur.

### 2.3 Integration patterns (UI)
Supported patterns (v0.1): native UI exporting to case management, embedded widget in existing case tools, or API-only integration with external case UI rendering.
Minimum integration requirement: caseId linkage to external case reference (if used) and ability to write back investigator feedback.

---

## 3) Screen catalog (IDs, stories, actions, validations)

### UC01 — Use-case Canvas (SME framing)
Goal: capture structured problem framing, guardrails, success metrics, and approvals so downstream indicator and triage behavior is defensible and auditable.

User stories:
- As a PI Ops Lead, I can create/edit the high-level definition of a use case (decision supported, what happens next, non-goals).
- As Security/Privacy, I can review scope/data/risk and confirm required controls and approvals.
- As Analytics/ML, I can see what entities, windows, and evidence expectations drive indicator design.

Entry points:
- Left nav → “Use-case Canvas”, or “Create new use case” CTA (PI Ops/Admin only).

Required actions:
- PI Ops MUST define triage-only boundaries and non-goals before any indicator can reach “pilot/approved”.
- Approvals section MUST record role + timestamp for required approvers per the governance model.

Validations:
- Required: useCaseName, domainPackId, owners/POCs, primary entity type, time windows, success metric targets (e.g., precision@K and evidence/explanation targets).
- Time windows must validate start < end and lookback aligns with indicator windows.
- “Sole basis for action” MUST be explicitly “No” where applicable to preserve triage-only stance.

Audit events:
- create/update use case, approvals recorded.

---

### IND01 — Indicator Builder (List)
Goal: manage indicator library (draft/pilot/approved/paused/retired) and ensure each indicator has reason codes, evidence requirements, next steps, and monitoring hooks.

User stories:
- As Analytics/ML, I can create and version indicator definitions.
- As PI Ops, I can see which indicators are active in production and their status.
- As SMEs (via PI Ops workflow), I can review indicator intent, reason codes, and “what this does NOT mean” guardrails.

Key UI elements:
- Table: indicatorId, name, owner, indicatorType (rule/peer/time-series/graph/ml/composite), status, last modified, domain pack scope.
- Filters: domainPackId, entityType, status, owner/team.

Actions (role-gated):
- Create new indicator (Analytics/ML, Admin).
- Open indicator detail (all with access).
- Propose change (creates change request) for any prod-impacting edit.

Validations:
- Cannot set indicatorStatus=approved unless required artifacts are present (C02 completed, C06 acceptance met, C04 model card updated, monitoring readiness) per the “no go-live unless…” enforcement.

Audit events:
- create indicator, status change requests initiated, edits saved.

---

### IND02 — Indicator Builder (Detail)
Goal: define the indicator contract inputs/logic, reason code UX, evidence requirements, and evaluation/monitoring links.

Tabs/sections (minimum):
1) Overview: identity, owner, status, unit-of-scoring (entity/entity-month/claim/event).
2) Logic & features: free-text logic + structured feature list and threshold definitions.
3) Reason codes & UX guardrails: reason code catalog, one-sentence explanation, “what this does NOT mean”, prohibited language.
4) Evidence requirements: required evidence items, time window, insufficient-evidence conditions.
5) Evaluation & monitoring: links/fields for baseline metrics, monitoring thresholds, drift/stability expectations.

Required actions:
- Define reason codes and next-step guidance for investigators (indicator contract requirement).
- Define insufficient-evidence conditions that force low confidence / INSUFFICIENT_EVIDENCE handling.

Validations:
- Required: indicatorName, entityType, indicatorType, reasonCodeCatalog (>=1), requiredEvidenceItems (>=1), evidence window days, owner, scope criteria.
- Reason code IDs must be unique within indicatorVersion and stable across releases where possible.
- Evidence requirements must be compatible with the Evidence Bundle Viewer payload structure.

Audit events:
- edits, proposed changes, indicator status transitions (via governance).

---

### RISK01 — Risk Dashboard (Entity-level)
Goal: show aggregate risk patterns across entities/indicators and support operational prioritization without forcing investigators into each case.

User stories:
- As PI Ops, I can see overall risk patterns and hotspot indicators.
- As Investigator Lead, I can identify clusters by region/program/entity type for QA focus.
- As Analytics/ML, I can sanity-check distributions and volume.

Key UI elements:
- Filters: time range, entity type, indicators, severity bands, program/region tags (if available).
- Summary cards: total scored, above-threshold counts, severity distribution, top indicators by volume.
- Entity table: entityId, displayName (if allowed), latest score (or max across indicators), severity, lastScoredAt, activeCase flag/caseId.
- Drill-in: entity detail panel (score timeline, contributing indicators/reason codes, link to open/create case).

Validations:
- Export is subject to access policy and must exclude raw PII/PHI by default.

Audit events:
- view dashboard, drill into entity, export summaries (if permitted).

---

### QUEUE01 — Triage Queue (Ranked items)
Goal: deliver investigator workbench with prioritized queue, filters, assignment, and SLA visibility.

User stories:
- As an Investigator, I see a prioritized list of items to review and open the evidence bundle quickly.
- As PI Ops, I manage queue configuration and assignments.

Key UI elements:
- Filters: severity bands, indicatorIds, entity types, assigned to me/unassigned, time range, queue bucket.
- Queue table columns: rank, entityId/displayName, indicator name/id, score + severity, evidence completeness, case status, assignedTo, lastViewedAt.
- Row click opens CASE01.

Required actions:
- Investigator MUST open CASE01 to view evidence before submitting a final disposition for that queue item.
- PI Ops MAY bulk reassign, and MAY mark duplicates/errors with reason (structured).

Validations:
- Assignment actions require an assignee and log timestamp.
- “Duplicate/error” requires a reason tag (controlled vocabulary).

Audit events:
- view queue, open case, reassign, mark duplicate/error.

---

### CASE01 — Case View + Evidence Bundle Viewer (Trust anchor)
Goal: show why flagged (reason codes), what evidence supports it (timeline/tables/network slice), and enable dispositions + escalation.

User stories:
- As an Investigator, I can review full context, understand “why flagged”, and record a structured disposition.
- As a reviewer, I can see “what this does NOT mean” to prevent over-reliance.

Layout (minimum):
1) Case header: caseId, externalCaseRef (if any), entity info, involved indicators, case status, assignedTo, openedAt.
2) Summary panel: short summary, top reason codes, “what this does NOT mean” list.
3) Evidence tabs:
   - Timeline (time-ordered events with source pointers).
   - Tables (domain-specific tabular views, each row with source pointer).
   - Network (optional; small suspicious subgraph when graph contributes materially).
4) Source record drill-in (permissioned): show underlying identifiers and raw record link only if allowed.
5) Embedded feedback panel (FB01) on same screen for low-friction labeling.

Required actions:
- Evidence completeness status MUST be visible and must influence confidence band (low when insufficient evidence).
- Any export action MUST be explicit, permissioned, and audited.

Validations:
- If required evidence elements are missing, UI MUST display “INSUFFICIENT_EVIDENCE” state and restrict confident dispositions unless investigator overrides with a reason tag.
- Case status transitions must follow allowed enums (e.g., new → inReview → closed/referred/escalated/needsMoreInfo).

Audit events:
- view evidence bundle, export evidence, change case status, escalate.

---

### FB01 — Feedback Capture (Inline on case)
Goal: capture structured labels and explanation/evidence quality for evaluation and continuous monitoring.

User stories:
- As an Investigator, I can submit Agree/Disagree/Insufficient evidence with reason tags and next step.
- As PI Ops/Analytics, I can use feedback to compute precision proxies and explanation usefulness trends.

Required fields (minimum):
- feedbackLabel: suspicious / not_suspicious / insufficient_evidence.
- reasonTags: data issue vs model/explanation issue vs expected behavior vs policy/program change (controlled vocabulary).
- explanationUsefulness (1–5) and evidenceAdequacy (1–5).
- optional: missingEvidenceReported, confusingReasonCodes, freeTextNotes.

Required actions:
- Closing a case SHOULD require a feedback submission (v0.1 enforcement recommended to avoid missing evaluation signal).
- “Insufficient evidence” label SHOULD prompt missing evidence selection (structured list).

Validations:
- explanationUsefulness and evidenceAdequacy must be integers 1–5.
- reasonTags must be selected (>=1) for suspicious/not_suspicious outcomes.
- If feedbackLabel=insufficient_evidence, missingEvidenceReported should be required (>=1) unless investigator provides justification.

Audit events:
- submit feedback (immutable record), edits not allowed post-submit (new record instead).

---

### HLTH01 — Indicator Health Dashboard (Quality, drift, evidence missingness)
Goal: enable operations to see yield, adoption, precision proxies, drift alerts, and trigger tune/pause decisions.

User stories:
- As PI Ops, I can monitor indicator usefulness and pause when performance degrades.
- As Analytics/ML, I can detect drift and plan calibrations via change control.
- As Investigator Lead, I can spot trust/usability failures (confusing reason codes, missing evidence).

Key UI elements:
- Period selector (daily/weekly), indicator selector, severity band breakdown.
- Metrics: items scored/queued, severity distribution, feedback count, precision@K (proxy), explanation usefulness avg, evidence adequacy avg, missing critical evidence rate.
- Alerts panel: drift/performance drop/explainability failure incidents with links.

Required actions:
- “Create change request” CTA from any metric anomaly (links to GOV02).
- “Pause indicator” CTA for authorized roles (links to CTRL01).

Validations:
- Precision proxy computations must clearly label “proxy” and define sample sizes (to avoid false certainty).

Audit events:
- view health, create change request, pause actions invoked.

---

### GOV01 — Governance Change Log (Read)
Goal: provide auditable trace of changes, approvals, validation results, and rollbacks.

User stories:
- As PI Ops/Security/Privacy, I can see all changes to indicators/use cases with approvals.
- As Analytics/ML, I can track which versions are live and what changed when.

Key UI elements:
- Table: changeRequestId, title, changeType(s), affectedIndicatorIds, requestedBy, requestedAt, decision, decisionAt.
- Detail view: motivation/risk assessment, proposed payload summary, validation plan/results pointers, rollback plan, approval records.

Validations:
- Production-impacting edits MUST be represented by a change request record.

Audit events:
- approve/reject/needs revision decisions (immutable).

---

### GOV02 — Change Request (Create/Edit/Decide)
Goal: enforce change control (C09) for thresholds/models/data/evidence/reason code UX changes and ensure validation + rollback readiness.

User stories:
- As Analytics/ML, I can propose a threshold calibration update with a validation plan.
- As PI Ops, I can approve/reject changes based on operational risk and evidence.
- As Security/Privacy, I can require access/audit changes before approval.

Required actions:
- Submitter MUST provide motivation/evidence, risk assessment, implementation plan, validation plan, and rollback plan.
- Approvers MUST record decision and comments.

Validations:
- Required: changeTitle, changeType(s), affected indicator(s)/use case, validation plan pointer, rollback plan fields.
- If changeType includes security/privacy control change, Security/Privacy approval is required before prod deploy.

Audit events:
- create change request, decision, rollback executed (if used).

---

### CTRL01 — Pause / Resume / Retire Controls (Ops safety)
Goal: make pausing/resuming/retiring indicators and use cases normal, auditable safety operations.

User stories:
- As PI Ops or Security/Privacy, I can pause indicators/use cases immediately when performance or security risk emerges.
- As downstream users, I can see which indicators are active/paused/retired and why.

Required actions:
- Every action MUST capture reason, effective time, issuer, and roles notified.
- The action MUST write to governance log and emit telemetry/audit events.

Validations:
- Only authorized roles can execute control actions.
- Resume SHOULD require remediation notes and (where applicable) a mini-eval/spot-check pointer.

Audit events:
- pause indicator, resume indicator, retire indicator/use case.

---

### AUD01 — Security Audit View (SP-focused)
Goal: audit evidence access, exports, governance actions, and support incident response.

User stories:
- As Security/Privacy, I can audit who viewed evidence, exported data, or performed governance actions.
- As Admin (incident support), I can retrieve an access trail quickly.

Key UI elements:
- Filters: date range, actorId/role, eventType, objectType (case/evidence/indicator/config/export).
- Table: timestamp, actor, role, eventType, object, result, error details.
- Drill-in: request metadata (ip/useragent) and related IDs.

Validations:
- Exporting audit logs is policy-gated and must be audited.

Audit events:
- audit log export, evidence access events.

---

### ADMIN01 — Admin (Users/Roles) (optional v0.1)
Goal: manage user roles/permissions and configuration plumbing without bypassing governance decision rights.

User stories:
- As Admin, I can assign roles (piops, investigator, analytics, securityprivacy, admin, viewer) and revoke access quickly.

Validations:
- Role changes must be audited and require justification notes in sensitive environments.

Audit events:
- role assignment changes.

---

## 4) Role-based permissions (screen-level)

Legend: V=view, E=edit/create, A=approve/decide, P=pause/resume/retire, X=export evidence, S=sensitive evidence drill-in.

| Screen | PI Ops | Investigator | Inv Lead | Analytics/ML | Security/Privacy | Admin | Viewer |
|---|---:|---:|---:|---:|---:|---:|---:|
| UC01 Use-case Canvas | V/E | V | V | V | V | V/E | V |
| IND01/IND02 Indicator Builder | V | V (read-only) | V | V/E | V (read-only) | V/E | V |
| RISK01 Risk Dashboard | V | V | V | V | V (restricted) | V | V (restricted) |
| QUEUE01 Triage Queue | V/E (assign) | V/E (work items) | V | V | V (restricted) | V | V (restricted) |
| CASE01 Evidence Viewer | V | V/E | V | V (as approved) | V/S | V/S | V (no S) |
| FB01 Feedback | V | E | V | V | V | V | V |
| HLTH01 Indicator Health | V/E (actions via GOV/CTRL) | V (optional) | V | V/E | V | V | V |
| GOV01/GOV02 Change Control | V/A (operational) | V | V | V/E | V/A (when required) | V | V |
| CTRL01 Pause/Resume | P | V | V | V (request only) | P | V | V |
| AUD01 Security Audit | V (limited) | — | — | — | V/E/X | V (limited) | — |
| ADMIN01 Admin | — | — | — | — | — | V/E | — |

Notes: Evidence drill-in and export should be explicitly permissioned and audited, with least-privilege defaults and data minimization (surrogate IDs in most UI surfaces).

---

## 5) Required validations and guardrails (cross-cutting)

### 5.1 Triage-only posture
UI copy MUST reinforce that outputs support prioritization and investigation and that humans make consequential decisions.
Any scope expansion toward consequential decision-making MUST trigger refreshed high-impact screening and stronger controls per the governance model.

### 5.2 Evidence completeness and confidence
Evidence completeness MUST be computed and displayed, and “insufficient evidence” MUST downgrade confidence and show explicit disclaimers.
Evidence viewing and exports MUST be audited and role-restricted.

### 5.3 Feedback as a first-class artifact
Every investigator disposition SHOULD produce a structured feedback record (labels + reason tags + usefulness/adequacy) to support continuous evaluation and pause triggers.
Separate operational labels from training labels where applicable and retain provenance of feedback.

### 5.4 Governance enforcement
Indicators cannot be “approved” without required artifacts and acceptance criteria, and all production-impacting changes must go through a change request with validation and rollback plans.
Pause/discontinue is a normal, logged safety mechanism, not an exception.

### 5.5 Non-functional requirements (v0.1)
Evidence bundle initial load target: ~3 seconds for typical cases, and queue/dashboards must paginate and lazy-load.
Accessibility: keyboard navigation and WCAG-aligned contrast for core workflows.

