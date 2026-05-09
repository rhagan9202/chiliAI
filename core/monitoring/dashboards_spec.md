# Core Monitoring Dashboards Specification (v0.1)

## Purpose
Defines the minimum dashboards required to safely operate the Program Integrity XAI Accelerator in production, focusing on:
- Data pipeline health
- Scoring and triage operations
- Indicator quality and drift
- Explainability and evidence quality
- Governance and auditability

---

## 1. Data pipeline health dashboard

### 1.1 Audience
- Data engineering
- Analytics/ML
- PI Ops (read-only)

### 1.2 Goals
- Detect freshness, volume, schema, and quality issues before they affect scoring and triage.
- Quickly localize which source or step is failing.

### 1.3 Key metrics (per source and pipeline step)
- Freshness:
  - `max(event_timestamp)` vs current time.
  - `data_freshness_hours` by table/source.
- Volume:
  - Row counts per batch vs historical median.
  - Volume anomaly flags (high/low).
- Schema:
  - Schema drift detected (yes/no).
  - Count of fields with changed type or missing.
- Quality:
  - Missingness rate per key field.
  - Basic validity checks (e.g., non-negative amounts).

### 1.4 Visuals
- Time series of freshness lag per source.
- Time series of row counts vs baseline band.
- Table of current alerts by pipeline step (color-coded).

---

## 2. Triage & queue operations dashboard

### 2.1 Audience
- PI Ops
- Investigator Leads
- Analytics/ML

### 2.2 Goals
- Understand workload, throughput, and backlog.
- Ensure queue configuration aligns with capacity and priorities.

### 2.3 Key metrics
By time bucket (e.g., daily):
- Workload:
  - New items queued.
  - Items worked (cases opened).
  - Open vs closed cases.
- Throughput:
  - Median and distribution of time from queue entry to first view.
  - Median and distribution of time from first view to case closure.
- Assignment:
  - Items per investigator.
  - Unassigned items.

### 2.4 Visuals
- Time series: new vs closed items.
- Histogram: time-to-first-view, time-to-close.
- Table: backlog by severity and indicator.

---

## 3. Indicator quality & drift dashboard

### 3.1 Audience
- Analytics/ML
- PI Ops
- Investigator Leads

### 3.2 Goals
- Track indicator performance and stability over time.
- Detect drift or degradations that may require tuning or pause.

### 3.3 Key metrics (per indicator, per period)
- Volume:
  - `items_scored`.
  - `items_queued`.
- Effectiveness:
  - `precision_at_k` (or best proxy if labels lag).
  - `yield_at_k` (e.g., proportion of cases leading to actions).
- Explanation & evidence:
  - `explanation_usefulness_avg`.
  - `evidence_adequacy_avg`.
  - `missing_critical_evidence_rate`.
- Stability & drift:
  - `stability_at_k` (e.g., overlap of top-K entities between runs).
  - Output distribution drift (score distributions, severity distribution).
  - Input data drift (selected features, peer baselines).

### 3.4 Visuals
- Time series per indicator for:
  - Precision@K, yield@K.
  - Explanation usefulness and evidence adequacy.
  - Missing critical evidence rate.
- Bar/stacked bar:
  - Severity distribution per indicator.
- Drift panel:
  - Flags and severity per indicator with links to detail.

---

## 4. Explainability & evidence quality dashboard

### 4.1 Audience
- Investigator Leads
- Analytics/ML
- PI Ops

### 4.2 Goals
- Ensure explanations and evidence bundles remain actionable.
- Detect patterns where users frequently report confusion or missing evidence.

### 4.3 Key metrics
- Explanation quality:
  - Distribution of `explanation_usefulness` (1–5) per indicator.
  - Percentage of feedback with usefulness ≥ 4.
- Evidence quality:
  - Distribution of `evidence_adequacy` (1–5).
  - Rate of `missing_evidence_reported`.
  - `missing_critical_evidence_rate` flagged by system.
- Reason code issues:
  - Most frequently marked “confusing_reason_codes`.
  - Free-text “what was confusing” themes (optional text analytics).

### 4.4 Visuals
- Boxplots or histograms for usefulness and adequacy scores.
- Top confusing reason codes list.
- Time series of missing evidence rates with alerts.

---

## 5. Governance & safety dashboard

### 5.1 Audience
- PI Ops
- Security/Privacy
- Senior stakeholders

### 5.2 Goals
- Provide a single place to see governance posture: changes, incidents, and pause/retire actions.

### 5.3 Key metrics
- Change control:
  - Number of change requests by status (open/approved/rejected).
  - Time from request to decision.
- Safety:
  - Count of pause/resume actions by indicator/use-case.
  - Open incidents by severity.
- Compliance:
  - Audit coverage (percentage of high-risk indicators with recent review).
  - Older-than-threshold indicators (e.g., not re-evaluated in N months).

### 5.4 Visuals
- Timeline of change events.
- Table of current paused/retired indicators and reasons.
- Incident summary cards and drill-down.

---

## 6. Security & audit dashboard

### 6.1 Audience
- Security/Privacy
- Compliance

### 6.2 Goals
- Track access to sensitive artifacts (evidence, exports, governance actions).
- Support investigations and compliance checks.

### 6.3 Key metrics
- Evidence access:
  - Count of evidence_bundle views by user/role.
  - Exports/attachments by user/role.
- Governance actions:
  - Approvals/denials for high-risk changes.
  - Pause/resume/retire actions with actor details.
- Anomalies:
  - Unusual access patterns (e.g., out-of-hours, unusual volume).

### 6.4 Visuals
- Heatmap of access events by hour and role.
- Table of top viewers/exporters.
- List of flagged anomalous sessions.

---

## 7. Implementation notes

- All dashboards should link back to:
  - Underlying cases, indicators, and change requests.
  - Underlying incidents when relevant.
- Thresholds for alerts must be configurable per environment and use case.
- Dashboards should be environment-aware (dev/test/prod) to avoid confusing signals.
