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


@pytest.mark.parametrize(
    "pack",
    ["medicare_fraud.yaml", "medicare_fraud_cms_desynpuf.yaml", "food_supply_chain.yaml"],
)
def test_every_declared_typology_id_is_reachable_from_some_signal_name(
    pack: str,
) -> None:
    """A typology nothing can resolve to is a filter that always returns zero."""
    config = load_config(_DEFAULTS / pack)
    catalog_typologies = {
        typology_id
        for feature in config.feature_catalog.features
        for typology_id in feature.typology_ids
    }
    if not catalog_typologies:
        pytest.skip(f"{pack} ships an empty feature catalog")

    reachable = {
        typology_id
        for typology_ids in build_feature_typology_index(config).values()
        for typology_id in typology_ids
    }

    assert catalog_typologies <= reachable
