# Indicator Library — Marketplace Agent/Broker Enrollment Integrity (v0.1)
DomainPackId: marketplaceagentbrokerenrollment
Version: 0.1.0
Target workflow: unauthorized enrollment / unauthorized plan switch detection + broker oversight + case prioritization.

Indicator IDs: MKT-01..MKT-10

---

## MKT-01 Broker abnormal switch rate spike (temporal + peer)
Target entity: broker (NPN)
Type: timeseries + peeroutlier
What it flags: Broker plan-switch rate rises sharply vs its baseline and vs peer brokers (region/channel).
Suggested threshold: z-score >= 3 on 7-day rolling rate (SME-calibrated).
Reason codes:
- SWITCH_VOLUME_SPIKE
- PEER_OUTLIER_RATE
- CHANGE_POINT_DETECTED
Required evidence:
- Timeline of change events
- Peer comparison table
Next steps:
- Sample top 20 events; check association status and complaint overlap
Routing: broker_triage_queue, P0/P1

---

## MKT-02 Complaint-linked broker concentration
Target entity: broker (NPN)
Type: rule + peeroutlier
What it flags: Broker linked to unusually high complaint count/rate for unauthorized enrollment/switch.
Reason codes:
- HIGH_COMPLAINT_LINKAGE
- COMPLAINT_RATE_OUTLIER
- SEVERITY_MIX_SPIKE
Required evidence:
- Complaint list and counts over time
- Complaint rate vs peers
Next steps:
- Prioritize for case package; verify consent evidence pathways where available
Routing: broker_triage_queue, P0/P1

---

## MKT-03 Association mismatch prior to enrollment change
Target entity: enrollment_change_event
Type: rule
What it flags: Change attributed to broker not previously associated with that consumer/enrollment, or association added immediately before change.
Reason codes:
- NOT_ASSOCIATED_AT_CHANGE
- JUST_IN_TIME_ASSOCIATION
- ASSOCIATION_AUDIT_FLAG
Required evidence:
- Association audit trail (before/after)
- Change event metadata
Next steps:
- Validate whether change occurred via approved exception pathway; route to investigation
Routing: event_triage_queue, P0

---

## MKT-04 Rapid multi-consumer change burst (“spray and pray”)
Target entity: broker (NPN)
Type: timeseries + rule
What it flags: Many consumers changed/enrolled in a tight time window inconsistent with broker’s normal pattern.
Reason codes:
- BURST_ACTIVITY
- UNUSUAL_TIME_OF_DAY
- HIGH_EVENT_DENSITY
Required evidence:
- Burst window list of events
- Geographic spread summary (if available)
Next steps:
- Sample events; check channel/source consistency and association status
Routing: broker_triage_queue, P1

---

## MKT-05 High reversal / remediation rate
Target entity: broker (NPN)
Type: peeroutlier
What it flags: Large share of broker-driven changes are reversed or lead to remediation/casework outcomes.
Reason codes:
- HIGH_REVERSAL_RATE
- REMEDIATION_HEAVY
- POST_EVENT_COMPLAINT
Required evidence:
- Event → reversal timeline
- Complaint/resolution linkage
Next steps:
- Deep dive affected consumers; prioritize for oversight package
Routing: broker_triage_queue, P1

---

## MKT-06 Commission-change anomaly (if commission signals exist)
Target entity: broker (NPN)
Type: peeroutlier
What it flags: Unusual commission-related change frequency, especially when complaint-linked.
Reason codes:
- COMMISSION_ANOMALY
- PEER_OUTLIER_COMMISSION
- COMPLAINT_OVERLAP
Required evidence:
- Commission change history (if permitted)
- Complaint overlap table
Next steps:
- Route to oversight review; confirm whether operational confounders apply
Routing: broker_triage_queue, P2

---

## MKT-07 Consumer contact reuse cluster (graph)
Target entity: broker (NPN) and cluster
Type: graphpattern
What it flags: Many consumers share phone/email/address/device patterns disproportionately tied to one broker/broker cluster.
Reason codes:
- SHARED_CONTACT_CLUSTER
- BROKER_CONCENTRATION_IN_CLUSTER
- CLUSTER_DENSITY_HIGH
Required evidence:
- Capped subgraph (consumer surrogates ↔ contact hashes ↔ broker)
- Cluster summary stats
Next steps:
- Determine if legitimate assister patterns explain it; otherwise escalate
Routing: broker_triage_queue, P2

---

## MKT-08 Cross-broker handoff loop (graph + temporal)
Target entity: broker cluster
Type: graphpattern + timeseries
What it flags: Consumers repeatedly shift between a small set of brokers over short intervals.
Reason codes:
- BROKER_HANDOFF_LOOP
- SHORT_INTERVAL_SWITCHES
- CLUSTER_RECURRENCE
Required evidence:
- Per-consumer broker timeline slice
- Capped broker cluster subgraph
Next steps:
- Check whether consumer-initiated; cross-check complaint linkage
Routing: broker_triage_queue, P2

---

## MKT-09 Composite corroboration (01+02+03)
Target entity: broker (NPN)
Type: composite
What it flags: Multi-signal corroboration across switch spike + complaint linkage + association mismatch prevalence.
Reason codes:
- MULTI_SIGNAL_CORROBORATION
- COMPLAINT_PLUS_SWITCH
- ASSOCIATION_MISMATCH_PATTERN
Required evidence:
- Contributing indicator pointers (evidence slices)
Next steps:
- Prioritize for immediate investigator sampling and PI ops oversight
Routing: broker_triage_queue, P0

---

## MKT-10 Policy/control evasion pattern (rules)
Target entity: enrollment_change_event
Type: rule
What it flags: Events that appear to bypass expected engagement/consent markers (if available) or show channel anomalies.
Reason codes:
- MISSING_ENGAGEMENT_MARKER
- CHANNEL_ANOMALY
- CONSENT_GAP
Required evidence:
- Event metadata
- Consent verification signals (if available)
Next steps:
- Route to specialized queue; request more info when evidence is incomplete
Routing: event_triage_queue, P1/P2
