# Pause / Discontinue Policy (Core v0.1)
File: /core/monitoring/pause_discontinue_policy.md [file:1]

Purpose: Define explicit triggers, decision authority, communications, and re-enable/retire criteria for pausing, resuming, and discontinuing (retiring) indicators and/or whole use cases, aligned to Core dashboards and telemetry. [file:1]
Default posture: triage support (not automated enforcement); pause/discontinue is a normal safety mechanism and part of weekly operations (C08), not an exception. [file:1]

Related (normative):
- /core/monitoring/dashboardsspec.md (DASH 01–06 required dashboards). [file:1]
- /core/monitoring/driftchecks.md (drift categories, thresholds, response actions). [file:1]
- /core/monitoring/telemetrycontract.md (events + fields used for monitoring, governance, audit). [file:1]
- /core/templates/C08-weekly-ops-review.md and C09-change-request.md (weekly decisions + change control). [file:1]

---

## 1) Control scope and principles

### 1.1 Control objects
- Indicator: the primary unit of control; may be paused/resumed/retired independently. [file:1]
- Use case: a configured bundle of indicators + routing + thresholds; may be paused/resumed/retired when the blast radius is broad or governance/security requires it. [file:1]

### 1.2 Control states
- Active: generates cases/queue items normally. [file:1]
- Paused: new cases MUST NOT be generated for the paused target; scoring may continue for diagnostics if explicitly configured. [file:1]
- Retired (discontinued): removed from operational routing; any reintroduction requires a new version and fresh evaluation gates. [file:1]

### 1.3 No auto-pause (v0.1)
**No indicators or use cases are auto-paused** by monitoring jobs in v0.1. [file:1]
Monitoring jobs may raise alerts (and recommended actions) and may apply approved *non-pause safeguards* (e.g., route to a HOLD bucket or force low confidence) only if those safeguards are explicitly configured for the use case and reviewed weekly. [file:1]

### 1.4 Weekly-first operating model
Pause/resume/retire decisions are primarily made in the weekly ops review (C08) using DASH 01–05 (and DASH 06 when security/privacy is in scope). [file:1]
Emergency carve-out: for SEV0/SEV1 events (security incident, major data freshness breach, systemic evidence/explanation failure), authorized roles may pause immediately, but must formalize via C09 within 24 hours and include in the next weekly review. [file:1]

---

## 2) Decision rights and required logging

### 2.1 Authority (who can do what)
Pause authority (immediate containment): [file:1]
- PI Ops Lead: may pause indicators/use cases for operational harm, backlog, performance collapse, or unusable evidence/explanations. [file:1]
- Security/Privacy Lead: may pause indicators/use cases and restrict evidence access/exports for security or privacy risk. [file:1]

Resume authority (prod): requires explicit approval evidence and documented validation. [file:1]
Minimum approvals recommended for prod resume:
- PI Ops Lead (operational risk acceptance). [file:1]
- Analytics/ML Lead (remediation + validation evidence). [file:1]
- Investigator Lead consulted (may block if explanations/evidence remain not actionable). [file:1]
- Security/Privacy approval required if the pause was triggered by access/audit/privacy issues or any change to access controls/logging. [file:1]

Retire authority (prod): PI Ops + Analytics/ML jointly recommend; Security/Privacy must approve if the retirement is security-driven or if it affects audit posture. [file:1]

### 2.2 Required telemetry + governance artifacts for control actions
Every pause/resume/retire MUST: [file:1]
- Emit telemetry for the action (see 2.3). [file:1]
- Write to governance change log (DASH 05) and be reviewable in weekly ops review (C08). [file:1]
- Create or link to a C09 Change Request within 24 hours (retroactive allowed for SEV0/SEV1 containment). [file:1]

### 2.3 Control action telemetry (standard)
Preferred event (recommended for consistency):
- `safetycontrolaction` (actiontype: pauseindicator/resumeindicator/retireindicator/pauseusecase/resumeusecase/retireusecase; includes reason, effective time, authorizedBy). [file:1]

Accepted v0.1 alternative (already in telemetry contract):
- `indicatorpaused` / `indicatorresumed` with `pausereason`, `authorizedbyuserid`, and notes. [file:1]

In all cases, the event MUST be linkable to governance artifacts:
- Include `changelogid` (or `correlationid` that ties to `changerequestcreated/changeimplemented`) where possible. [file:1]

---

## 3) Triggers (alerts → weekly decision)

### 3.1 How triggers are raised
Triggers should appear as: [file:1]
- A dashboard alert (DASH 01–06), AND/OR [file:1]
- A telemetry alert event: `monitoringalertraised` with `alerttype`, `severity`, `relatedindicatorids`, and `recommendedaction` (e.g., investigatedata, tunethreshold, pauseindicator, escalatesecurity). [file:1]

### 3.2 Trigger categories (what can lead to pause/retire)

A) Data freshness or ingestion failure (DASH 03) [file:1]
- Source: `dataingestcompleted` (success/failure + freshness timestamp), `dataqualitycheckcompleted` (failed checks). [file:1]
- Typical action: pause impacted indicators (or apply approved HOLD/low-confidence safeguards) until freshness and quality are restored. [file:1]

B) Data quality / linkage integrity breach (DASH 03) [file:1]
- Source: `dataqualitycheckcompleted.qualitymetrics` (missing key rate, referential integrity failures). [file:1]
- Typical action: pause impacted indicators; fix joins/evidence pointers; re-run feature build and scoring under a new scoringrunid. [file:1]

C) Performance degradation (DASH 02 + DASH 01) [file:1]
- Source: `monitoringmetricscomputed.metricprecisionproxy` and feedback outcomes (`feedbacksubmitted.labeloutcome` plus reason tags). [file:1]
- Typical action: tune thresholds/peer groups via C09; if operational harm is material, pause the specific indicators driving low-yield volume. [file:1]

D) Drift / instability (DASH 03) [file:1]
- Source: `driftcheckcompleted` drift metrics + flags, including PSI/KS and stability signals. [file:1]
- Typical action: investigate and document; pause only when drift is severe/unexplained and causes unsafe or unusable triage dynamics. [file:1]

E) Explainability / evidence failure (DASH 04) [file:1]
- Source: `monitoringmetricscomputed` trust metrics + `feedbacksubmitted` explanation usefulness/evidence adequacy; `casegenerated.evidencecompletenessflag`; `explanationgenerated` size/flags. [file:1]
- Typical action: pause indicators that cannot present sufficient evidence or actionable explanations; remediate evidence bundle mappings and explanation caps. [file:1]

F) Security/privacy anomaly (DASH 06) [file:1]
- Source: access audit telemetry (e.g., denied access spikes, unusual evidence viewing/export patterns), and anomaly events (e.g., `sensitiveaccessanomalydetected`). [file:1]
- Typical action: immediate containment (disable access/exports, pause impacted targets) and follow incident response; retirement if controls cannot be remediated. [file:1]

G) Governance violation (DASH 05) [file:1]
- Source: change control telemetry (`changerequestcreated/approved/changeimplemented`) and dashboards showing missing approvals/validation references. [file:1]
- Typical action: roll back to last approved configuration and pause until integrity is restored. [file:1]

---

## 4) Communications requirements (weekly + emergency)

### 4.1 Weekly communications (standard)
Every pause/resume/retire decision made in weekly review (C08) MUST be communicated to: [file:1]
- Investigators and queue owners: what changed, why, what to do with in-flight cases, and when the next update will occur. [file:1]
- Analytics/ML and data owners: remediation tasks, validation expectations, and deadlines. [file:1]

### 4.2 Emergency communications (SEV0/SEV1)
For emergency pauses (outside weekly cadence): [file:1]
- Notify PI Ops + Investigator Lead immediately if queues/cases are impacted. [file:1]
- For security/privacy events, Security/Privacy Lead follows client-specific escalation policy and preserves logs. [file:1]
- Create incident ticket + C09 change request within 24 hours and include in the next C08 agenda. [file:1]

---

## 5) Re-enable (resume) and discontinue (retire) criteria

### 5.1 Resume criteria (prod)
An indicator/use case may be resumed only when all are true: [file:1]
- Root cause is identified and remediation is implemented (data fix, threshold/peer group update, evidence mapping fix, access control fix). [file:1]
- Validation evidence exists (mini-eval / fresh top‑K spot-check recommended 20–50 items) confirming: [file:1]
  - precision proxy is back within the use-case threshold (or an explicitly accepted revised threshold), [file:1]
  - actionable explanation rate and evidence adequacy are back within thresholds, [file:1]
  - drift is either under threshold or documented as explained/accepted. [file:1]
- Governance record is complete: C09 updated, approvals captured, effective timestamp/version recorded. [file:1]

Resume must emit telemetry: `safetycontrolaction` (resume…) or `indicatorresumed`, linked to the change record. [file:1]

### 5.2 Retire criteria (prod)
Retire when any is true: [file:1]
- Repeated pauses for the same failure mode without durable remediation. [file:1]
- Program/policy shift makes indicator no longer meaningful and safe rebaseline is not feasible. [file:1]
- Security/privacy requirements cannot be met (e.g., required evidence cannot be shown without unacceptable exposure). [file:1]
- Sustained non-actionability: explanations/evidence remain unusable despite iterations, creating unsafe or wasteful operations. [file:1]

Retirement must emit telemetry: `safetycontrolaction` (retire…) and remove from routing. [file:1]

---

# Appendix A — Default thresholds table (v0.1) (weekly review; no auto-pause)

These defaults seed per-use-case configuration and weekly review, and should be tuned per domain pack and investigator capacity constraints. [file:1]

| Dashboard | Metric / signal | Telemetry source | Default threshold (warn/alert) | Weekly decision default | Recommended `monitoringalertraised.recommendedaction` |
|---|---|---|---|---|---|
| DASH 03 | Data freshness breach | `dataingestcompleted` (freshness timestamp, success) | Alert if critical source late by 24h (or agreed SLA). [file:1] | Pause impacted indicators OR apply approved HOLD/low-confidence safeguards; fix data pipeline; re-score. [file:1] | `investigatedata` or `pauseindicator` [file:1] |
| DASH 03 | Missing key rate spike | `dataqualitycheckcompleted.qualitymetrics.missingkeyrate` | Alert if +50% relative increase vs baseline. [file:1] | Pause impacted indicators; fix joins/evidence pointers; validate evidence completeness. [file:1] | `investigatedata` or `pauseindicator` [file:1] |
| DASH 03 | PSI drift | `driftcheckcompleted.featuredriftvalue/scoredriftvalue` | Warn PSI ≥ 0.2; Alert PSI ≥ 0.3 (heuristic). [file:1] | Investigate; document; pause only if paired with quality/usability harm. [file:1] | `investigatedata` / `tunethreshold` / `redefinepeergroup` [file:1] |
| DASH 02 | Precision@K proxy below acceptance | `monitoringmetricscomputed.metricprecisionproxy` | Alert if below threshold for 2 consecutive weekly periods. [file:1] | Tune via C09; pause indicators driving volume if harm/backlog. [file:1] | `tunethreshold` or `pauseindicator` [file:1] |
| DASH 01 | Queue aging p90 exceeds SLA | `monitoringmetricscomputed.metricqueueagingp90hours` + routing SLA | Alert when p90 exceeds configured SLA. [file:1] | Throttle/route/pause low-yield indicators; adjust priority bands; document in C08. [file:1] | `pauseindicator` or `tunethreshold` [file:1] |
| DASH 01/02 | Insufficient evidence rate spike | `feedbacksubmitted.labeloutcome=insufficientevidence`; `casegenerated.evidencecompletenessflag` | Alert on spike (threshold set per use case). [file:1] | Pause impacted indicators or force low confidence + HOLD; fix evidence bundle. [file:1] | `investigatedata` or `pauseindicator` [file:1] |
| DASH 04 | Actionable explanation rate drop | `monitoringmetricscomputed.metricexplanationactionablerate`; `feedbacksubmitted.labelexplanationusefulness` | Alert when below use-case threshold (weekly). [file:1] | Fix explanation payload/reason codes; pause if broadly unusable. [file:1] | `tunethreshold` or `pauseindicator` [file:1] |
| DASH 03/04 | Explanation subgraph too large | `explanationgenerated.explanationsize.networknodecount` | Warn > 25 nodes (usability warning). [file:1] | Cap subgraph; re-validate explanation usability; pause graph indicators if widespread failure. [file:1] | `investigatedata` (for linkage issues) or `tunethreshold` (for caps) [file:1] |
| DASH 05 | Unapproved change / missing approvals | `changerequest*` + governance dashboard checks | Alert if implemented without required approvals/validation refs. [file:1] | Roll back; pause affected indicators until integrity restored. [file:1] | `pauseindicator` [file:1] |
| DASH 06 | Sensitive access anomaly | Access audit telemetry + anomaly events | Critical alert for confirmed unauthorized access. [file:1] | Immediate containment (lock accounts, disable exports), pause affected targets; incident response. [file:1] | `escalatesecurity` or `pauseindicator` [file:1] |
| DASH 02/03 | StabilityK (STABK) collapse | Stability metrics tracked in eval/monitoring | Alert STABK < 0.3 unless explained by known event. [file:1] | Investigate drift + changes; pause if operational spikes/unsafe instability. [file:1] | `redefinepeergroup` / `tunethreshold` / `pauseindicator` [file:1] |

---

# Appendix B — Standard alert types (for `monitoringalertraised`)

Use these `alerttype` values for consistent routing and weekly review language: [file:1]
- `datafreshness`, `drift`, `performancedrop`, `explanationdrop`, `evidencemissingspike`, `queuebacklog`, `securityaccessanomaly`. [file:1]

Each alert should include: [file:1]
- `severity` (low/medium/high/critical), `relatedindicatorids`, and `recommendedaction` (investigatedata/tunethreshold/redefinepeergroup/pauseindicator/escalatesecurity/other). [file:1]

---

# Appendix C — Weekly decision outputs (required)

Each weekly ops review (C08) must produce at least one of: [file:1]
- “No change” decision with documented rationale (especially when drift alerts exist but are explained). [file:1]
- A C09 change request with owner and validation plan reference. [file:1]
- A pause/resume/retire action (with telemetry emitted and governance log updated). [file:1]
