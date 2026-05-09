# Incident Runbook (v0.1)

## Purpose
Provides a standard process to detect, triage, and resolve production incidents involving:
- Data pipelines
- Indicator scoring and triage queues
- Explainability and evidence bundles
- Governance and safety controls

This covers both technical failures and monitoring/drift issues.

---

## 1. Incident types

### 1.1 Data pipeline incidents
- Symptoms:
  - Stale data (freshness lag beyond threshold).
  - Missing or incomplete data (volume/missingness anomalies).
  - Schema changes breaking pipelines.
- Impact:
  - Inaccurate or delayed scoring and evidence bundles.

### 1.2 Scoring and service incidents
- Symptoms:
  - Scoring service errors or timeouts.
  - Scoring runs not completing or taking too long.
  - Spikes/drop-offs in queued items without explanation.

### 1.3 Drift and performance incidents
- Symptoms:
  - Monitoring alerts for severe data/output/performance drift.
  - Sudden drop in Precision@K or Yield@K.
  - Abnormal Stability@K without planned changes.

### 1.4 Explainability/evidence incidents
- Symptoms:
  - Evidence bundles missing critical components at high rates.
  - Explanations consistently rated low usefulness.
  - Inconsistent or incorrect traceability to source records.

### 1.5 Security and access incidents
- Symptoms:
  - Unusual access patterns to evidence or exports.
  - Unauthorized changes to indicators or controls.
  - Audit trail gaps.

---

## 2. Severity levels

- SEV1 (Critical):
  - Safety or compliance risk; triage system must be paused or heavily restricted.
  - Example: Evidence missing for majority of high-risk flags; severe drift with clear harm risk.
- SEV2 (High):
  - Significant degradation in quality or availability impacting normal operations.
  - Example: Scoring runs failing for a day; high false positive rate spike.
- SEV3 (Moderate):
  - Degradation with workarounds or limited scope.
- SEV4 (Low):
  - Minor issues; informational or backlog-only impacts.

---

## 3. Roles

- Incident commander (IC): coordinates response (usually PI Ops or ML Ops lead).
- Data engineer: owns data pipeline investigation.
- Analytics/ML owner: owns indicator and performance analysis.
- Application owner: owns UI and integration behavior.
- Security/Privacy: consulted for security-related incidents.
- Communications owner: handles stakeholder updates.

---

## 4. Generic incident lifecycle

1) Detect:
   - Alert fires from monitoring.
   - User reports an issue.
2) Triage (first 15–30 minutes):
   - Confirm incident and severity.
   - Assign IC and on-call roles.
3) Stabilize:
   - Contain blast radius (pause indicators, route to safe defaults).
   - Apply temporary mitigations.
4) Diagnose:
   - Use telemetry and logs to localize root cause.
5) Remediate:
   - Implement fix (data hotfix, configuration change, rollback).
6) Verify:
   - Check dashboards and key metrics.
7) Close:
   - Communicate resolution.
   - Create post-incident review.

---

## 5. Runbooks by incident type

### 5.1 Data pipeline incident runbook

Steps:
1) Confirm:
   - Check data pipeline dashboard.
   - Identify failing source or step (freshness, volume, schema).
2) Contain:
   - If data is stale or incomplete:
     - Option A: Pause new scoring runs for affected use cases.
     - Option B: Continue but mark scores as low-confidence and exclude from queue, depending on risk.
3) Diagnose:
   - Inspect pipeline logs.
   - Identify whether issue is upstream source, ETL, or infrastructure.
4) Remediate:
   - Fix ETL or revert to last known-good config.
   - Re-run backfill for affected period if feasible.
5) Verify:
   - Ensure freshness, volume, and missingness are back within thresholds.
   - Resume normal scoring.
6) Document:
   - Log incident in governance system.
   - Capture root cause and follow-ups.

### 5.2 Scoring/service incident runbook

Steps:
1) Confirm:
   - Check scoring_run metrics and error logs.
2) Contain:
   - If scoring is unreliable, pause affected indicators/use cases.
   - Communicate status to investigators (e.g., “queue not updated since <time>”).
3) Diagnose:
   - Identify whether issue is model/service, infrastructure, or integration.
4) Remediate:
   - Fix configuration or dependencies.
   - Roll back to previous version if new release caused issue.
5) Verify:
   - Run test scoring job in lower environment if possible.
   - Resume production run and monitor first batch.
6) Document:
   - Incident summary and corrective actions.

### 5.3 Drift/performance incident runbook

Steps:
1) Confirm:
   - Validate drift/metric alerts on the Indicator health dashboard.
   - Check whether any recent config or policy changes could explain changes.
2) Contain:
   - For severe drift or Precision@K collapse:
     - Consider lowering thresholds (more conservative) or pausing indicator.
     - Notify investigators of potential quality issues.
3) Diagnose:
   - Compare feature distributions and score distributions to baseline.
   - Review investigator feedback for pattern shifts.
4) Remediate:
   - Retrain/recalibrate model (if ML).
   - Update logic or thresholds.
   - Adjust peer group definitions if relevant.
5) Verify:
   - Re-run evaluation on recent data with updated configuration.
   - Confirm metrics are back within acceptable ranges.
6) Document:
   - Update C02, C06, change log, and monitoring thresholds.

### 5.4 Explainability/evidence incident runbook

Steps:
1) Confirm:
   - Check Explainability & evidence dashboard.
   - Review reports of missing/incorrect evidence.
2) Contain:
   - If critical evidence is missing or misleading:
     - Set indicator to produce `INSUFFICIENT_EVIDENCE` and/or low-confidence flags.
     - Consider pausing the indicator for triage.
3) Diagnose:
   - Determine whether issue is in feature pipeline, evidence bundler, or UI layer.
   - Check traceability pointers to source records.
4) Remediate:
   - Fix bundling logic or data joins.
   - Rebuild evidence bundles if feasible.
5) Verify:
   - Sample cases with investigators to confirm evidence and explanations are correct.
6) Document:
   - Record incident and any changes to evidence requirements.

### 5.5 Security/access incident runbook

Steps:
1) Confirm:
   - Use Security & audit dashboard to validate unusual access.
2) Contain:
   - Revoke or adjust access for suspicious accounts.
   - Temporarily disable exports if necessary.
3) Diagnose:
   - Identify root cause (credential misuse, misconfigured roles, etc.).
4) Remediate:
   - Fix IAM/role configuration.
   - Rotate credentials.
5) Verify:
   - Re-check audit logs for residual anomalies.
6) Document:
   - Security incident record; may require external reporting.

---

## 6. Communications

- Internal status updates:
  - Initial: acknowledgement, scope, and severity.
  - Ongoing: on major milestones (containment, remediation progress).
  - Final: resolution summary and next steps.
- External/regulator communications:
  - Follow program policies for high-impact incidents.

---

## 7. Post-incident review

Within 5–10 business days for SEV1/SEV2:
- Participants:
  - IC, data engineering, Analytics/ML, PI Ops, Security/Privacy (if relevant).
- Agenda:
  - Timeline of events.
  - Root cause analysis (5 Whys).
  - What worked well and what did not.
  - Concrete actions:
    - Monitoring improvements.
    - Process changes.
    - Documentation updates.

Outcomes:
- Update monitoring thresholds and dashboards.
- Update templates:
  - C02 (indicator monitoring section).
  - C06 (eval plan).
  - C09 (change request patterns if needed).
