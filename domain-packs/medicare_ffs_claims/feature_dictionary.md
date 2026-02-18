# /domain-packs/medicareffsclaims/feature_dictionary.md
DomainPackId: medicareffsclaims [file:1]
Version: 0.1.0 [file:1]

Purpose
- Define a stable, cross-use-case feature vocabulary that indicators reference via `featureinputs` (C02), and that drift checks/dashboards monitor weekly. [file:1]

Conventions
- Feature names are snake_case and prefixed by grain: provider_, beneficiary_, claim_, claimline_, graph_. [file:1]
- Windowed aggregates suffix: _w30d/_w90d/_w180d/_w365d, computed as-of `as_of_date`. [file:1]
- Missingness handling: emit *_missing_flag features and downgrade confidence when required evidence elements are missing. [file:1]

## A) Provider-window aggregate features (primary table)
Grain: (provider_id, claim_type, as_of_date, window) [file:1]

Volume / utilization
- provider_claim_count_wXd: Count of distinct claims. [file:1]
- provider_claimline_count_wXd: Count of distinct claim lines. [file:1]
- provider_unique_beneficiaries_wXd: Count of unique beneficiaries. [file:1]
- provider_units_sum_wXd: Sum of units (when available). [file:1]
- provider_allowed_amt_sum_wXd: Sum allowed (when available). [file:1]
- provider_paid_amt_sum_wXd: Sum paid (when available). [file:1]
- provider_services_per_beneficiary_wXd: claimline_count / unique_beneficiaries. [file:1]
- provider_units_per_beneficiary_wXd: units_sum / unique_beneficiaries. [file:1]

Code-mix
- provider_code_entropy_wXd: Entropy of hcpcs/cpt/revenue-center distribution. [file:1]
- provider_top_code_share_wXd: Share of volume in most frequent code. [file:1]
- provider_rare_code_family_rate_wXd: Share of volume in “rare” code families (domain-configured list). [file:1]

Temporal stability
- provider_util_rate_7d: Rolling 7-day utilization rate (choose numerator/denominator per indicator). [file:1]
- provider_util_rate_baseline_90d: Baseline rate for comparison. [file:1]
- provider_util_rate_zscore_7d_vs_90d: Z-score of 7d vs baseline. [file:1]
- provider_change_point_flag_7d: Change-point detected (boolean; method configurable). [file:1]

Concentration / panel dynamics
- provider_new_beneficiaries_wXd: Beneficiaries first seen with provider in window. [file:1]
- provider_new_beneficiary_share_wXd: new_beneficiaries / unique_beneficiaries. [file:1]
- provider_beneficiary_concentration_hhi_wXd: HHI over beneficiary volumes (optional). [file:1]

Duplicates / repeat patterns (rule-friendly)
- provider_duplicate_like_line_count_wXd: Count of lines in near-duplicate clusters (same code/units/date rules). [file:1]
- provider_duplicate_like_line_rate_wXd: duplicate_like_line_count / claimline_count. [file:1]

## B) Peer-group features (computed for peeroutlier indicators)
Grain: (provider_id, peer_group_id, metric_name, as_of_date, window) [file:1]
- peer_group_definition_text: Human-readable specialty × geography × claim_type definition. [file:1]
- peer_metric_median_wXd / peer_metric_p90_wXd / peer_metric_p99_wXd. [file:1]
- provider_metric_percentile_wXd / provider_metric_zscore_wXd. [file:1]
- peer_group_size_wXd; peer_group_too_small_flag. [file:1]

## C) Optional graph features (only if permitted)
Grain: (provider_id, as_of_date, window) [file:1]
- graph_shared_beneficiary_degree_wXd: Number of other providers sharing ≥N beneficiaries. [file:1]
- graph_ordering_supplier_exclusivity_wXd: Share of supplier volume from top ordering provider (or inverse). [file:1]
- graph_shared_contact_degree_wXd: Degree via shared contact/address (permissioned). [file:1]

## D) Drift monitoring set (weekly)
For each indicator, monitor drift on its top 10 referenced features, plus score distribution drift. [file:1]
Minimum telemetry alignment: `featurebuildcompleted` for feature refresh lineage, `driftcheckcompleted` for drift results. [file:1]

## E) Indicator → feature inputs mapping (v0.1)
- MCR-01: provider_services_per_beneficiary_w90d, provider_units_per_beneficiary_w90d, peer_* stats for same metrics. [file:1]
- MCR-02: provider_code_entropy_w90d, provider_top_code_share_w90d, provider_rare_code_family_rate_w90d, peer_* stats. [file:1]
- MCR-03: provider_util_rate_7d, provider_util_rate_baseline_90d, provider_util_rate_zscore_7d_vs_90d, provider_change_point_flag_7d. [file:1]
- MCR-04: provider_unique_beneficiaries_w90d, provider_new_beneficiary_share_w90d, provider_beneficiary_concentration_hhi_w90d (optional), graph_shared_beneficiary_degree_w90d (optional). [file:1]
- MCR-05: (if POS/location present) provider_pos_mix_* features (domain extension) + peer stats. [file:1]
- MCR-06: provider_duplicate_like_line_count_w90d, provider_duplicate_like_line_rate_w90d. [file:1]
- MCR-07: graph_ordering_supplier_exclusivity_w180d, graph_shared_beneficiary_degree_w180d (as available). [file:1]
- MCR-08: peer_group_size_w90d, peer_group_too_small_flag, peer composition drift metrics (from drift checks). [file:1]
- MCR-09: policy_window_active_flag (use-case config) + provider_util_rate_* trend features. [file:1]
- MCR-10: composite uses the contributing indicators’ feature sets; store contribution shares. [file:1]
