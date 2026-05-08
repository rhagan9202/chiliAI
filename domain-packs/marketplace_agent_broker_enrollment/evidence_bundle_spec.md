# Evidence Bundle Spec — Marketplace Agent/Broker Enrollment Integrity (v0.1)
DomainPackId: marketplaceagentbrokerenrollment
Version: 0.1.0

Purpose
- Standardize what investigators see for broker-level and event-level cases (timeline, association status, complaint linkage, and optional cluster/network evidence).

## 1) Required evidence elements (domain-level)
For any broker- or event-level case, the bundle SHOULD include:
- EnrollmentChangeEvent timeline slice (windowed)
- BrokerConsumerAssociation history slice
- ComplaintCase linkage slice (if available)
- Peer comparison stats for broker-level rates (for peer/time-series indicators)

## 2) Evidence views
A) Timeline
- Change events ordered by time with change_type, channel/source, and broker attribution
- Overlay complaint arrivals (by type/severity)
- Overlay association start/remove timestamps

B) Tables
- Broker event list: top contributing change events (consumer_id surrogate, event dt/type)
- Complaint list: complaint dt/type/status, linkage notes
- Association audit: association status over time, “just-in-time association” markers

C) Optional network card
- Consumer-contact clusters (hashed contact/device nodes)
- Broker clusters (handoff loops)

## 3) Completeness rules (v0.1 defaults)
Evidence completeness FALSE if:
- For an association-mismatch indicator: association history is missing for the impacted consumer/enrollment window
- For complaint-linked indicators: complaint feed is stale beyond SLA or linkage keys missing
- For peer/time-series indicators: peer group stats cannot be computed for the broker

If completeness FALSE:
- downgrade confidenceband=low and prompt investigators to label insufficient_evidence.
