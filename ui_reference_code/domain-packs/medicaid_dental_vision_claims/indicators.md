# Indicator Library — Medicaid Dental/Vision Claims Integrity (v0.1)
DomainPackId: medicaiddentalvisionclaims
Version: 0.1.0
Target workflow: provider/clinic risk triage, ring detection, and case prioritization.

Indicator IDs: MDV-01..MDV-10

---

## MDV-01 Clinic/provider ring via shared attributes (graph)
Target entity: clinicgroup or provider cluster
Type: graphpattern
What it flags: Provider cluster with shared address/phone/bank/contact (as permitted) and suspicious density.
Reason codes:
- SHARED_ATTRIBUTE_RING
- HIGH_CLUSTER_DENSITY
- MULTI_PROVIDER_LINKAGE
Required evidence:
- Capped subgraph + edge-type counts
- Provider list with shared attributes summary
Next steps:
- Validate legitimacy (multi-site org) vs suspect linkage; escalate to SIU referral package if warranted
Routing: clinic_triage_queue, P1

---

## MDV-02 Procedure bundle community outlier
Target entity: provider or clinicgroup
Type: peeroutlier + graphpattern (optional)
What it flags: Unusual code bundle communities deviating from peers.
Reason codes:
- BUNDLE_COMMUNITY_OUTLIER
- RARE_BUNDLE_SPIKE
- PEER_DEVIATION
Required evidence:
- Bundle frequency table vs peers
- Claim/line samples
Next steps:
- SME review: clinical plausibility; update peer groups if needed
Routing: provider_risk_queue, P2

---

## MDV-03 Temporal over-utilization spike vs peers
Target entity: provider
Type: timeseries + peeroutlier
What it flags: Abrupt increases in volume/paid amounts vs baseline and peer baseline.
Reason codes:
- UTILIZATION_SPIKE
- CHANGE_POINT_DETECTED
- PEER_OUTLIER_RATE
Required evidence:
- Trend summary + baseline/comparison window
- Top contributing procedures
Next steps:
- Check data freshness; investigate confounders; sample claims
Routing: provider_risk_queue, P1

---

## MDV-04 High repeat services for beneficiary cohorts
Target entity: provider
Type: timeseries
What it flags: High frequency repeat services for same beneficiaries beyond expected intervals.
Reason codes:
- HIGH_REPEAT_SERVICES
- SHORT_INTERVAL_REPEATS
- BENEFICIARY_TRAJECTORY_ANOMALY
Required evidence:
- De-identified beneficiary trajectory summaries
- Repeat interval distribution
Next steps:
- Review documentation; consider targeted sampling
Routing: provider_risk_queue, P2

---

## MDV-05 Provider-beneficiary churn / panel instability
Target entity: provider
Type: timeseries + network-ready
What it flags: Unusual new-beneficiary influx or churn patterns inconsistent with peers.
Reason codes:
- NEW_BENEFICIARY_INFLUX
- HIGH_CHURN_RATE
- PANEL_INSTABILITY
Required evidence:
- Beneficiary count trend
- Peer comparison
Next steps:
- Check whether provider added a new site/contract; if not, investigate
Routing: provider_risk_queue, P2

---

## MDV-06 Upcoding / high-complexity code mix outlier
Target entity: provider
Type: peeroutlier
What it flags: Elevated rate of high-complexity procedures or modifiers vs peers.
Reason codes:
- HIGH_COMPLEXITY_RATE
- CODE_MIX_OUTLIER
- PEER_DEVIATION
Required evidence:
- Code-mix distribution vs peer
- Sample of high-complexity lines
Next steps:
- SME review for appropriateness; adjust for case-mix segments if needed
Routing: provider_risk_queue, P2

---

## MDV-07 Location/time anomaly (if location + timestamps available)
Target entity: provider or clinicgroup
Type: rule + peeroutlier
What it flags: Improbable service volumes at certain locations or unusual time-of-day/weekend patterns.
Reason codes:
- UNUSUAL_LOCATION_VOLUME
- UNUSUAL_TIME_PATTERN
- POS_LOCATION_OUTLIER
Required evidence:
- Location distribution
- Timeline of service volume by hour/day
Next steps:
- Validate location feed; investigate scheduling/operational confounders
Routing: clinic_triage_queue, P3

---

## MDV-08 Same-day multi-location / improbable travel (optional)
Target entity: beneficiary cohort or provider
Type: rule
What it flags: Patterns suggesting implausible sequences (requires sufficient geo granularity).
Reason codes:
- IMPROBABLE_SEQUENCE
- MULTI_LOCATION_SAME_DAY
- DATA_OR_FRAUD_SIGNAL
Required evidence:
- De-identified sequence table (dates/locations)
Next steps:
- Validate geo quality; if valid, escalate for deeper review
Routing: provider_risk_queue, P3

---

## MDV-09 Prior auth mismatch / bypass (if prior auth exists)
Target entity: provider
Type: rule
What it flags: Services frequently lacking required prior auth or inconsistent with auth scope.
Reason codes:
- PRIOR_AUTH_MISMATCH
- AUTH_BYPASS_PATTERN
- POLICY_NONCOMPLIANCE_SIGNAL
Required evidence:
- Prior auth linkage table (authorized vs observed)
Next steps:
- Route to MCO/state PI review; check policy windows
Routing: provider_risk_queue, P1/P2

---

## MDV-10 Composite corroboration score
Target entity: provider or clinicgroup
Type: composite
What it flags: Multi-signal corroboration across rings + utilization spikes + bundle outliers.
Reason codes:
- MULTI_SIGNAL_CORROBORATION
- RING_PLUS_UTILIZATION
- BUNDLE_PLUS_TEMPORAL
Required evidence:
- Contributing indicators panel + pointers
Next steps:
- Prioritize for SIU/MFCU referral package assembly as appropriate
Routing: provider_risk_queue, P0/P1
