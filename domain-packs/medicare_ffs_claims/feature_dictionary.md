# /domain-packs/medicareffsclaims/feature_dictionary.md
DomainPackId: medicareffsclaims
Version: 0.1.0

Purpose
- Define a stable, cross-use-case feature vocabulary that indicators reference via `featureinputs` (C02), and that drift checks/dashboards monitor weekly.

Conventions
- Feature names are snake_case and prefixed by grain: provider_, beneficiary_, claim_, claimline_, graph_.
- Windowed aggregates suffix: _w30d/_w90d/_w180d/_w365d, computed as-of `as_of_date`.
- Missingness handling: emit *_missing_flag features and downgrade confidence when required evidence elements are missing.

## A) Provider-window aggregate features (primary table)
Grain: (provider_id, claim_type, as_of_date, window)

Volume / utilization
- provider_claim_count_wXd: Count of distinct claims.
- provider_claimline_count_wXd: Count of distinct claim lines.
- provider_unique_beneficiaries_wXd: Count of unique beneficiaries.
- provider_units_sum_wXd: Sum of units (when available).
- provider_allowed_amt_sum_wXd: Sum allowed (when available).
- provider_paid_amt_sum_wXd: Sum paid (when available).
- provider_services_per_beneficiary_wXd: claimline_count / unique_beneficiaries.
- provider_units_per_beneficiary_wXd: units_sum / unique_beneficiaries.

Code-mix
- provider_code_entropy_wXd: Entropy of hcpcs/cpt/revenue-center distribution.
- provider_top_code_share_wXd: Share of volume in most frequent code.
- provider_rare_code_family_rate_wXd: Share of volume in “rare” code families (domain-configured list).

Temporal stability
- provider_util_rate_7d: Rolling 7-day utilization rate (choose numerator/denominator per indicator).
- provider_util_rate_baseline_90d: Baseline rate for comparison.
- provider_util_rate_zscore_7d_vs_90d: Z-score of 7d vs baseline.
- provider_change_point_flag_7d: Change-point detected (boolean; method configurable).

Concentration / panel dynamics
- provider_new_beneficiaries_wXd: Beneficiaries first seen with provider in window.
- provider_new_beneficiary_share_wXd: new_beneficiaries / unique_beneficiaries.
- provider_beneficiary_concentration_hhi_wXd: HHI over beneficiary volumes (optional).

Duplicates / repeat patterns (rule-friendly)
- provider_duplicate_like_line_count_wXd: Count of lines in near-duplicate clusters (same code/units/date rules).
- provider_duplicate_like_line_rate_wXd: duplicate_like_line_count / claimline_count.

## B) Peer-group features (computed for peeroutlier indicators)
Grain: (provider_id, peer_group_id, metric_name, as_of_date, window)
- peer_group_definition_text: Human-readable specialty × geography × claim_type definition.
- peer_metric_median_wXd / peer_metric_p90_wXd / peer_metric_p99_wXd.
- provider_metric_percentile_wXd / provider_metric_zscore_wXd.
- peer_group_size_wXd; peer_group_too_small_flag.

## C) Optional graph features (only if permitted)
Grain: (provider_id, as_of_date, window)
- graph_shared_beneficiary_degree_wXd: Number of other providers sharing ≥N beneficiaries.
- graph_ordering_supplier_exclusivity_wXd: Share of supplier volume from top ordering provider (or inverse).
- graph_shared_contact_degree_wXd: Degree via shared contact/address (permissioned).

## D) Drift monitoring set (weekly)
For each indicator, monitor drift on its top 10 referenced features, plus score distribution drift.
Minimum telemetry alignment: `featurebuildcompleted` for feature refresh lineage, `driftcheckcompleted` for drift results.

## E) Indicator → feature inputs mapping (v0.1)
- MCR-01: provider_services_per_beneficiary_w90d, provider_units_per_beneficiary_w90d, peer_* stats for same metrics.
- MCR-02: provider_code_entropy_w90d, provider_top_code_share_w90d, provider_rare_code_family_rate_w90d, peer_* stats.
- MCR-03: provider_util_rate_7d, provider_util_rate_baseline_90d, provider_util_rate_zscore_7d_vs_90d, provider_change_point_flag_7d.
- MCR-04: provider_unique_beneficiaries_w90d, provider_new_beneficiary_share_w90d, provider_beneficiary_concentration_hhi_w90d (optional), graph_shared_beneficiary_degree_w90d (optional).
- MCR-05: (if POS/location present) provider_pos_mix_* features (domain extension) + peer stats.
- MCR-06: provider_duplicate_like_line_count_w90d, provider_duplicate_like_line_rate_w90d.
- MCR-07: graph_ordering_supplier_exclusivity_w180d, graph_shared_beneficiary_degree_w180d (as available).
- MCR-08: peer_group_size_w90d, peer_group_too_small_flag, peer composition drift metrics (from drift checks).
- MCR-09: policy_window_active_flag (use-case config) + provider_util_rate_* trend features.
- MCR-10: composite uses the contributing indicators’ feature sets; store contribution shares.
