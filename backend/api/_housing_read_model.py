"""Read-model builders for the Air Force housing dashboard endpoints.

Computes the executive overview and installation list/map payloads from the
knowledge base's ingested feed records (UMD authorizations, housing
inventory, resident experience, market and demographic snapshots) — the same
rows the scorecard evaluator consumes via
:class:`api.dependencies.RecordFeedSourceLoader`. Lives beside the other
gateway read models (``api._analytics_overview``) so the router stays a thin
HTTP layer.

Status banding is statutorily informed and documented on
:func:`derive_status_with_reasons` — the single threshold evaluation that
yields both the status band and the human-readable, data-bearing reasons the
frontend renders. Builders degrade to the safe-empty payloads when no
knowledge base with housing data exists yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from api.contracts import (
    HousingExecutiveKpiResponse,
    HousingInstallationMapPointResponse,
    HousingInstallationResponse,
    HousingInstallationsResponse,
    HousingOverviewResponse,
    HousingPortfolioSummaryResponse,
)
from api.dependencies import RecordFeedSourceLoader
from config.schema import DomainConfig
from knowledgebases.protocols import KnowledgeBaseRepository
from scorecards.evaluation import SourceRecord

__all__ = [
    "HousingStatus",
    "build_housing_installations",
    "build_housing_overview",
    "derive_status",
    "derive_status_with_reasons",
]

HousingStatus = Literal["ok", "watch", "critical", "unknown"]

# Statutorily informed banding thresholds (see derive_status).
_OCCUPANCY_CRITICAL = 0.75
_OCCUPANCY_WATCH = 0.85
_CONDITION_CRITICAL = 70.0
_CONDITION_WATCH = 80.0
_SATISFACTION_CRITICAL = 60.0
_SATISFACTION_WATCH = 75.0
_OVERDUE_RATIO_CRITICAL = 0.25
_OVERDUE_RATIO_WATCH = 0.10
_SUPPLY_RATIO_PASS = 1.0
_SUPPLY_RATIO_WATCH = 0.9


@dataclass
class _InstallationRollup:
    """Accumulated per-installation aggregates from the KB's feed records."""

    installation_id: str
    name: str | None = None
    majcom: str | None = None
    state: str | None = None
    branch: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    unaccompanied_authorized: float = 0.0
    accompanied_authorized: float = 0.0
    uh_available_units: float = 0.0
    mfh_available_units: float = 0.0
    utilization_weighted_sum: float = 0.0
    utilization_weight: float = 0.0
    condition_weighted_sum: float = 0.0
    condition_weight: float = 0.0
    satisfaction_values: list[float] = field(default_factory=list)
    open_work_orders: int = 0
    overdue_work_orders: int = 0
    has_inventory: bool = False
    has_uh_inventory: bool = False
    has_mfh_inventory: bool = False
    has_experience: bool = False

    @property
    def occupancy_rate(self) -> float | None:
        """Occupancy as utilization weighted by each asset's total unit count."""
        if self.utilization_weight <= 0:
            return None
        return self.utilization_weighted_sum / self.utilization_weight

    @property
    def condition_index(self) -> float | None:
        """Condition weighted by available units — the same weighting the
        scorecard's ``weighted_mean`` condition metrics use, so the dashboard
        and a scorecard run cannot disagree across the 80/60 grade lines.
        """
        if self.condition_weight <= 0:
            return None
        return self.condition_weighted_sum / self.condition_weight

    @property
    def satisfaction_score(self) -> float | None:
        if not self.satisfaction_values:
            return None
        return sum(self.satisfaction_values) / len(self.satisfaction_values)

    @property
    def overdue_ratio(self) -> float | None:
        if self.open_work_orders <= 0:
            return None
        return self.overdue_work_orders / self.open_work_orders

    @property
    def is_reporting(self) -> bool:
        """An installation reports when condition/experience data landed."""
        return self.has_inventory or self.has_experience


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _in_period(
    record: SourceRecord, period_start: date | None, period_end: date | None
) -> bool:
    """Keep records dated inside the requested window; undated records stay."""
    if record.observed_at is None:
        return True
    observed = record.observed_at.date()
    if period_start is not None and observed < period_start:
        return False
    if period_end is not None and observed > period_end:
        return False
    return True


def _rollup_installations(
    records: list[SourceRecord],
) -> dict[str, _InstallationRollup]:
    """Fold the KB's feed records into per-installation aggregates.

    Identity (name, MAJCOM, state, branch, coordinates) comes from the UMD
    authorization feed; supply/occupancy/condition from housing inventory;
    work orders and satisfaction from resident experience. Feeds that only
    contextualize (BAH, market, demographics) register the installation but
    contribute no roll-up fields.
    """
    rollups: dict[str, _InstallationRollup] = {}
    for record in records:
        installation_id = _as_str(record.values.get("installation_id"))
        if installation_id is None:
            continue
        rollup = rollups.setdefault(
            installation_id, _InstallationRollup(installation_id=installation_id)
        )
        if record.feed_name == "umd_authorizations":
            rollup.name = _as_str(record.values.get("installation_name")) or rollup.name
            rollup.majcom = _as_str(record.values.get("majcom")) or rollup.majcom
            rollup.state = _as_str(record.values.get("state")) or rollup.state
            rollup.branch = _as_str(record.values.get("branch")) or rollup.branch
            latitude = _as_float(record.values.get("latitude"))
            longitude = _as_float(record.values.get("longitude"))
            if latitude is not None and longitude is not None:
                rollup.latitude = latitude
                rollup.longitude = longitude
            rollup.unaccompanied_authorized += (
                _as_float(record.values.get("unaccompanied_authorized")) or 0.0
            )
            rollup.accompanied_authorized += (
                _as_float(record.values.get("accompanied_authorized")) or 0.0
            )
        elif record.feed_name == "housing_inventory":
            rollup.has_inventory = True
            available = _as_float(record.values.get("available_units")) or 0.0
            offline = _as_float(record.values.get("offline_units")) or 0.0
            category = _as_str(record.values.get("category"))
            if category == "UH":
                rollup.has_uh_inventory = True
                rollup.uh_available_units += available
            elif category == "MFH":
                rollup.has_mfh_inventory = True
                rollup.mfh_available_units += available
            utilization = _as_float(record.values.get("utilization_rate"))
            total_units = available + offline
            if utilization is not None and total_units > 0:
                rollup.utilization_weighted_sum += utilization * total_units
                rollup.utilization_weight += total_units
            condition = _as_float(record.values.get("condition_index"))
            if condition is not None and available > 0:
                rollup.condition_weighted_sum += condition * available
                rollup.condition_weight += available
        elif record.feed_name == "resident_experience":
            rollup.has_experience = True
            satisfaction = _as_float(record.values.get("satisfaction_score"))
            if satisfaction is not None:
                rollup.satisfaction_values.append(satisfaction)
            rollup.open_work_orders += int(
                _as_float(record.values.get("work_orders_open")) or 0.0
            )
            rollup.overdue_work_orders += int(
                _as_float(record.values.get("work_orders_overdue")) or 0.0
            )
    return rollups


_NO_DATA_REASON = "No inventory or resident-experience data reported"


def _fmt_toward_band(value: float, *, exceeds: bool) -> str:
    """Render a tripped metric to one decimal, rounding AWAY from the line.

    Plain ``:.1f`` rounding can display a near-boundary value as equal to the
    threshold it crossed (occupancy 74.96% would render "75.0% is below the
    75% ... trigger"). Below-threshold reasons floor and exceeds-threshold
    reasons ceil at one decimal, so the rendered value always sits on the
    same side of the line as the comparison that tripped. The ``round(..., 6)``
    first absorbs binary float noise on exact-decimal inputs (e.g. weighted
    0.70 occupancy arriving as 69.999999999999986%).
    """
    scaled = round(value * 10.0, 6)
    rounded = math.ceil(scaled) if exceeds else math.floor(scaled)
    return f"{rounded / 10.0:.1f}"


def derive_status_with_reasons(
    rollup: _InstallationRollup,
) -> tuple[HousingStatus, list[str]]:
    """Band an installation from its aggregates and explain every tripped band.

    Single source of truth for status derivation: the returned status is the
    worst band any metric tripped, and the reasons list carries one
    human-readable, data-bearing finding per tripped metric (its most severe
    band only — a metric below the critical line does not also emit its watch
    reason). ``ok`` installations return an empty list; ``unknown`` ones
    return the no-data reason.

    Thresholds trace to the congressionally mandated instruments the demo
    scorecards encode (see docs/research/housing-scorecard-mandates.md):

    - Occupancy below 75% is the 10 U.S.C. §2884(c)(2) financial-risk
      reporting trigger for privatized housing → critical; below 85% → watch.
    - Condition index below 70 mirrors this pack's alert threshold
      (``alerts.thresholds.housing_inventory_snapshot.condition_index``) →
      critical; below 80 → watch.
    - Resident satisfaction below 60 → critical; below 75 → watch (tenant
      satisfaction survey banding, FY2020 NDAA §3011 tenant-bill-of-rights
      oversight regime).
    - Overdue work orders above 25% of open orders → critical; above 10% →
      watch (maintenance responsiveness element of §2884(c) reporting).

    No inventory and no resident-experience data → unknown.
    """
    if not rollup.is_reporting:
        return "unknown", [_NO_DATA_REASON]

    critical = False
    watch = False
    reasons: list[str] = []

    occupancy = rollup.occupancy_rate
    if occupancy is not None:
        if occupancy < _OCCUPANCY_CRITICAL:
            critical = True
            reasons.append(
                f"Occupancy {_fmt_toward_band(occupancy * 100.0, exceeds=False)}% "
                f"is below the "
                f"{_OCCUPANCY_CRITICAL * 100.0:.0f}% financial-risk trigger "
                "(10 U.S.C. §2884(c)(2))"
            )
        elif occupancy < _OCCUPANCY_WATCH:
            watch = True
            reasons.append(
                f"Occupancy {_fmt_toward_band(occupancy * 100.0, exceeds=False)}% "
                f"is below the "
                f"{_OCCUPANCY_WATCH * 100.0:.0f}% watch threshold"
            )

    condition = rollup.condition_index
    if condition is not None:
        if condition < _CONDITION_CRITICAL:
            critical = True
            reasons.append(
                f"Condition index {_fmt_toward_band(condition, exceeds=False)} "
                "is below the critical "
                f"threshold of {_CONDITION_CRITICAL:.0f}"
            )
        elif condition < _CONDITION_WATCH:
            watch = True
            reasons.append(
                f"Condition index {_fmt_toward_band(condition, exceeds=False)} "
                "is below the watch "
                f"threshold of {_CONDITION_WATCH:.0f}"
            )

    satisfaction = rollup.satisfaction_score
    if satisfaction is not None:
        if satisfaction < _SATISFACTION_CRITICAL:
            critical = True
            reasons.append(
                f"Resident satisfaction "
                f"{_fmt_toward_band(satisfaction, exceeds=False)} is below the "
                f"critical threshold of {_SATISFACTION_CRITICAL:.0f}"
            )
        elif satisfaction < _SATISFACTION_WATCH:
            watch = True
            reasons.append(
                f"Resident satisfaction "
                f"{_fmt_toward_band(satisfaction, exceeds=False)} is below the "
                f"watch threshold of {_SATISFACTION_WATCH:.0f}"
            )

    overdue_ratio = rollup.overdue_ratio
    if overdue_ratio is not None:
        if overdue_ratio > _OVERDUE_RATIO_CRITICAL:
            critical = True
            reasons.append(
                f"Overdue work-order ratio "
                f"{_fmt_toward_band(overdue_ratio * 100.0, exceeds=True)}% "
                f"exceeds the {_OVERDUE_RATIO_CRITICAL * 100.0:.0f}% "
                "critical threshold"
            )
        elif overdue_ratio > _OVERDUE_RATIO_WATCH:
            watch = True
            reasons.append(
                f"Overdue work-order ratio "
                f"{_fmt_toward_band(overdue_ratio * 100.0, exceeds=True)}% "
                f"exceeds the {_OVERDUE_RATIO_WATCH * 100.0:.0f}% "
                "watch threshold"
            )

    if critical:
        return "critical", reasons
    if watch:
        return "watch", reasons
    return "ok", reasons


def derive_status(rollup: _InstallationRollup) -> HousingStatus:
    """Band an installation from its aggregates.

    Thin wrapper over :func:`derive_status_with_reasons` for callers that
    only need the band — both always agree because there is exactly one
    threshold evaluation.
    """
    status, _reasons = derive_status_with_reasons(rollup)
    return status


def _resolve_knowledge_base_id(
    knowledge_base_id: str | None,
    config: DomainConfig,
    repository: KnowledgeBaseRepository,
) -> str | None:
    """Return the KB to aggregate: explicit param, else newest KB of this domain.

    Preference order for the default: ``ready`` KBs first (fully built), then
    still-``active`` ones (records land before the pipeline marks the KB
    ready), newest ``created_at`` within each band. Legacy KBs without a
    domain stamp are excluded from the default — pass ``knowledge_base_id``
    explicitly to aggregate one of those.
    """
    if knowledge_base_id is not None:
        return knowledge_base_id
    knowledge_bases, _total = repository.list(limit=500, offset=0)
    candidates = [
        kb
        for kb in knowledge_bases
        if kb.domain == config.domain.name
        and kb.status in {"ready", "active"}
        and not kb.pending_cleanup
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda kb: (kb.status == "ready", kb.created_at))
    return best.id


def _load_rollups(
    *,
    knowledge_base_id: str | None,
    period_start: date | None,
    period_end: date | None,
    config: DomainConfig,
    loader: RecordFeedSourceLoader,
    kb_repository: KnowledgeBaseRepository,
) -> dict[str, _InstallationRollup]:
    resolved_kb = _resolve_knowledge_base_id(knowledge_base_id, config, kb_repository)
    if resolved_kb is None:
        return {}
    records = [
        record
        for record in loader.load_source_records(resolved_kb)
        if _in_period(record, period_start, period_end)
    ]
    return _rollup_installations(records)


def _kpi(
    *,
    kpi_id: str,
    label: str,
    value: float | None,
    unit: str,
    critical_below: float | None = None,
    watch_below: float | None = None,
    critical_above: float | None = None,
    watch_above: float | None = None,
) -> HousingExecutiveKpiResponse:
    """Build one KPI with banding on either a lower or an upper bound."""
    status: HousingStatus = "unknown"
    if value is not None:
        status = "ok"
        if watch_below is not None and value < watch_below:
            status = "watch"
        if critical_below is not None and value < critical_below:
            status = "critical"
        if watch_above is not None and value > watch_above:
            status = "watch"
        if critical_above is not None and value > critical_above:
            status = "critical"
    return HousingExecutiveKpiResponse(
        id=kpi_id,
        label=label,
        value=None if value is None else round(value, 3),
        unit=unit,
        status=status,
    )


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _portfolio_occupancy(rollups: dict[str, _InstallationRollup]) -> float | None:
    utilization_weight = sum(r.utilization_weight for r in rollups.values())
    utilization_weighted = sum(r.utilization_weighted_sum for r in rollups.values())
    if utilization_weight <= 0:
        return None
    return utilization_weighted / utilization_weight


def _build_executive_kpis(
    rollups: dict[str, _InstallationRollup],
) -> list[HousingExecutiveKpiResponse]:
    """Portfolio KPIs mirroring the scorecard instruments at enterprise scope."""
    occupancy = _portfolio_occupancy(rollups)
    condition_weight = sum(r.condition_weight for r in rollups.values())
    condition_weighted = sum(r.condition_weighted_sum for r in rollups.values())
    condition = (
        condition_weighted / condition_weight if condition_weight > 0 else None
    )
    satisfaction = _mean(
        [value for r in rollups.values() for value in r.satisfaction_values]
    )
    open_orders = sum(r.open_work_orders for r in rollups.values())
    overdue_orders = sum(r.overdue_work_orders for r in rollups.values())
    overdue_rate = (overdue_orders / open_orders) if open_orders > 0 else None
    # Supply ratios need BOTH sides observed: demand from UMD rows and at
    # least one inventory row in the category — zero recorded supply is a
    # real fail, but absent inventory data is unknown, not zero.
    uh_supply = sum(r.uh_available_units for r in rollups.values())
    uh_demand = sum(r.unaccompanied_authorized for r in rollups.values())
    mfh_supply = sum(r.mfh_available_units for r in rollups.values())
    mfh_demand = sum(r.accompanied_authorized for r in rollups.values())
    has_uh_inventory = any(r.has_uh_inventory for r in rollups.values())
    has_mfh_inventory = any(r.has_mfh_inventory for r in rollups.values())
    uh_ratio = (uh_supply / uh_demand) if uh_demand > 0 and has_uh_inventory else None
    mfh_ratio = (
        (mfh_supply / mfh_demand) if mfh_demand > 0 and has_mfh_inventory else None
    )
    critical_count = float(
        sum(1 for r in rollups.values() if derive_status(r) == "critical")
    )

    return [
        _kpi(
            kpi_id="portfolio_occupancy",
            label="Portfolio Occupancy",
            value=None if occupancy is None else occupancy * 100.0,
            unit="%",
            critical_below=_OCCUPANCY_CRITICAL * 100.0,
            watch_below=_OCCUPANCY_WATCH * 100.0,
        ),
        _kpi(
            kpi_id="average_condition_index",
            label="Average Condition Index",
            value=condition,
            unit="index",
            critical_below=_CONDITION_CRITICAL,
            watch_below=_CONDITION_WATCH,
        ),
        _kpi(
            kpi_id="resident_satisfaction",
            label="Resident Satisfaction",
            value=satisfaction,
            unit="score",
            critical_below=_SATISFACTION_CRITICAL,
            watch_below=_SATISFACTION_WATCH,
        ),
        _kpi(
            kpi_id="work_order_overdue_rate",
            label="Work Orders Overdue",
            value=None if overdue_rate is None else overdue_rate * 100.0,
            unit="%",
            critical_above=_OVERDUE_RATIO_CRITICAL * 100.0,
            watch_above=_OVERDUE_RATIO_WATCH * 100.0,
        ),
        _kpi(
            kpi_id="uh_supply_ratio",
            label="UH Supply Ratio",
            value=uh_ratio,
            unit="ratio",
            critical_below=_SUPPLY_RATIO_WATCH,
            watch_below=_SUPPLY_RATIO_PASS,
        ),
        _kpi(
            kpi_id="mfh_supply_ratio",
            label="MFH Supply Ratio",
            value=mfh_ratio,
            unit="ratio",
            critical_below=_SUPPLY_RATIO_WATCH,
            watch_below=_SUPPLY_RATIO_PASS,
        ),
        _kpi(
            kpi_id="installations_critical",
            label="Installations Critical",
            value=critical_count,
            unit="count",
            critical_above=0.0,
        ),
    ]


def build_housing_overview(
    *,
    knowledge_base_id: str | None,
    period_start: date | None,
    period_end: date | None,
    config: DomainConfig,
    loader: RecordFeedSourceLoader,
    kb_repository: KnowledgeBaseRepository,
) -> HousingOverviewResponse:
    """Compute the executive housing KPI payload from ingested records."""
    rollups = _load_rollups(
        knowledge_base_id=knowledge_base_id,
        period_start=period_start,
        period_end=period_end,
        config=config,
        loader=loader,
        kb_repository=kb_repository,
    )
    if not rollups:
        return HousingOverviewResponse(
            period_start=period_start,
            period_end=period_end,
            portfolio_summary=HousingPortfolioSummaryResponse(),
            executive_kpis=[],
        )

    occupancy = _portfolio_occupancy(rollups)
    satisfaction = _mean(
        [value for r in rollups.values() for value in r.satisfaction_values]
    )
    summary = HousingPortfolioSummaryResponse(
        total_installations=len(rollups),
        installations_reporting=sum(1 for r in rollups.values() if r.is_reporting),
        open_work_orders=sum(r.open_work_orders for r in rollups.values()),
        overdue_work_orders=sum(r.overdue_work_orders for r in rollups.values()),
        occupancy_rate=None if occupancy is None else round(occupancy, 4),
        resident_satisfaction=None if satisfaction is None else round(satisfaction, 2),
    )
    return HousingOverviewResponse(
        period_start=period_start,
        period_end=period_end,
        portfolio_summary=summary,
        executive_kpis=_build_executive_kpis(rollups),
    )


def build_housing_installations(
    *,
    knowledge_base_id: str | None,
    period_start: date | None,
    period_end: date | None,
    config: DomainConfig,
    loader: RecordFeedSourceLoader,
    kb_repository: KnowledgeBaseRepository,
) -> HousingInstallationsResponse:
    """Compute the installation list and map payload from ingested records.

    Installations without resolvable coordinates appear in ``items`` but not
    in ``map_points`` — the frontend surfaces them as location-pending rather
    than silently dropping them.

    ``open_work_orders_rank`` is the 1-based competition rank by open work
    orders (1 = most) among reporting installations; ties share the smaller
    rank, and non-reporting installations get ``None`` rather than competing
    with zeros they never reported.
    """
    rollups = _load_rollups(
        knowledge_base_id=knowledge_base_id,
        period_start=period_start,
        period_end=period_end,
        config=config,
        loader=loader,
        kb_repository=kb_repository,
    )
    ordered = sorted(
        rollups.values(), key=lambda r: (r.name or r.installation_id).lower()
    )
    derived = {
        rollup.installation_id: derive_status_with_reasons(rollup)
        for rollup in ordered
    }
    reporting_counts = [r.open_work_orders for r in ordered if r.is_reporting]
    items = [
        HousingInstallationResponse(
            installation_id=rollup.installation_id,
            name=rollup.name or rollup.installation_id,
            majcom=rollup.majcom,
            state=rollup.state,
            branch=rollup.branch,
            status=derived[rollup.installation_id][0],
            status_reasons=derived[rollup.installation_id][1],
            open_work_orders=rollup.open_work_orders,
            open_work_orders_rank=(
                1
                + sum(
                    1 for count in reporting_counts if count > rollup.open_work_orders
                )
                if rollup.is_reporting
                else None
            ),
            occupancy_rate=(
                None
                if rollup.occupancy_rate is None
                else round(rollup.occupancy_rate, 4)
            ),
        )
        for rollup in ordered
    ]
    map_points = [
        HousingInstallationMapPointResponse(
            installation_id=rollup.installation_id,
            name=rollup.name or rollup.installation_id,
            latitude=rollup.latitude,
            longitude=rollup.longitude,
            branch=rollup.branch,
            status=derived[rollup.installation_id][0],
        )
        for rollup in ordered
        if rollup.latitude is not None and rollup.longitude is not None
    ]
    return HousingInstallationsResponse(
        period_start=period_start,
        period_end=period_end,
        total=len(items),
        items=items,
        map_points=map_points,
    )
