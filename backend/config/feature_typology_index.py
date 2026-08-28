"""Resolve risk-factor names to the fraud typologies they evidence.

The feature catalog keys its entries by feature id (``weekly_provider_billing_zscore``),
but a scored ``RiskFactor`` is named after the *signal* that produced it — the
peer metric name (``weekly_provider_billing``), the derived-signal name, or the
``timeseries_anomaly:<spec>`` name the timeseries stage writes. Indexing by
feature id alone therefore misses every lookup and leaves ``top_typology_ids``
empty for every entity.

This builds one index keyed by every name a factor can plausibly arrive under,
so both the live projection path and the history-rebuild path resolve the same
way.
"""

from __future__ import annotations

from config.schema import DomainConfig

__all__ = ["build_feature_typology_index"]

# How a catalog ``source_ref`` maps onto the ``factor_name`` that reaches the
# projection. Each entry drops the source_ref's leading namespace segment and
# applies the prefix the producing stage stamps on the metric name.
_SOURCE_NAME_PREFIXES: dict[str, str] = {
    "peer_metric": "",
    "derived_signal": "",
    "timeseries_metric": "timeseries_anomaly:",
}


def _signal_name(source_type: str, source_ref: str) -> str | None:
    """Return the runtime factor name a catalog source_ref corresponds to."""
    prefix = _SOURCE_NAME_PREFIXES.get(source_type)
    if prefix is None:
        return None
    _, separator, remainder = source_ref.partition(".")
    if not separator or not remainder:
        return None
    return f"{prefix}{remainder}"


def build_feature_typology_index(config: DomainConfig) -> dict[str, list[str]]:
    """Map every resolvable factor name to the typology ids it evidences.

    Keys include each feature's own catalog id (callers that already hold one
    keep working) plus the signal names derived from its source mappings.
    """
    index: dict[str, list[str]] = {}
    for feature in config.feature_catalog.features:
        typology_ids = list(feature.typology_ids)
        if not typology_ids:
            continue
        names = {feature.id}
        for mapping in feature.source_mappings:
            name = _signal_name(mapping.source_type, mapping.source_ref)
            if name is not None:
                names.add(name)
        for name in names:
            merged = index.setdefault(name, [])
            for typology_id in typology_ids:
                if typology_id not in merged:
                    merged.append(typology_id)
    return index
