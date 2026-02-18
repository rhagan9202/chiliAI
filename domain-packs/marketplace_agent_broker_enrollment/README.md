# /domain-packs/marketplaceagentbrokerenrollment/README.md
DomainPackId: marketplaceagentbrokerenrollment [file:1]
Version: 0.1.0 [file:1]

# Purpose
- Detect and triage suspected unauthorized enrollments and unauthorized plan switches linked to agents/brokers using enrollment-change patterns plus complaint/casework signals. [file:1]
- Outputs must map to feasible operational controls and casework workflows, with human review required for any consequential action. [file:1]

# What’s in this pack
- schema.md: Consumer/enrollment/change-event, broker NPN, complaint/case, association history (+ optional consent/device/contact). [file:1]
- evidence_bundle_spec.md: Required timeline slices (change events, complaints, association audit) and completeness rules. [file:1]
- feature_dictionary.md: Broker-window, event-level, and optional cluster features with time windows and drift set. [file:1]
- indicators.v0.1.md: 10 broker/event indicators (switch spikes, complaint concentration, association mismatch, bursts, reversals, clusters). [file:1]
- eval_dataset_spec.md: Stratified sampling and labeling tuned to complaint linkage + association-based controls. [file:1]

# Minimum data requirements (v0.1)
- EnrollmentChangeEvent with broker attribution (broker_npn when present), timestamps, and change types (enroll/switch/terminate/update). [file:1]
- ComplaintCase feed with complaint type/date/status and keys to consumer/enrollment and broker_npn when present or inferable. [file:1]
- BrokerConsumerAssociation history sufficient to detect “not associated at change” and “just-in-time association.” [file:1]

# Operational workflow integration
- System should output (1) broker risk queue and (2) event triage queue, each with evidence bundles and structured feedback capture. [file:1]
- Governance requires change logs for threshold/peer-group changes and a pause/discontinue mechanism when performance or evidence quality degrades. [file:1]

# Quick start
1) Implement indicators 01–05 end-to-end first (switch spike, complaint linkage, association mismatch, burst activity, reversal/remediation rate) since they align to complaint/casework workflows. [file:1]
2) Run eval on a time-sliced, stratified set that includes complaint-linked and non-complaint cases to avoid overfitting to complaint presence. [file:1]
3) Add optional graph/cluster indicators only after evidence completeness rules and investigator feedback loops are stable. [file:1]
