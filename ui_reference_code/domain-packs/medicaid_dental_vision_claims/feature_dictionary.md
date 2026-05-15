# /domain-packs/medicaiddentalvisionclaims/feature_dictionary.md
DomainPackId: medicaiddentalvisionclaims
Version: 0.1.0

Purpose
- Define a reusable feature vocabulary for Medicaid dental/vision claims PI indicators (provider/clinic triage, ring signals, code-pattern anomalies), monitored weekly.

Conventions
- Grains: provider-window (provider_id), clinicgroup-window (clinicgroup_id), and optional graph cluster grain.
- Windows: _w30d/_w90d/_w180d; compute as-of `as_of_date`.

## A) Provider-window aggregate features
Grain: (provider_id, as_of_date, window)

Volume / dollars
- provider_claim_count_wXd.
- provider_claimline_count_wXd.
- provider_unique_beneficiaries_wXd.
- provider_units_sum_wXd (if units exist).
- provider_paid_amt_sum_wXd / provider_allowed_amt_sum_wXd (if available).
- provider_services_per_beneficiary_wXd.

Procedure mix / complexity
- provider_proc_entropy_wXd: Entropy of procedure_code distribution.
- provider_top_proc_share_wXd.
- provider_high_complexity_rate_wXd: Share of lines in configured “high complexity” code set.
- provider_rare_bundle_rate_wXd: Share of lines in rare co-occurrence bundles (if bundle mining used).

Temporal utilization change
- provider_volume_7d: Rolling 7-day line volume.
- provider_volume_baseline_90d; provider_volume_zscore_7d_vs_90d; provider_change_point_flag_7d.

Repeat services / trajectories (beneficiary-level aggregates rolled up to provider)
- provider_repeat_interval_p50_wXd: Median days between repeat procedures per beneficiary (configurable by procedure group).
- provider_short_interval_repeat_rate_wXd: Share of repeats within “too soon” threshold.

Panel dynamics
- provider_new_beneficiary_share_wXd.
- provider_churn_rate_wXd: Share of beneficiaries not seen in prior baseline window (definition configurable).

Location/time patterns (if location/time granularity exists)
- provider_location_count_wXd.
- provider_location_concentration_hhi_wXd.
- provider_weekend_share_wXd (if service_dt supports).

## B) Peer-group features
Grain: (provider_id, peer_group_id, metric_name, as_of_date, window)
- peer_metric_median/p90/p99, provider_metric_percentile/zscore, peer_group_size, peer_group_too_small_flag.

## C) Ring / graph features (optional / permissioned)
Grain: (provider_id or clinicgroup_id, as_of_date, window)
- graph_shared_location_degree_wXd: Number of other providers sharing locations above threshold.
- graph_shared_attribute_degree_wXd: Degree via shared address/phone/bank (permissioned).
- graph_shared_beneficiary_overlap_degree_wXd: Degree via high beneficiary overlap.
- graph_cluster_density_wXd: Density of detected provider cluster.

## D) Drift monitoring set (weekly)
Monitor drift on each indicator’s top 10 features (mix + utilization + ring metrics where used) and score drift per indicator.
Minimum telemetry alignment: `featurebuildcompleted`, `driftcheckcompleted`, and weekly `monitoringmetricscomputed`.

## E) Indicator → feature inputs mapping (v0.1)
- MDV-01: graph_shared_attribute_degree_w90d, graph_cluster_density_w90d, graph_shared_location_degree_w90d (as permitted).
- MDV-02: provider_rare_bundle_rate_w90d, provider_proc_entropy_w90d, provider_top_proc_share_w90d, peer stats.
- MDV-03: provider_volume_zscore_7d_vs_90d, provider_change_point_flag_7d, provider_paid_amt_sum_w30d (+ peer stats).
- MDV-04: provider_short_interval_repeat_rate_w90d, provider_repeat_interval_p50_w90d.
- MDV-05: provider_new_beneficiary_share_w90d, provider_churn_rate_w90d (+ peer stats).
- MDV-06: provider_high_complexity_rate_w90d, provider_proc_entropy_w90d (+ peer stats).
- MDV-07: provider_location_count_w90d, provider_weekend_share_w90d, provider_location_concentration_hhi_w90d.
- MDV-08: (optional) beneficiary_sequence_improbable_rate_w90d (domain extension; requires geo/time).
- MDV-09: prior_auth_mismatch_rate_w90d (domain extension; requires PA feed).
- MDV-10: composite uses the contributing indicators’ feature sets; store contribution shares.
