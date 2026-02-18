# /domain-packs/marketplaceagentbrokerenrollment/feature_dictionary.md
DomainPackId: marketplaceagentbrokerenrollment [file:1]
Version: 0.1.0 [file:1]

Purpose
- Define the broker/event features used by Marketplace agent/broker indicators and monitored weekly for drift and performance. [file:1]

Conventions
- Grains: broker-window (broker_npn), event-level (change_event_id), and cluster-level (cluster_id). [file:1]
- Windows: _w7d/_w14d/_w30d/_w90d; all time-aware and computed as-of `as_of_dt`. [file:1]

## A) Broker-window aggregate features
Grain: (broker_npn, as_of_dt, window) [file:1]

Enrollment/change activity
- broker_change_event_count_wXd: Total attributed change events. [file:1]
- broker_switch_count_wXd: Count where change_type == switch. [file:1]
- broker_new_enroll_count_wXd: Count where change_type == new_enroll. [file:1]
- broker_switch_rate_wXd: switch_count / change_event_count. [file:1]

Temporal burstiness
- broker_max_events_per_hour_wXd: Max hourly count in window. [file:1]
- broker_burst_flag_wXd: True if max_events_per_hour exceeds configured threshold. [file:1]
- broker_off_hours_share_wXd: Share of events in configured off-hours. [file:1]

Complaints / casework linkage
- broker_complaint_count_wXd: Count of complaints linked to broker (direct or inferred). [file:1]
- broker_complaint_rate_wXd: complaint_count / change_event_count. [file:1]
- broker_complaint_severity_mix_wXd: Distribution over severity bands (if available). [file:1]
- broker_complaint_lag_days_p50_wXd: Complaint arrival lag vs event (if linkable). [file:1]

Association integrity
- broker_assoc_mismatch_count_wXd: Count of events where broker not associated at change time. [file:1]
- broker_assoc_just_in_time_count_wXd: Count where association_start within X hours/days pre-change. [file:1]
- broker_assoc_mismatch_rate_wXd: assoc_mismatch_count / change_event_count. [file:1]

Remediation / reversal
- broker_reversal_count_wXd: Events reversed within Y days (config). [file:1]
- broker_reversal_rate_wXd: reversal_count / change_event_count. [file:1]

Commission (optional / permissioned)
- broker_commission_change_count_wXd; broker_commission_change_rate_wXd. [file:1]

## B) Event-level features (for event triage)
Grain: (change_event_id) [file:1]
- event_has_prior_association_flag (bool). [file:1]
- event_just_in_time_association_flag (bool). [file:1]
- event_channel_anomaly_flag (bool; rules configured). [file:1]
- event_missing_engagement_marker_flag (bool; depends on consent/call-center feeds). [file:1]
- event_complaint_linked_flag (bool; if complaint linkage exists). [file:1]

## C) Cluster/graph features (optional)
Grain: (broker_npn, as_of_dt, window) or (cluster_id, as_of_dt, window) [file:1]
- broker_contact_cluster_max_size_wXd: Max size of consumer-contact cluster tied to broker. [file:1]
- broker_contact_cluster_concentration_wXd: Share of broker events within top cluster. [file:1]
- broker_handoff_loop_count_wXd: Count of consumers with ≥N broker switches among small broker set within M days. [file:1]

## D) Drift monitoring set (weekly)
For each indicator, monitor drift on its referenced top features (e.g., switch_rate, complaint_rate, assoc_mismatch_rate) and score distribution drift. [file:1]
Minimum telemetry alignment: `featurebuildcompleted`, `monitoringmetricscomputed`, and `driftcheckcompleted`. [file:1]

## E) Indicator → feature inputs mapping (v0.1)
- MKT-01: broker_switch_rate_w7d, broker_switch_rate_w90d (baseline), broker_max_events_per_hour_w7d, peer stats by region/channel. [file:1]
- MKT-02: broker_complaint_rate_w30d, broker_complaint_count_w30d, broker_complaint_severity_mix_w30d, peer stats. [file:1]
- MKT-03: event_has_prior_association_flag, event_just_in_time_association_flag. [file:1]
- MKT-04: broker_max_events_per_hour_w7d, broker_off_hours_share_w7d, broker_change_event_count_w7d. [file:1]
- MKT-05: broker_reversal_rate_w90d, broker_reversal_count_w90d, broker_complaint_rate_w90d. [file:1]
- MKT-06: broker_commission_change_rate_w90d (if present), broker_complaint_linkage features. [file:1]
- MKT-07: broker_contact_cluster_max_size_w90d, broker_contact_cluster_concentration_w90d. [file:1]
- MKT-08: broker_handoff_loop_count_w90d (+ supporting per-consumer switching counts if implemented). [file:1]
- MKT-09: composite uses MKT-01/02/03 feature sets; store contribution shares. [file:1]
- MKT-10: event_channel_anomaly_flag, event_missing_engagement_marker_flag, event_complaint_linked_flag (as available). [file:1]
