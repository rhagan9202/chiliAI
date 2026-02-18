# Core UI Navigation Flow (v0.1)

Purpose: Define the navigational routes and end-to-end user flows across Core UI screens, and map each key UI action to the telemetry/audit events required by `core/monitoring/telemetrycontract.md`. [file:1]
This document is aligned to the v0.1 intent: triage support (not automated enforcement), human-in-the-loop validation, and operational governance (monitoring + change control + pause/discontinue). [file:1]

Related specs (normative):
- `core/ui/screens_spec.md` (screen catalog, required actions, validations). [file:1]
- `core/ui/fields_dictionary.md` (canonical field names for case, evidence bundle, feedback, governance). [file:1]
- `core/monitoring/telemetrycontract.md` (event envelope and required events). [file:1]
- `core/monitoring/dashboardsspec.md`, `core/monitoring/driftchecks.md` (how telemetry rolls up into ops + drift + trust dashboards). [file:1]
- `core/docs/governance-change-control.md` (approval gates, C09 change request discipline). [file:1]

---

## 1) Route map (UI IA)

Routes are role-filtered in left navigation; deep links may exist (e.g., `/case/:case_id`) but must enforce RBAC on load. [file:1]

Core routes:
- `/use-cases` → UC01 Use-case Canvas (list/select; optional list in v0.1). [file:1]
- `/use-cases/:use_case_id` → UC01 Use-case Canvas (detail). [file:1]
- `/indicators` → IND01 Indicator Builder (list). [file:1]
- `/indicators/:indicator_id` → IND02 Indicator Builder (detail). [file:1]
- `/risk` → RISK01 Risk Dashboard. [file:1]
- `/queue/:queue_name` → QUEUE01 Triage Queue. [file:1]
- `/case/:case_id` → CASE01 Case View + Evidence Bundle Viewer (includes FB01 inline). [file:1]
- `/health` → HLTH01 Indicator Health Dashboard. [file:1]
- `/governance/changes` → GOV01 Governance Change Log (read). [file:1]
- `/governance/changes/new` → GOV02 Change Request (create). [file:1]
- `/governance/changes/:change_id` → GOV02 Change Request (detail/decide). [file:1]
- `/controls` → CTRL01 Pause/Resume/Retire Controls. [file:1]
- `/audit` → AUD01 Security Audit View. [file:1]
- `/admin` → ADMIN01 Admin (optional v0.1). [file:1]

Global search (header):
- Search by `entity_id`, `case_id`, `external_case_ref`. [file:1]
- Results link to `/case/:case_id` when a case exists; otherwise to RISK01 entity drill-in. [file:1]

---

## 2) Canonical telemetry naming (and legacy mapping)

The telemetry contract appears in two compatible “shapes” in v0.1 materials:
- Canonical (recommended): `queueviewed`, `caseopened`, `evidenceviewed`, `feedbacksubmitted`, `casestatuschanged`, etc. [file:1]
- Legacy UI event names that appeared earlier: `uiviewqueue`, `uiopencase`, `uiviewevidencebundle`, `uiexportevidence`, `uisubmitfeedback`, `uichangecasestatus`. [file:1]

### 2.1 Compatibility mapping
Implementations MAY emit canonical event names only, or MAY emit both during transition; downstream dashboards must map legacy → canonical. [file:1]

| Canonical eventname (recommended) | Legacy eventtype (if present) |
|---|---|
| `queueviewed` | `uiviewqueue` [file:1] |
| `caseopened` | `uiopencase` [file:1] |
| `evidenceviewed` | `uiviewevidencebundle` [file:1] |
| `evidenceexported` (optional alias; see note) | `uiexportevidence` [file:1] |
| `feedbacksubmitted` | `uisubmitfeedback` [file:1] |
| `casestatuschanged` | `uichangecasestatus` [file:1] |
| `indicatorpaused` | `safetycontrolaction` (actiontype=pauseindicator) [file:1] |
| `indicatorresumed` | `safetycontrolaction` (actiontype=resumeindicator) [file:1] |

Note: If you already log `uiexportevidence` as defined, you can treat it as the export event for dashboards/audit; a separate canonical `evidenceexported` is not required in v0.1. [file:1]

---

## 3) End-to-end navigation flows (with telemetry)

### Flow A — Frame (Use-case + Indicator definition)
Goal: Create/maintain the framed use case and indicator definitions with explicit guardrails, evidence requirements, and governance-ready approvals. [file:1]

A1. Enter UC01 Use-case Canvas
1) User navigates to `/use-cases/:use_case_id` (UC01). [file:1]
2) System enforces RBAC; if denied → emit `accessdenied`. [file:1]
3) User views the use case definition (triage-only intent, non-goals, evidence requirements, success metrics, approvals). [file:1]
Telemetry:
- (Optional) emit a generic `securityaccessevent` (objecttype=usecase, action=view, result=success) if audit wants full coverage. [file:1]

A2. Edit use case (role-gated)
1) PI Ops Lead (or Admin) edits fields and saves changes. [file:1]
2) For production-impacting changes (scope, data sources, guardrails, success metric targets), user SHOULD be routed to GOV02 to raise a change request before applying the change in prod. [file:1]
Telemetry:
- `governancechangerequestcreated` / `changerequestcreated` (changetype includes datachange/uichange/securitychange as applicable; rationalesummary references UC01 scope change). [file:1]

A3. Navigate to IND01/IND02
1) From UC01, user clicks “View indicators in scope” → `/indicators?use_case_id=...`. [file:1]
2) Analytics creates/edits indicator in IND02, including reason codes, evidence requirements, and “what this does NOT mean”. [file:1]
Telemetry:
- For draft-only saves: log locally (optional) but do not require governance events. [file:1]
- For prod-impacting updates: `changerequestcreated` then `changerequestapproved` then `changeimplemented`. [file:1]

---

### Flow B — Validate (Triage, Evidence, Feedback)
Goal: Move from scored outputs to human-reviewed, evidence-linked feedback that supports evaluation gates and continuous monitoring. [file:1]

B0. Scoring pipeline produces queue items (system-driven)
1) System runs scoring: `scoringrunstarted` → `scoringruncompleted` and `indicatoroutputstats` per indicator. [file:1]
2) When a queue item/case is created, system emits `casegenerated` with `case_id`, `target_entity_id`, `triggering_indicator_ids`, `evidencebundleid`, `evidencecompletenessflag`, and `reasoncodes`. [file:1]

B1. Investigator opens triage queue
1) Investigator navigates to `/queue/:queue_name` (QUEUE01). [file:1]
2) Investigator applies filters and sorts; queue paginates/lazy-loads. [file:1]
Telemetry:
- `queueviewed` (payload: queuename/queueid, filtersapplied/filterstate, itemsreturned). [file:1]
- Legacy alternative: `uiviewqueue`. [file:1]

B2. Investigator opens case
1) Investigator clicks queue row → `/case/:case_id`. [file:1]
2) Case header loads: case state, involved indicators, top reason codes, confidence band, evidence completeness status. [file:1]
Telemetry:
- `caseopened` (payload: caseid, queuename, openedfrom). [file:1]
- Legacy alternative: `uiopencase`. [file:1]

B3. Investigator views evidence bundle
1) Investigator selects Evidence tab(s): timeline/tables/network (if present). [file:1]
2) If sensitive drill-in is requested, enforce S-permission; if denied, show redacted view and emit `accessdenied`. [file:1]
Telemetry:
- `evidenceviewed` (payload includes: evidencebundleid, sensitiveevidenceaccessed, evidencetypesviewed, optional loadtimems). [file:1]
- Legacy alternative: `uiviewevidencebundle` with viewdurationms. [file:1]
- `securityaccessevent` (objecttype=evidencebundle, action=view, result=success/denied/error) for audit-grade trails. [file:1]

B4. Investigator exports evidence (if allowed)
1) Investigator clicks Export (CASE01). [file:1]
2) Enforce export permissions; log output format and size. [file:1]
Telemetry:
- Legacy: `uiexportevidence` (exportformat, exportsizebytes). [file:1]
- Also emit `securityaccessevent` (objecttype=export, action=export, result=success/denied/error). [file:1]

B5. Investigator submits structured feedback (FB01 inline)
1) Investigator selects outcome (suspicious / not_suspicious / insufficient_evidence), reason tags, explanation usefulness, evidence adequacy, and next action. [file:1]
2) UI enforces required fields (e.g., reason tags for non-insufficient outcomes; missing evidence list for insufficient evidence). [file:1]
Telemetry:
- `feedbacksubmitted` (labeloutcome, labelreasontags, labelexplanationusefulness, labelevidenceadequacy, labelnextaction, notespresent). [file:1]
- Legacy: `uisubmitfeedback` (feedbacklabel, reasontags, explanationusefulness, evidenceadequacy). [file:1]

B6. Investigator changes case status
1) Investigator updates case status (e.g., new → inreview → closed/referred/escalated/needsMoreInfo). [file:1]
2) Status transition must follow allowed enums and require reason where applicable. [file:1]
Telemetry:
- `casestatuschanged` (oldstatus, newstatus, changereason/statusreason). [file:1]
- Legacy: `uichangecasestatus`. [file:1]

---

### Flow C — Operate (Health, Drift, Governance, Pause/Resume)
Goal: Monitor indicators in production, detect drift/performance decline, apply controlled changes, and pause/resume/retire when needed. [file:1]

C1. Monitoring jobs compute metrics and drift
1) Monitoring service emits `monitoringmetricscomputed` (period metrics, and optionally by-indicator metrics). [file:1]
2) Drift job emits `driftcheckcompleted` (or legacy `monitoringdriftcheckcompleted`) with metric values and pass/warn/fail status. [file:1]
3) When thresholds are exceeded, system emits `monitoringalertraised`. [file:1]

C2. PI Ops / Analytics open HLTH01
1) User navigates to `/health`. [file:1]
2) User reviews PK proxy, actionable explanation rate, evidence missingness, queue aging, drift flags, and recent changes. [file:1]
Telemetry:
- (Optional) `securityaccessevent` (objecttype=dashboard, action=view, result=success). [file:1]

C3. Create change request (GOV02) from HLTH01
1) User clicks “Create change request” on an alert or degrading metric. [file:1]
2) GOV02 requires rationale, risk assessment, validation plan pointer, and rollback plan. [file:1]
Telemetry:
- `changerequestcreated` / `governancechangerequestcreated`. [file:1]

C4. Approve/reject change request
1) Approver opens `/governance/changes/:change_id` and decides (approved/rejected/needs revision). [file:1]
Telemetry:
- `changerequestapproved` OR legacy `governancechangerequestdecision`. [file:1]

C5. Implement change (deploy config/model/threshold updates)
1) Change is implemented (effective time recorded; artifacts updated; rollback available captured). [file:1]
Telemetry:
- `changeimplemented`. [file:1]

C6. Pause / resume / retire (CTRL01)
1) PI Ops or Security/Privacy navigates to `/controls`. [file:1]
2) Executes control action with reason and effective time; action is written to governance log. [file:1]
Telemetry:
- Preferred: `indicatorpaused` / `indicatorresumed` (if implemented). [file:1]
- Or: `safetycontrolaction` with actiontype pauseindicator/resumeindicator/retireindicator/pauseusecase/resumeusecase. [file:1]

---

## 4) Error, denial, and incident paths

### 4.1 Access denied (RBAC or sensitivity restriction)
When a user attempts to access a forbidden route or sensitive evidence drill-in: [file:1]
- UI shows a safe “access restricted” message with no sensitive leakage. [file:1]
- Telemetry MUST include `accessdenied` with resourcetype/resourceid/denialreason, and SHOULD include `securityaccessevent` with result=denied. [file:1]

### 4.2 Evidence missing / insufficient evidence
When CASE01 detects missing critical evidence elements: [file:1]
- UI forces low-confidence/INSUFFICIENT_EVIDENCE state and prompts structured missing evidence reporting in FB01. [file:1]
- Monitoring should treat spikes in insufficient evidence feedback or evidence missingness as an alertable condition. [file:1]

### 4.3 Production incident workflows (handoff)
SEV2+ incidents must connect to: [file:1]
- `monitoringalertraised` (detection) → pause if needed (`safetycontrolaction` / `indicatorpaused`) → remediation via GOV02 change request → validation and resume. [file:1]

---

## 5) Minimum “happy path” instrumentation checklist (v0.1)

If time is tight, these events are the minimum to support ops + monitoring + governance loops end-to-end: [file:1]
- Data: `dataingestcompleted`, `dataqualitycheckcompleted`. [file:1]
- Scoring: `scoringruncompleted` (or `indicatorscoringcompleted`), `casegenerated`. [file:1]
- UI: `queueviewed`, `caseopened`, `evidenceviewed`, `feedbacksubmitted`, `casestatuschanged`, and `uiexportevidence` if export is enabled. [file:1]
- Monitoring: `monitoringmetricscomputed`, `driftcheckcompleted`, `monitoringalertraised`. [file:1]
- Governance + safety: `changerequestcreated`, `changerequestapproved`/decision, `changeimplemented`, `safetycontrolaction` (pause/resume/retire). [file:1]
- Audit: `securityaccessevent` + `accessdenied` for sensitive evidence and exports. [file:1]
