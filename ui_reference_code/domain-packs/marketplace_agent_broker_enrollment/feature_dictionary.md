# /domain-packs/marketplaceagentbrokerenrollment/feature_dictionary.md
DomainPackId: marketplaceagentbrokerenrollment
Version: 0.1.0

Purpose
- Define the broker/event features used by Marketplace agent/broker indicators and monitored weekly for drift and performance.

Conventions
- Grains: broker-window (broker_npn), event-level (change_event_id), and cluster-level (cluster_id).
- Windows: _w7d/_w14d/_w30d/_w90d; all time-aware and computed as-of `as_of_dt`.

## A) Broker-window aggregate features
Grain: (broker_npn, as_of_dt, window)

Enrollment/change activity
- broker_change_event_count_wXd: Total attributed change events.
- broker_switch_count_wXd: Count where change_type == switch.
- broker_new_enroll_count_wXd: Count where change_type == new_enroll.
- broker_switch_rate_wXd: switch_count / change_event_count.

Temporal burstiness
- broker_max_events_per_hour_wXd: Max hourly count in window.
- broker_burst_flag_wXd: True if max_events_per_hour exceeds configured threshold.
- broker_off_hours_share_wXd: Share of events in configured off-hours.

Complaints / casework linkage
- broker_complaint_count_wXd: Count of complaints linked to broker (direct or inferred).
- broker_complaint_rate_wXd: complaint_count / change_event_count.
- broker_complaint_severity_mix_wXd: Distribution over severity bands (if available).
- broker_complaint_lag_days_p50_wXd: Complaint arrival lag vs event (if linkable).

Association integrity
- broker_assoc_mismatch_count_wXd: Count of events where broker not associated at change time.
- broker_assoc_just_in_time_count_wXd: Count where association_start within X hours/days pre-change.
- broker_assoc_mismatch_rate_wXd: assoc_mismatch_count / change_event_count.

Remediation / reversal
- broker_reversal_count_wXd: Events reversed within Y days (config).
- broker_reversal_rate_wXd: reversal_count / change_event_count.

Commission (optional / permissioned)
- broker_commission_change_count_wXd; broker_commission_change_rate_wXd.

## B) Event-level features (for event triage)
Grain: (change_event_id)
- event_has_prior_association_flag (bool).
- event_just_in_time_association_flag (bool).
- event_channel_anomaly_flag (bool; rules configured).
- event_missing_engagement_marker_flag (bool; depends on consent/call-center feeds).
- event_complaint_linked_flag (bool; if complaint linkage exists).

## C) Cluster/graph features (optional)
Grain: (broker_npn, as_of_dt, window) or (cluster_id, as_of_dt, window)
- broker_contact_cluster_max_size_wXd: Max size of consumer-contact cluster tied to broker.
- broker_contact_cluster_concentration_wXd: Share of broker events within top cluster.
- broker_handoff_loop_count_wXd: Count of consumers with ≥N broker switches among small broker set within M days.

## D) Drift monitoring set (weekly)
For each indicator, monitor drift on its referenced top features (e.g., switch_rate, complaint_rate, assoc_mismatch_rate) and score distribution drift.
Minimum telemetry alignment: `featurebuildcompleted`, `monitoringmetricscomputed`, and `driftcheckcompleted`.

## E) Indicator → feature inputs mapping (v0.1)
- MKT-01: broker_switch_rate_w7d, broker_switch_rate_w90d (baseline), broker_max_events_per_hour_w7d, peer stats by region/channel.
- MKT-02: broker_complaint_rate_w30d, broker_complaint_count_w30d, broker_complaint_severity_mix_w30d, peer stats.
- MKT-03: event_has_prior_association_flag, event_just_in_time_association_flag.
- MKT-04: broker_max_events_per_hour_w7d, broker_off_hours_share_w7d, broker_change_event_count_w7d.
- MKT-05: broker_reversal_rate_w90d, broker_reversal_count_w90d, broker_complaint_rate_w90d.
- MKT-06: broker_commission_change_rate_w90d (if present), broker_complaint_linkage features.
- MKT-07: broker_contact_cluster_max_size_w90d, broker_contact_cluster_concentration_w90d.
- MKT-08: broker_handoff_loop_count_w90d (+ supporting per-consumer switching counts if implemented).
- MKT-09: composite uses MKT-01/02/03 feature sets; store contribution shares.
- MKT-10: event_channel_anomaly_flag, event_missing_engagement_marker_flag, event_complaint_linked_flag (as available).
