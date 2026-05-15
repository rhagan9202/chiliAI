# Pause / Discontinue Policy (Core v0.1)
File: /core/monitoring/pause_discontinue_policy.md

Purpose: Define explicit triggers, decision authority, communications, and re-enable/retire criteria for pausing, resuming, and discontinuing (retiring) indicators and/or whole use cases, aligned to Core dashboards and telemetry.
Default posture: triage support (not automated enforcement); pause/discontinue is a normal safety mechanism and part of weekly operations (C08), not an exception.

Related (normative):
- /core/monitoring/dashboardsspec.md (DASH 01–06 required dashboards).
- /core/monitoring/driftchecks.md (drift categories, thresholds, response actions).
- /core/monitoring/telemetrycontract.md (events + fields used for monitoring, governance, audit).
- /core/templates/C08-weekly-ops-review.md and C09-change-request.md (weekly decisions + change control).

---

## 1) Control scope and principles

### 1.1 Control objects
- Indicator: the primary unit of control; may be paused/resumed/retired independently.
- Use case: a configured bundle of indicators + routing + thresholds; may be paused/resumed/retired when the blast radius is broad or governance/security requires it.

### 1.2 Control states
- Active: generates cases/queue items normally.
- Paused: new cases MUST NOT be generated for the paused target; scoring may continue for diagnostics if explicitly configured.
- Retired (discontinued): removed from operational routing; any reintroduction requires a new version and fresh evaluation gates.

### 1.3 No auto-pause (v0.1)
**No indicators or use cases are auto-paused** by monitoring jobs in v0.1.
Monitoring jobs may raise alerts (and recommended actions) and may apply approved *non-pause safeguards* (e.g., route to a HOLD bucket or force low confidence) only if those safeguards are explicitly configured for the use case and reviewed weekly.

### 1.4 Weekly-first operating model
Pause/resume/retire decisions are primarily made in the weekly ops review (C08) using DASH 01–05 (and DASH 06 when security/privacy is in scope).
Emergency carve-out: for SEV0/SEV1 events (security incident, major data freshness breach, systemic evidence/explanation failure), authorized roles may pause immediately, but must formalize via C09 within 24 hours and include in the next weekly review.

---

## 2) Decision rights and required logging

### 2.1 Authority (who can do what)
Pause authority (immediate containment):
- PI Ops Lead: may pause indicators/use cases for operational harm, backlog, performance collapse, or unusable evidence/explanations.
- Security/Privacy Lead: may pause indicators/use cases and restrict evidence access/exports for security or privacy risk.

Resume authority (prod): requires explicit approval evidence and documented validation.
Minimum approvals recommended for prod resume:
- PI Ops Lead (operational risk acceptance).
- Analytics/ML Lead (remediation + validation evidence).
- Investigator Lead consulted (may block if explanations/evidence remain not actionable).
- Security/Privacy approval required if the pause was triggered by access/audit/privacy issues or any change to access controls/logging.

Retire authority (prod): PI Ops + Analytics/ML jointly recommend; Security/Privacy must approve if the retirement is security-driven or if it affects audit posture.

### 2.2 Required telemetry + governance artifacts for control actions
Every pause/resume/retire MUST:
- Emit telemetry for the action (see 2.3).
- Write to governance change log (DASH 05) and be reviewable in weekly ops review (C08).
- Create or link to a C09 Change Request within 24 hours (retroactive allowed for SEV0/SEV1 containment).

### 2.3 Control action telemetry (standard)
Preferred event (recommended for consistency):
- `safetycontrolaction` (actiontype: pauseindicator/resumeindicator/retireindicator/pauseusecase/resumeusecase/retireusecase; includes reason, effective time, authorizedBy).

Accepted v0.1 alternative (already in telemetry contract):
- `indicatorpaused` / `indicatorresumed` with `pausereason`, `authorizedbyuserid`, and notes.

In all cases, the event MUST be linkable to governance artifacts:
- Include `changelogid` (or `correlationid` that ties to `changerequestcreated/changeimplemented`) where possible.

---

## 3) Triggers (alerts → weekly decision)

### 3.1 How triggers are raised
Triggers should appear as:
- A dashboard alert (DASH 01–06), AND/OR
- A telemetry alert event: `monitoringalertraised` with `alerttype`, `severity`, `relatedindicatorids`, and `recommendedaction` (e.g., investigatedata, tunethreshold, pauseindicator, escalatesecurity).

### 3.2 Trigger categories (what can lead to pause/retire)

A) Data freshness or ingestion failure (DASH 03)
- Source: `dataingestcompleted` (success/failure + freshness timestamp), `dataqualitycheckcompleted` (failed checks).
- Typical action: pause impacted indicators (or apply approved HOLD/low-confidence safeguards) until freshness and quality are restored.

B) Data quality / linkage integrity breach (DASH 03)
- Source: `dataqualitycheckcompleted.qualitymetrics` (missing key rate, referential integrity failures).
- Typical action: pause impacted indicators; fix joins/evidence pointers; re-run feature build and scoring under a new scoringrunid.

C) Performance degradation (DASH 02 + DASH 01)
- Source: `monitoringmetricscomputed.metricprecisionproxy` and feedback outcomes (`feedbacksubmitted.labeloutcome` plus reason tags).
- Typical action: tune thresholds/peer groups via C09; if operational harm is material, pause the specific indicators driving low-yield volume.

D) Drift / instability (DASH 03)
- Source: `driftcheckcompleted` drift metrics + flags, including PSI/KS and stability signals.
- Typical action: investigate and document; pause only when drift is severe/unexplained and causes unsafe or unusable triage dynamics.

E) Explainability / evidence failure (DASH 04)
- Source: `monitoringmetricscomputed` trust metrics + `feedbacksubmitted` explanation usefulness/evidence adequacy; `casegenerated.evidencecompletenessflag`; `explanationgenerated` size/flags.
- Typical action: pause indicators that cannot present sufficient evidence or actionable explanations; remediate evidence bundle mappings and explanation caps.

F) Security/privacy anomaly (DASH 06)
- Source: access audit telemetry (e.g., denied access spikes, unusual evidence viewing/export patterns), and anomaly events (e.g., `sensitiveaccessanomalydetected`).
- Typical action: immediate containment (disable access/exports, pause impacted targets) and follow incident response; retirement if controls cannot be remediated.

G) Governance violation (DASH 05)
- Source: change control telemetry (`changerequestcreated/approved/changeimplemented`) and dashboards showing missing approvals/validation references.
- Typical action: roll back to last approved configuration and pause until integrity is restored.

---

## 4) Communications requirements (weekly + emergency)

### 4.1 Weekly communications (standard)
Every pause/resume/retire decision made in weekly review (C08) MUST be communicated to:
- Investigators and queue owners: what changed, why, what to do with in-flight cases, and when the next update will occur.
- Analytics/ML and data owners: remediation tasks, validation expectations, and deadlines.

### 4.2 Emergency communications (SEV0/SEV1)
For emergency pauses (outside weekly cadence):
- Notify PI Ops + Investigator Lead immediately if queues/cases are impacted.
- For security/privacy events, Security/Privacy Lead follows client-specific escalation policy and preserves logs.
- Create incident ticket + C09 change request within 24 hours and include in the next C08 agenda.

---

## 5) Re-enable (resume) and discontinue (retire) criteria

### 5.1 Resume criteria (prod)
An indicator/use case may be resumed only when all are true:
- Root cause is identified and remediation is implemented (data fix, threshold/peer group update, evidence mapping fix, access control fix).
- Validation evidence exists (mini-eval / fresh top‑K spot-check recommended 20–50 items) confirming:
  - precision proxy is back within the use-case threshold (or an explicitly accepted revised threshold),
  - actionable explanation rate and evidence adequacy are back within thresholds,
  - drift is either under threshold or documented as explained/accepted.
- Governance record is complete: C09 updated, approvals captured, effective timestamp/version recorded.

Resume must emit telemetry: `safetycontrolaction` (resume…) or `indicatorresumed`, linked to the change record.

### 5.2 Retire criteria (prod)
Retire when any is true:
- Repeated pauses for the same failure mode without durable remediation.
- Program/policy shift makes indicator no longer meaningful and safe rebaseline is not feasible.
- Security/privacy requirements cannot be met (e.g., required evidence cannot be shown without unacceptable exposure).
- Sustained non-actionability: explanations/evidence remain unusable despite iterations, creating unsafe or wasteful operations.

Retirement must emit telemetry: `safetycontrolaction` (retire…) and remove from routing.

---

# Appendix A — Default thresholds table (v0.1) (weekly review; no auto-pause)

These defaults seed per-use-case configuration and weekly review, and should be tuned per domain pack and investigator capacity constraints.

| Dashboard | Metric / signal | Telemetry source | Default threshold (warn/alert) | Weekly decision default | Recommended `monitoringalertraised.recommendedaction` |
|---|---|---|---|---|---|
| DASH 03 | Data freshness breach | `dataingestcompleted` (freshness timestamp, success) | Alert if critical source late by 24h (or agreed SLA). | Pause impacted indicators OR apply approved HOLD/low-confidence safeguards; fix data pipeline; re-score. | `investigatedata` or `pauseindicator` |
| DASH 03 | Missing key rate spike | `dataqualitycheckcompleted.qualitymetrics.missingkeyrate` | Alert if +50% relative increase vs baseline. | Pause impacted indicators; fix joins/evidence pointers; validate evidence completeness. | `investigatedata` or `pauseindicator` |
| DASH 03 | PSI drift | `driftcheckcompleted.featuredriftvalue/scoredriftvalue` | Warn PSI ≥ 0.2; Alert PSI ≥ 0.3 (heuristic). | Investigate; document; pause only if paired with quality/usability harm. | `investigatedata` / `tunethreshold` / `redefinepeergroup` |
| DASH 02 | Precision@K proxy below acceptance | `monitoringmetricscomputed.metricprecisionproxy` | Alert if below threshold for 2 consecutive weekly periods. | Tune via C09; pause indicators driving volume if harm/backlog. | `tunethreshold` or `pauseindicator` |
| DASH 01 | Queue aging p90 exceeds SLA | `monitoringmetricscomputed.metricqueueagingp90hours` + routing SLA | Alert when p90 exceeds configured SLA. | Throttle/route/pause low-yield indicators; adjust priority bands; document in C08. | `pauseindicator` or `tunethreshold` |
| DASH 01/02 | Insufficient evidence rate spike | `feedbacksubmitted.labeloutcome=insufficientevidence`; `casegenerated.evidencecompletenessflag` | Alert on spike (threshold set per use case). | Pause impacted indicators or force low confidence + HOLD; fix evidence bundle. | `investigatedata` or `pauseindicator` |
| DASH 04 | Actionable explanation rate drop | `monitoringmetricscomputed.metricexplanationactionablerate`; `feedbacksubmitted.labelexplanationusefulness` | Alert when below use-case threshold (weekly). | Fix explanation payload/reason codes; pause if broadly unusable. | `tunethreshold` or `pauseindicator` |
| DASH 03/04 | Explanation subgraph too large | `explanationgenerated.explanationsize.networknodecount` | Warn > 25 nodes (usability warning). | Cap subgraph; re-validate explanation usability; pause graph indicators if widespread failure. | `investigatedata` (for linkage issues) or `tunethreshold` (for caps) |
| DASH 05 | Unapproved change / missing approvals | `changerequest*` + governance dashboard checks | Alert if implemented without required approvals/validation refs. | Roll back; pause affected indicators until integrity restored. | `pauseindicator` |
| DASH 06 | Sensitive access anomaly | Access audit telemetry + anomaly events | Critical alert for confirmed unauthorized access. | Immediate containment (lock accounts, disable exports), pause affected targets; incident response. | `escalatesecurity` or `pauseindicator` |
| DASH 02/03 | StabilityK (STABK) collapse | Stability metrics tracked in eval/monitoring | Alert STABK < 0.3 unless explained by known event. | Investigate drift + changes; pause if operational spikes/unsafe instability. | `redefinepeergroup` / `tunethreshold` / `pauseindicator` |

---

# Appendix B — Standard alert types (for `monitoringalertraised`)

Use these `alerttype` values for consistent routing and weekly review language:
- `datafreshness`, `drift`, `performancedrop`, `explanationdrop`, `evidencemissingspike`, `queuebacklog`, `securityaccessanomaly`.

Each alert should include:
- `severity` (low/medium/high/critical), `relatedindicatorids`, and `recommendedaction` (investigatedata/tunethreshold/redefinepeergroup/pauseindicator/escalatesecurity/other).

---

# Appendix C — Weekly decision outputs (required)

Each weekly ops review (C08) must produce at least one of:
- “No change” decision with documented rationale (especially when drift alerts exist but are explained).
- A C09 change request with owner and validation plan reference.
- A pause/resume/retire action (with telemetry emitted and governance log updated).
