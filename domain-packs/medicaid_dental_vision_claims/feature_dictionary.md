# /domain-packs/medicaiddentalvisionclaims/feature_dictionary.md
DomainPackId: medicaiddentalvisionclaims [file:1]
Version: 0.1.0 [file:1]

Purpose
- Define a reusable feature vocabulary for Medicaid dental/vision claims PI indicators (provider/clinic triage, ring signals, code-pattern anomalies), monitored weekly. [file:1]

Conventions
- Grains: provider-window (provider_id), clinicgroup-window (clinicgroup_id), and optional graph cluster grain. [file:1]
- Windows: _w30d/_w90d/_w180d; compute as-of `as_of_date`. [file:1]

## A) Provider-window aggregate features
Grain: (provider_id, as_of_date, window) [file:1]

Volume / dollars
- provider_claim_count_wXd. [file:1]
- provider_claimline_count_wXd. [file:1]
- provider_unique_beneficiaries_wXd. [file:1]
- provider_units_sum_wXd (if units exist). [file:1]
- provider_paid_amt_sum_wXd / provider_allowed_amt_sum_wXd (if available). [file:1]
- provider_services_per_beneficiary_wXd. [file:1]

Procedure mix / complexity
- provider_proc_entropy_wXd: Entropy of procedure_code distribution. [file:1]
- provider_top_proc_share_wXd. [file:1]
- provider_high_complexity_rate_wXd: Share of lines in configured “high complexity” code set. [file:1]
- provider_rare_bundle_rate_wXd: Share of lines in rare co-occurrence bundles (if bundle mining used). [file:1]

Temporal utilization change
- provider_volume_7d: Rolling 7-day line volume. [file:1]
- provider_volume_baseline_90d; provider_volume_zscore_7d_vs_90d; provider_change_point_flag_7d. [file:1]

Repeat services / trajectories (beneficiary-level aggregates rolled up to provider)
- provider_repeat_interval_p50_wXd: Median days between repeat procedures per beneficiary (configurable by procedure group). [file:1]
- provider_short_interval_repeat_rate_wXd: Share of repeats within “too soon” threshold. [file:1]

Panel dynamics
- provider_new_beneficiary_share_wXd. [file:1]
- provider_churn_rate_wXd: Share of beneficiaries not seen in prior baseline window (definition configurable). [file:1]

Location/time patterns (if location/time granularity exists)
- provider_location_count_wXd. [file:1]
- provider_location_concentration_hhi_wXd. [file:1]
- provider_weekend_share_wXd (if service_dt supports). [file:1]

## B) Peer-group features
Grain: (provider_id, peer_group_id, metric_name, as_of_date, window) [file:1]
- peer_metric_median/p90/p99, provider_metric_percentile/zscore, peer_group_size, peer_group_too_small_flag. [file:1]

## C) Ring / graph features (optional / permissioned)
Grain: (provider_id or clinicgroup_id, as_of_date, window) [file:1]
- graph_shared_location_degree_wXd: Number of other providers sharing locations above threshold. [file:1]
- graph_shared_attribute_degree_wXd: Degree via shared address/phone/bank (permissioned). [file:1]
- graph_shared_beneficiary_overlap_degree_wXd: Degree via high beneficiary overlap. [file:1]
- graph_cluster_density_wXd: Density of detected provider cluster. [file:1]

## D) Drift monitoring set (weekly)
Monitor drift on each indicator’s top 10 features (mix + utilization + ring metrics where used) and score drift per indicator. [file:1]
Minimum telemetry alignment: `featurebuildcompleted`, `driftcheckcompleted`, and weekly `monitoringmetricscomputed`. [file:1]

## E) Indicator → feature inputs mapping (v0.1)
- MDV-01: graph_shared_attribute_degree_w90d, graph_cluster_density_w90d, graph_shared_location_degree_w90d (as permitted). [file:1]
- MDV-02: provider_rare_bundle_rate_w90d, provider_proc_entropy_w90d, provider_top_proc_share_w90d, peer stats. [file:1]
- MDV-03: provider_volume_zscore_7d_vs_90d, provider_change_point_flag_7d, provider_paid_amt_sum_w30d (+ peer stats). [file:1]
- MDV-04: provider_short_interval_repeat_rate_w90d, provider_repeat_interval_p50_w90d. [file:1]
- MDV-05: provider_new_beneficiary_share_w90d, provider_churn_rate_w90d (+ peer stats). [file:1]
- MDV-06: provider_high_complexity_rate_w90d, provider_proc_entropy_w90d (+ peer stats). [file:1]
- MDV-07: provider_location_count_w90d, provider_weekend_share_w90d, provider_location_concentration_hhi_w90d. [file:1]
- MDV-08: (optional) beneficiary_sequence_improbable_rate_w90d (domain extension; requires geo/time). [file:1]
- MDV-09: prior_auth_mismatch_rate_w90d (domain extension; requires PA feed). [file:1]
- MDV-10: composite uses the contributing indicators’ feature sets; store contribution shares. [file:1]
