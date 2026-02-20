# Core UI Navigation Flow (v0.1)

Purpose: Define the navigational routes and end-to-end user flows across Core UI screens, and map each key UI action to the telemetry/audit events required by `core/monitoring/telemetrycontract.md`.
This document is aligned to the v0.1 intent: triage support (not automated enforcement), human-in-the-loop validation, and operational governance (monitoring + change control + pause/discontinue).

Related specs (normative):
- `core/ui/screens_spec.md` (screen catalog, required actions, validations).
- `core/ui/fields_dictionary.md` (canonical field names for case, evidence bundle, feedback, governance).
- `core/monitoring/telemetrycontract.md` (event envelope and required events).
- `core/monitoring/dashboardsspec.md`, `core/monitoring/driftchecks.md` (how telemetry rolls up into ops + drift + trust dashboards).
- `core/docs/governance-change-control.md` (approval gates, C09 change request discipline).

---

## 1) Route map (UI IA)

Routes are role-filtered in left navigation; deep links may exist (e.g., `/case/:case_id`) but must enforce RBAC on load.

Core routes:
- `/use-cases` → UC01 Use-case Canvas (list/select; optional list in v0.1).
- `/use-cases/:use_case_id` → UC01 Use-case Canvas (detail).
- `/indicators` → IND01 Indicator Builder (list).
- `/indicators/:indicator_id` → IND02 Indicator Builder (detail).
- `/risk` → RISK01 Risk Dashboard.
- `/queue/:queue_name` → QUEUE01 Triage Queue.
- `/case/:case_id` → CASE01 Case View + Evidence Bundle Viewer (includes FB01 inline).
- `/health` → HLTH01 Indicator Health Dashboard.
- `/governance/changes` → GOV01 Governance Change Log (read).
- `/governance/changes/new` → GOV02 Change Request (create).
- `/governance/changes/:change_id` → GOV02 Change Request (detail/decide).
- `/controls` → CTRL01 Pause/Resume/Retire Controls.
- `/audit` → AUD01 Security Audit View.
- `/admin` → ADMIN01 Admin (optional v0.1).

Global search (header):
- Search by `entity_id`, `case_id`, `external_case_ref`.
- Results link to `/case/:case_id` when a case exists; otherwise to RISK01 entity drill-in.

---

## 2) Canonical telemetry naming (and legacy mapping)

The telemetry contract appears in two compatible “shapes” in v0.1 materials:
- Canonical (recommended): `queueviewed`, `caseopened`, `evidenceviewed`, `feedbacksubmitted`, `casestatuschanged`, etc.
- Legacy UI event names that appeared earlier: `uiviewqueue`, `uiopencase`, `uiviewevidencebundle`, `uiexportevidence`, `uisubmitfeedback`, `uichangecasestatus`.

### 2.1 Compatibility mapping
Implementations MAY emit canonical event names only, or MAY emit both during transition; downstream dashboards must map legacy → canonical.

| Canonical eventname (recommended) | Legacy eventtype (if present) |
|---|---|
| `queueviewed` | `uiviewqueue` |
| `caseopened` | `uiopencase` |
| `evidenceviewed` | `uiviewevidencebundle` |
| `evidenceexported` (optional alias; see note) | `uiexportevidence` |
| `feedbacksubmitted` | `uisubmitfeedback` |
| `casestatuschanged` | `uichangecasestatus` |
| `indicatorpaused` | `safetycontrolaction` (actiontype=pauseindicator) |
| `indicatorresumed` | `safetycontrolaction` (actiontype=resumeindicator) |

Note: If you already log `uiexportevidence` as defined, you can treat it as the export event for dashboards/audit; a separate canonical `evidenceexported` is not required in v0.1.

---

## 3) End-to-end navigation flows (with telemetry)

### Flow A — Frame (Use-case + Indicator definition)
Goal: Create/maintain the framed use case and indicator definitions with explicit guardrails, evidence requirements, and governance-ready approvals.

A1. Enter UC01 Use-case Canvas
1) User navigates to `/use-cases/:use_case_id` (UC01).
2) System enforces RBAC; if denied → emit `accessdenied`.
3) User views the use case definition (triage-only intent, non-goals, evidence requirements, success metrics, approvals).
Telemetry:
- (Optional) emit a generic `securityaccessevent` (objecttype=usecase, action=view, result=success) if audit wants full coverage.

A2. Edit use case (role-gated)
1) PI Ops Lead (or Admin) edits fields and saves changes.
2) For production-impacting changes (scope, data sources, guardrails, success metric targets), user SHOULD be routed to GOV02 to raise a change request before applying the change in prod.
Telemetry:
- `governancechangerequestcreated` / `changerequestcreated` (changetype includes datachange/uichange/securitychange as applicable; rationalesummary references UC01 scope change).

A3. Navigate to IND01/IND02
1) From UC01, user clicks “View indicators in scope” → `/indicators?use_case_id=...`.
2) Analytics creates/edits indicator in IND02, including reason codes, evidence requirements, and “what this does NOT mean”.
Telemetry:
- For draft-only saves: log locally (optional) but do not require governance events.
- For prod-impacting updates: `changerequestcreated` then `changerequestapproved` then `changeimplemented`.

---

### Flow B — Validate (Triage, Evidence, Feedback)
Goal: Move from scored outputs to human-reviewed, evidence-linked feedback that supports evaluation gates and continuous monitoring.

B0. Scoring pipeline produces queue items (system-driven)
1) System runs scoring: `scoringrunstarted` → `scoringruncompleted` and `indicatoroutputstats` per indicator.
2) When a queue item/case is created, system emits `casegenerated` with `case_id`, `target_entity_id`, `triggering_indicator_ids`, `evidencebundleid`, `evidencecompletenessflag`, and `reasoncodes`.

B1. Investigator opens triage queue
1) Investigator navigates to `/queue/:queue_name` (QUEUE01).
2) Investigator applies filters and sorts; queue paginates/lazy-loads.
Telemetry:
- `queueviewed` (payload: queuename/queueid, filtersapplied/filterstate, itemsreturned).
- Legacy alternative: `uiviewqueue`.

B2. Investigator opens case
1) Investigator clicks queue row → `/case/:case_id`.
2) Case header loads: case state, involved indicators, top reason codes, confidence band, evidence completeness status.
Telemetry:
- `caseopened` (payload: caseid, queuename, openedfrom).
- Legacy alternative: `uiopencase`.

B3. Investigator views evidence bundle
1) Investigator selects Evidence tab(s): timeline/tables/network (if present).
2) If sensitive drill-in is requested, enforce S-permission; if denied, show redacted view and emit `accessdenied`.
Telemetry:
- `evidenceviewed` (payload includes: evidencebundleid, sensitiveevidenceaccessed, evidencetypesviewed, optional loadtimems).
- Legacy alternative: `uiviewevidencebundle` with viewdurationms.
- `securityaccessevent` (objecttype=evidencebundle, action=view, result=success/denied/error) for audit-grade trails.

B4. Investigator exports evidence (if allowed)
1) Investigator clicks Export (CASE01).
2) Enforce export permissions; log output format and size.
Telemetry:
- Legacy: `uiexportevidence` (exportformat, exportsizebytes).
- Also emit `securityaccessevent` (objecttype=export, action=export, result=success/denied/error).

B5. Investigator submits structured feedback (FB01 inline)
1) Investigator selects outcome (suspicious / not_suspicious / insufficient_evidence), reason tags, explanation usefulness, evidence adequacy, and next action.
2) UI enforces required fields (e.g., reason tags for non-insufficient outcomes; missing evidence list for insufficient evidence).
Telemetry:
- `feedbacksubmitted` (labeloutcome, labelreasontags, labelexplanationusefulness, labelevidenceadequacy, labelnextaction, notespresent).
- Legacy: `uisubmitfeedback` (feedbacklabel, reasontags, explanationusefulness, evidenceadequacy).

B6. Investigator changes case status
1) Investigator updates case status (e.g., new → inreview → closed/referred/escalated/needsMoreInfo).
2) Status transition must follow allowed enums and require reason where applicable.
Telemetry:
- `casestatuschanged` (oldstatus, newstatus, changereason/statusreason).
- Legacy: `uichangecasestatus`.

---

### Flow C — Operate (Health, Drift, Governance, Pause/Resume)
Goal: Monitor indicators in production, detect drift/performance decline, apply controlled changes, and pause/resume/retire when needed.

C1. Monitoring jobs compute metrics and drift
1) Monitoring service emits `monitoringmetricscomputed` (period metrics, and optionally by-indicator metrics).
2) Drift job emits `driftcheckcompleted` (or legacy `monitoringdriftcheckcompleted`) with metric values and pass/warn/fail status.
3) When thresholds are exceeded, system emits `monitoringalertraised`.

C2. PI Ops / Analytics open HLTH01
1) User navigates to `/health`.
2) User reviews PK proxy, actionable explanation rate, evidence missingness, queue aging, drift flags, and recent changes.
Telemetry:
- (Optional) `securityaccessevent` (objecttype=dashboard, action=view, result=success).

C3. Create change request (GOV02) from HLTH01
1) User clicks “Create change request” on an alert or degrading metric.
2) GOV02 requires rationale, risk assessment, validation plan pointer, and rollback plan.
Telemetry:
- `changerequestcreated` / `governancechangerequestcreated`.

C4. Approve/reject change request
1) Approver opens `/governance/changes/:change_id` and decides (approved/rejected/needs revision).
Telemetry:
- `changerequestapproved` OR legacy `governancechangerequestdecision`.

C5. Implement change (deploy config/model/threshold updates)
1) Change is implemented (effective time recorded; artifacts updated; rollback available captured).
Telemetry:
- `changeimplemented`.

C6. Pause / resume / retire (CTRL01)
1) PI Ops or Security/Privacy navigates to `/controls`.
2) Executes control action with reason and effective time; action is written to governance log.
Telemetry:
- Preferred: `indicatorpaused` / `indicatorresumed` (if implemented).
- Or: `safetycontrolaction` with actiontype pauseindicator/resumeindicator/retireindicator/pauseusecase/resumeusecase.

---

## 4) Error, denial, and incident paths

### 4.1 Access denied (RBAC or sensitivity restriction)
When a user attempts to access a forbidden route or sensitive evidence drill-in:
- UI shows a safe “access restricted” message with no sensitive leakage.
- Telemetry MUST include `accessdenied` with resourcetype/resourceid/denialreason, and SHOULD include `securityaccessevent` with result=denied.

### 4.2 Evidence missing / insufficient evidence
When CASE01 detects missing critical evidence elements:
- UI forces low-confidence/INSUFFICIENT_EVIDENCE state and prompts structured missing evidence reporting in FB01.
- Monitoring should treat spikes in insufficient evidence feedback or evidence missingness as an alertable condition.

### 4.3 Production incident workflows (handoff)
SEV2+ incidents must connect to:
- `monitoringalertraised` (detection) → pause if needed (`safetycontrolaction` / `indicatorpaused`) → remediation via GOV02 change request → validation and resume.

---

## 5) Minimum “happy path” instrumentation checklist (v0.1)

If time is tight, these events are the minimum to support ops + monitoring + governance loops end-to-end:
- Data: `dataingestcompleted`, `dataqualitycheckcompleted`.
- Scoring: `scoringruncompleted` (or `indicatorscoringcompleted`), `casegenerated`.
- UI: `queueviewed`, `caseopened`, `evidenceviewed`, `feedbacksubmitted`, `casestatuschanged`, and `uiexportevidence` if export is enabled.
- Monitoring: `monitoringmetricscomputed`, `driftcheckcompleted`, `monitoringalertraised`.
- Governance + safety: `changerequestcreated`, `changerequestapproved`/decision, `changeimplemented`, `safetycontrolaction` (pause/resume/retire).
- Audit: `securityaccessevent` + `accessdenied` for sensitive evidence and exports.
