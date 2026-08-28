"""The feature -> typology index used to label risk projections.

Risk factors are named after the *signal* that produced them — a peer metric
name like ``weekly_provider_billing``, or ``timeseries_anomaly:<spec>`` — while
the feature catalog keys its entries by feature id (``weekly_provider_billing_zscore``).
An index built from feature ids alone therefore misses every lookup, and
``top_typology_ids`` comes back empty for every entity, which in turn makes
``GET /analytics/{kb}/risk-queue?typology_id=...`` return nothing for every
typology in every shipped pack.
"""

from __future__ import annotations

import pathlib

import pytest

from config.feature_typology_index import build_feature_typology_index
from config.loader import load_config
from config.schema import FeatureDefinitionConfig

_DEFAULTS = pathlib.Path(__file__).resolve().parents[2] / "config" / "defaults"


def test_a_peer_metric_factor_name_resolves_to_its_typologies() -> None:
    index = build_feature_typology_index(load_config(_DEFAULTS / "medicare_fraud.yaml"))

    assert index.get("weekly_provider_billing") == ["billing_spike", "peer_outlier"]


def test_a_timeseries_factor_name_resolves_with_its_runtime_prefix() -> None:
    """``run_timeseries_stage`` names these ``timeseries_anomaly:<spec>``."""
    index = build_feature_typology_index(load_config(_DEFAULTS / "medicare_fraud.yaml"))

    assert index.get("timeseries_anomaly:service_date_burstiness") == [
        "billing_spike",
        "geographic_anomaly",
    ]


def test_a_derived_signal_factor_name_resolves_to_its_typologies() -> None:
    index = build_feature_typology_index(load_config(_DEFAULTS / "medicare_fraud.yaml"))

    assert index.get("geographic_state_outlier") == ["geographic_anomaly"]


def test_the_feature_id_itself_still_resolves() -> None:
    """Callers that already hold a catalog id must keep working."""
    index = build_feature_typology_index(load_config(_DEFAULTS / "medicare_fraud.yaml"))

    assert index.get("weekly_provider_billing_zscore") == [
        "billing_spike",
        "peer_outlier",
    ]


def test_the_cms_desynpuf_pack_resolves_its_peer_metric_names() -> None:
    """The DESYNPUF pack renames its metrics, so it needs its own assertions."""
    index = build_feature_typology_index(
        load_config(_DEFAULTS / "medicare_fraud_cms_desynpuf.yaml")
    )

    assert index.get("weekly_carrier_billing") == ["billing_spike", "peer_outlier"]
    assert index.get("monthly_inpatient_billing") == [
        "dmepos_overutilization",
        "billing_spike",
    ]


def test_the_cms_desynpuf_pack_resolves_its_timeseries_name() -> None:
    index = build_feature_typology_index(
        load_config(_DEFAULTS / "medicare_fraud_cms_desynpuf.yaml")
    )

    assert index.get("timeseries_anomaly:weekly_carrier_billing_self") == [
        "billing_spike",
        "geographic_anomaly",
    ]


def test_the_cms_desynpuf_pack_resolves_a_feature_id_it_shares_with_its_signal() -> None:
    """``geographic_state_outlier`` is both a catalog id and a signal name."""
    index = build_feature_typology_index(
        load_config(_DEFAULTS / "medicare_fraud_cms_desynpuf.yaml")
    )

    assert index.get("geographic_state_outlier") == ["geographic_anomaly"]
    assert index.get("weekly_provider_billing_zscore") == [
        "billing_spike",
        "peer_outlier",
    ]


# The prefix each producing stage stamps on the metric name, derived here
# independently of ``config.feature_typology_index`` so this file is an oracle
# for the mapping rather than a restatement of it. ``None`` means the source
# type produces no runtime signal name at all (the factor arrives under the
# feature id).
_SIGNAL_PREFIXES: dict[str, str] = {
    "peer_metric": "",
    "derived_signal": "",
    "timeseries_metric": "timeseries_anomaly:",
}


def _expected_signal_names(feature: FeatureDefinitionConfig) -> set[str]:
    """Names a scored factor for ``feature`` can arrive under, minus its id.

    The feature id is excluded deliberately: it is in the index unconditionally,
    so any reachability claim that counts it is true no matter what the
    source-mapping derivation does — the exact tautology that let the original
    defect ship behind a green test.
    """
    names: set[str] = set()
    for mapping in feature.source_mappings:
        prefix = _SIGNAL_PREFIXES.get(mapping.source_type)
        if prefix is None:
            continue
        _, separator, remainder = mapping.source_ref.partition(".")
        if not separator or not remainder:
            continue
        names.add(f"{prefix}{remainder}")
    return names - {feature.id}


@pytest.mark.parametrize(
    "pack",
    ["medicare_fraud.yaml", "medicare_fraud_cms_desynpuf.yaml", "food_supply_chain.yaml"],
)
def test_every_signal_named_feature_is_reachable_under_its_signal_name(
    pack: str,
) -> None:
    """A typology nothing can resolve to is a filter that always returns zero.

    Reachability is asserted through the *derived* signal names only. Counting
    the feature ids as well cannot fail: ``build_feature_typology_index``
    always keys every feature by its own id, so the assertion held even with
    signal-name derivation switched off entirely.
    """
    config = load_config(_DEFAULTS / pack)
    features = [
        feature
        for feature in config.feature_catalog.features
        if feature.typology_ids and _expected_signal_names(feature)
    ]
    if not features:
        pytest.skip(f"{pack} declares no signal-derived feature")

    index = build_feature_typology_index(config)
    unreachable = {
        signal_name: sorted(set(feature.typology_ids) - set(index.get(signal_name, [])))
        for feature in features
        for signal_name in sorted(_expected_signal_names(feature))
        if not set(feature.typology_ids) <= set(index.get(signal_name, []))
    }

    assert not unreachable, (
        "these typologies are unreachable from the signal name a scored factor "
        f"actually carries, so the risk-queue filter returns nothing: {unreachable}"
    )


@pytest.mark.parametrize(
    "pack",
    ["medicare_fraud.yaml", "medicare_fraud_cms_desynpuf.yaml"],
)
def test_the_index_is_keyed_by_more_than_the_feature_ids(pack: str) -> None:
    """The index must carry keys the feature ids alone would never produce."""
    config = load_config(_DEFAULTS / pack)
    feature_ids = {feature.id for feature in config.feature_catalog.features}

    signal_keys = set(build_feature_typology_index(config)) - feature_ids

    assert signal_keys, (
        f"{pack} indexes nothing but its feature ids, so every factor named "
        "after its signal misses the lookup"
    )
