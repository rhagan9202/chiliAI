# Indicator Library — Medicare FFS Claims (v0.1)
DomainPackId: medicareffsclaims
Version: 0.1.0
Target workflow: provider/supplier risk triage and case prioritization (triage support; not automated enforcement).

Conventions
- Indicator IDs: MCR-01..MCR-10
- Priority bands: P0 (highest) .. P3 (lowest)
- Confidence: low/medium/high (downgrade to low if evidence completeness fails)

---

## MCR-01 Provider utilization peer outlier
Type: peeroutlier
Target entity: provider (billing or rendering; configurable)
What it flags: Provider’s utilization rate is extreme vs peers (specialty x geography x claim_type) over a defined window.
Suggested initial metric(s): services_per_beneficiary_90d, units_per_beneficiary_90d, allowed_amt_per_beneficiary_90d (as available)
Reason codes:
- PEER_OUTLIER_UTIL
- HIGH_UNITS_PER_BENEFICIARY
- HIGH_ALLOWED_PER_BENEFICIARY
Required evidence elements:
- Peer comparison table for chosen metric(s)
- Claim/line sample (top contributing lines)
Next steps:
- Verify peer group definition (specialty/geography)
- Sample top contributing beneficiaries/lines; confirm confounders (seasonality/policy)
Routing:
- queuename: provider_risk_queue
- priorityband: P1 (upgrade to P0 if corroborated by MCR-03 or MCR-04)
Monitoring:
- volume, precisionproxy, drift, explanationusefulness, queueaging

---

## MCR-02 Code-mix concentration / unusual code family mix
Type: peeroutlier + distribution
Target entity: provider
What it flags: Provider’s code mix is unusually concentrated or deviates sharply from peer distribution.
Example metrics: top_code_share, code_entropy, rare_code_family_rate
Reason codes:
- CODE_MIX_OUTLIER
- HIGH_TOP_CODE_SHARE
- RARE_CODE_FAMILY_SPIKE
Required evidence elements:
- Code distribution view (provider vs peer)
- Top contributing claim lines by code
Next steps:
- Check whether code family is tied to known policy/edit changes
- Validate documentation/evidence adequacy for the specific code set
Routing: provider_risk_queue, P2
Monitoring: volume, precisionproxy, drift, explanationusefulness

---

## MCR-03 Temporal change-point in utilization (provider)
Type: timeseries
Target entity: provider
What it flags: Abrupt change in utilization/amount vs provider baseline and vs peer baseline.
Reason codes:
- CHANGE_POINT_DETECTED
- UTILIZATION_SPIKE
- UNUSUAL_TREND_SHIFT
Required evidence elements:
- Timeline with baseline vs comparison windows
- Metric trend line summary (p50/p90 over time)
Next steps:
- Confirm data freshness and whether the change aligns with external events (policy, operational)
- Review top contributing services during spike window
Routing: provider_risk_queue, P1
Monitoring: drift, volume, precisionproxy

---

## MCR-04 Beneficiary concentration / patient panel anomaly
Type: peeroutlier + network-ready
Target entity: provider
What it flags: Unusual concentration in a small beneficiary set, rapid new-beneficiary influx, or unusual beneficiary overlap patterns.
Reason codes:
- BENEFICIARY_CONCENTRATION
- NEW_BENEFICIARY_INFLUX
- HIGH_BENEFICIARY_OVERLAP
Required evidence elements:
- Beneficiary count/time-series summary
- (Optional) overlap network card (provider↔beneficiary surrogates)
Next steps:
- Sample a set of beneficiaries driving the concentration
- Check for legitimate referral patterns vs suspect steering
Routing: provider_risk_queue, P2
Monitoring: volume, drift, explanationusefulness

---

## MCR-05 Location / place-of-service anomaly (if POS/location available)
Type: rule + peeroutlier
Target entity: provider
What it flags: Services billed from unusual locations, improbable distance patterns (if location granularity exists), or atypical POS mix vs peers.
Reason codes:
- POS_MIX_OUTLIER
- UNUSUAL_LOCATION_PATTERN
- HIGH_REMOTE_SERVICE_SHARE
Required evidence elements:
- POS distribution view
- Claim/line table with service location fields (if available)
Next steps:
- Validate location fields completeness
- Compare to peer POS mix; identify confounders (telehealth policy windows)
Routing: provider_risk_queue, P3
Monitoring: drift, explanationusefulness

---

## MCR-06 Duplicate / near-duplicate billing pattern (rule)
Type: rule
Target entity: provider (or claimline)
What it flags: Repeated identical/similar claim lines (same code, units, dates) beyond expected norms (configurable).
Reason codes:
- REPEAT_BILLING_PATTERN
- DUPLICATE_LIKE_LINES
- HIGH_FREQUENCY_SAME_CODE
Required evidence elements:
- Claim/line cluster table (grouped duplicates)
- Timeline highlighting repeats
Next steps:
- Check data duplication vs true repeats
- Escalate for deeper audit sampling if repeated across beneficiaries
Routing: provider_risk_queue, P2
Monitoring: volume, precisionproxy, drift

---

## MCR-07 Ordering → supplier/supplier → beneficiary network anomaly (if ordering available)
Type: graphpattern
Target entity: supplier or ordering_provider
What it flags: Suspicious ordering-to-supplier linkage patterns (tight loops, high exclusivity, sudden dominance shifts).
Reason codes:
- ORDERING_SUPPLIER_LOOP
- HIGH_EXCLUSIVITY_LINK
- NEW_DOMINANT_RELATIONSHIP
Required evidence elements:
- Network card with capped subgraph
- Table of top ordering-provider relationships
Next steps:
- Validate ordering fields completeness; check whether linkage is expected contract arrangement
- Route to specialized analyst for relationship review
Routing: supplier_risk_queue, P1
Monitoring: drift, explanationusefulness

---

## MCR-08 Peer-group instability / composition shift (safety signal)
Type: monitoring-oriented (operational indicator)
Target entity: indicator health (meta)
What it flags: Peer group definitions degrade (size drops below minimum) or peer composition shifts sharply, risking false positives.
Reason codes:
- PEER_GROUP_TOO_SMALL
- PEER_COMPOSITION_SHIFT
- BASELINE_UNSTABLE
Required evidence elements:
- Peer group size over time
- Drift dashboard snapshot (DASH 03)
Next steps:
- Redefine peer group; file C09; run mini-eval before resuming high-severity routing
Routing: not a queue indicator; triggers governance workflow
Monitoring: drift, volume, precisionproxy

---

## MCR-09 Policy window anomaly (pre/post known edit/rule window)
Type: rule + timeseries
Target entity: provider
What it flags: Patterns likely explained by policy/edit windows; used to prevent misuse and reduce false positives by tagging confounders.
Reason codes:
- POLICY_WINDOW_ACTIVE
- EXPECTED_SHIFT_CANDIDATE
- CONFUNDER_PRESENT
Required evidence elements:
- Timeline annotated with known windows (config)
- Metric trend showing step-change
Next steps:
- Document confounder in C01/C02; adjust evaluation and thresholds; do not treat as suspicious without corroboration
Routing: provider_risk_queue, P3 (or suppress)
Monitoring: explanationusefulness, precisionproxy

---

## MCR-10 Composite corroboration score (triage booster)
Type: composite
Target entity: provider
What it flags: Multi-signal corroboration across peer outlier + temporal + network-ready signals.
Inputs: MCR-01/02/03/04/07 (configurable)
Reason codes:
- MULTI_SIGNAL_CORROBORATION
- PEER_PLUS_TEMPORAL
- NETWORK_SUPPORTING_SIGNAL
Required evidence elements:
- “Contributing indicators” panel with pointers to each indicator’s evidence slice
Next steps:
- Prioritize for investigator/SME review; confirm evidence completeness and avoid over-reliance
Routing: provider_risk_queue, P0/P1 depending on threshold
Monitoring: precisionproxy, drift, explanationusefulness
