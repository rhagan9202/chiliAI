"""Tests for the Air Force housing API router."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    get_domain_config,
    get_knowledge_base_repository,
    get_source_record_loader,
)
from api.routers.housing import router
from config.schema import (
    AlertsConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    IngestionSourceConfig,
)
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from scorecards.evaluation import SourceRecord, SourceValue
from shared.types import KnowledgeBase

_DOMAIN_NAME = "department_air_force_housing"
_OBSERVED = datetime(2026, 6, 30, tzinfo=UTC)


class StubRecordLoader:
    """Serves a fixed record set and captures requested KB ids."""

    def __init__(self, records: list[SourceRecord] | None = None) -> None:
        self.records = records or []
        self.requested_kb_ids: list[str] = []

    def load_source_records(self, knowledge_base_id: str) -> list[SourceRecord]:
        self.requested_kb_ids.append(knowledge_base_id)
        return list(self.records)


def _config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(
            name=_DOMAIN_NAME,
            display_name="DAF Housing",
            description="Housing router test domain.",
        ),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(
            sources=[IngestionSourceConfig(type="file_upload", formats=["csv"])]
        ),
        alerts=AlertsConfig(thresholds={}),
    )


def _kb(
    kb_id: str,
    *,
    domain: str | None = _DOMAIN_NAME,
    status: str = "ready",
    created: datetime = datetime(2026, 6, 1, tzinfo=UTC),
) -> KnowledgeBase:
    return KnowledgeBase.model_validate(
        {
            "id": kb_id,
            "name": kb_id,
            "description": "test",
            "status": status,
            "created_at": created,
            "domain": domain,
        }
    )


def _record(
    feed_name: str, record_id: str, values: dict[str, SourceValue]
) -> SourceRecord:
    return SourceRecord(
        feed_name=feed_name,
        record_id=record_id,
        values=values,
        observed_at=_OBSERVED,
    )


def _installation_records() -> list[SourceRecord]:
    """Four installations spanning ok / watch / critical / unknown statuses."""
    return [
        # eglin_afb — healthy across the board → ok.
        _record(
            "umd_authorizations",
            "umd-eglin",
            {
                "installation_id": "eglin_afb",
                "installation_name": "Eglin AFB",
                "majcom": "AFMC",
                "state": "FL",
                "branch": "USAF",
                "latitude": 30.4832,
                "longitude": -86.5254,
                "unaccompanied_authorized": 1000,
                "accompanied_authorized": 900,
            },
        ),
        _record(
            "housing_inventory",
            "inv-eglin-uh",
            {
                "installation_id": "eglin_afb",
                "category": "UH",
                "available_units": 1100,
                "offline_units": 40,
                "utilization_rate": 0.92,
                "condition_index": 88.0,
            },
        ),
        _record(
            "resident_experience",
            "rex-eglin-uh",
            {
                "installation_id": "eglin_afb",
                "category": "UH",
                "satisfaction_score": 82.0,
                "work_orders_open": 30,
                "work_orders_overdue": 1,
            },
        ),
        # edwards_afb — watch band (occupancy 0.80, condition 74, satisfaction 68).
        _record(
            "umd_authorizations",
            "umd-edwards",
            {
                "installation_id": "edwards_afb",
                "installation_name": "Edwards AFB",
                "majcom": "AFMC",
                "state": "CA",
                "branch": "USAF",
                "latitude": 34.9054,
                "longitude": -117.8837,
                "unaccompanied_authorized": 1200,
                "accompanied_authorized": 800,
            },
        ),
        _record(
            "housing_inventory",
            "inv-edwards-uh",
            {
                "installation_id": "edwards_afb",
                "category": "UH",
                "available_units": 1150,
                "offline_units": 50,
                "utilization_rate": 0.80,
                "condition_index": 74.0,
            },
        ),
        _record(
            "resident_experience",
            "rex-edwards-uh",
            {
                "installation_id": "edwards_afb",
                "category": "UH",
                "satisfaction_score": 68.0,
                "work_orders_open": 40,
                "work_orders_overdue": 6,
            },
        ),
        # patrick_sfb — critical (occupancy 0.70, condition 65) and NO coordinates.
        _record(
            "umd_authorizations",
            "umd-patrick",
            {
                "installation_id": "patrick_sfb",
                "installation_name": "Patrick SFB",
                "majcom": "SpOC",
                "state": "FL",
                "branch": "USSF",
                "unaccompanied_authorized": 500,
                "accompanied_authorized": 450,
            },
        ),
        _record(
            "housing_inventory",
            "inv-patrick-uh",
            {
                "installation_id": "patrick_sfb",
                "category": "UH",
                "available_units": 400,
                "offline_units": 60,
                "utilization_rate": 0.70,
                "condition_index": 65.0,
            },
        ),
        _record(
            "resident_experience",
            "rex-patrick-uh",
            {
                "installation_id": "patrick_sfb",
                "category": "UH",
                "satisfaction_score": 50.0,
                "work_orders_open": 50,
                "work_orders_overdue": 20,
            },
        ),
        # context_only_afb — only market context, no roll-up feeds → unknown.
        _record(
            "market_availability",
            "market-context",
            {
                "installation_id": "context_only_afb",
                "available_rentals": 200,
                "affordability_index": 75.0,
            },
        ),
    ]


def _client(
    *,
    loader: StubRecordLoader | None = None,
    knowledge_bases: list[KnowledgeBase] | None = None,
) -> tuple[TestClient, StubRecordLoader]:
    app = FastAPI()
    app.include_router(router)
    stub_loader = loader or StubRecordLoader(_installation_records())
    repository = InMemoryKnowledgeBaseRepository()
    for kb in knowledge_bases if knowledge_bases is not None else [_kb("kb-housing")]:
        repository.create(kb)
    app.dependency_overrides[get_domain_config] = _config
    app.dependency_overrides[get_source_record_loader] = lambda: stub_loader
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    return TestClient(app), stub_loader


def test_overview_returns_safe_empty_model_without_a_domain_kb() -> None:
    client, loader = _client(knowledge_bases=[])

    response = client.get(
        "/housing/overview",
        params={"period_start": "2026-06-01", "period_end": "2026-06-30"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "portfolio_summary": {
            "total_installations": 0,
            "installations_reporting": 0,
            "open_work_orders": 0,
            "overdue_work_orders": 0,
            "occupancy_rate": None,
            "resident_satisfaction": None,
        },
        "executive_kpis": [],
    }
    assert loader.requested_kb_ids == []


def test_overview_ignores_kbs_from_other_domains() -> None:
    client, loader = _client(knowledge_bases=[_kb("kb-medicare", domain="medicare")])

    response = client.get("/housing/overview")

    assert response.status_code == 200
    assert response.json()["executive_kpis"] == []
    assert loader.requested_kb_ids == []


def test_overview_computes_portfolio_summary_from_records() -> None:
    client, loader = _client()

    response = client.get("/housing/overview")

    assert response.status_code == 200
    body = response.json()
    summary = body["portfolio_summary"]
    assert summary["total_installations"] == 4
    assert summary["installations_reporting"] == 3
    assert summary["open_work_orders"] == 30 + 40 + 50
    assert summary["overdue_work_orders"] == 1 + 6 + 20
    # Weighted occupancy: (0.92*1140 + 0.80*1200 + 0.70*460) / 2800.
    expected_occupancy = (0.92 * 1140 + 0.80 * 1200 + 0.70 * 460) / 2800
    assert summary["occupancy_rate"] == round(expected_occupancy, 4)
    assert summary["resident_satisfaction"] == round((82.0 + 68.0 + 50.0) / 3, 2)
    assert loader.requested_kb_ids == ["kb-housing"]


def test_overview_kpis_are_graded_from_aggregates() -> None:
    client, _loader = _client()

    body = client.get("/housing/overview").json()

    kpis = {kpi["id"]: kpi for kpi in body["executive_kpis"]}
    assert kpis["portfolio_occupancy"]["unit"] == "%"
    assert kpis["portfolio_occupancy"]["status"] == "watch"  # 82.9% < 85%
    # Condition is weighted by available units (scorecard weighted_mean parity).
    assert kpis["average_condition_index"]["value"] == round(
        (88.0 * 1100 + 74.0 * 1150 + 65.0 * 400) / (1100 + 1150 + 400), 3
    )
    assert kpis["resident_satisfaction"]["status"] == "watch"
    assert kpis["uh_supply_ratio"]["value"] == round((1100 + 1150 + 400) / 2700, 3)
    assert kpis["installations_critical"]["value"] == 1.0
    assert kpis["installations_critical"]["status"] == "critical"
    # MFH inventory never landed → unknown, not fabricated.
    assert kpis["mfh_supply_ratio"]["value"] is None
    assert kpis["mfh_supply_ratio"]["status"] == "unknown"


def test_condition_index_is_unit_weighted_like_the_scorecard() -> None:
    """A big healthy asset must outweigh a small distressed one (weighted_mean).

    Unweighted averaging would grade this installation 75 (watch side of the
    80 line) while the scorecard's unit-weighted metric grades 87 — the
    dashboard must use the same weighting so they cannot disagree.
    """
    records = [
        _record(
            "housing_inventory",
            "inv-mixed-uh-large",
            {
                "installation_id": "mixed_afb",
                "category": "UH",
                "available_units": 900,
                "offline_units": 0,
                "utilization_rate": 0.92,
                "condition_index": 90.0,
            },
        ),
        _record(
            "housing_inventory",
            "inv-mixed-uh-small",
            {
                "installation_id": "mixed_afb",
                "category": "UH",
                "available_units": 100,
                "offline_units": 0,
                "utilization_rate": 0.92,
                "condition_index": 60.0,
            },
        ),
    ]
    client, _loader = _client(loader=StubRecordLoader(records))

    body = client.get("/housing/overview").json()

    kpis = {kpi["id"]: kpi for kpi in body["executive_kpis"]}
    weighted = (90.0 * 900 + 60.0 * 100) / 1000
    assert kpis["average_condition_index"]["value"] == round(weighted, 3)
    assert kpis["average_condition_index"]["status"] == "ok"  # 87 >= 80

    items = client.get("/housing/installations").json()["items"]
    # Weighted 87 keeps the installation on the healthy side of the 80 line.
    assert items[0]["status"] == "ok"


def test_overview_period_filter_excludes_out_of_window_records() -> None:
    client, _loader = _client()

    response = client.get(
        "/housing/overview",
        params={"period_start": "2026-01-01", "period_end": "2026-03-31"},
    )

    body = response.json()
    assert body["portfolio_summary"]["total_installations"] == 0
    assert body["executive_kpis"] == []


def test_installations_lists_every_installation_with_derived_status() -> None:
    client, _loader = _client()

    response = client.get("/housing/installations")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    by_id = {item["installation_id"]: item for item in body["items"]}
    assert set(by_id) == {
        "eglin_afb",
        "edwards_afb",
        "patrick_sfb",
        "context_only_afb",
    }

    assert by_id["eglin_afb"]["status"] == "ok"
    assert by_id["eglin_afb"]["branch"] == "USAF"
    assert by_id["eglin_afb"]["majcom"] == "AFMC"
    assert by_id["eglin_afb"]["occupancy_rate"] == 0.92
    assert by_id["eglin_afb"]["open_work_orders"] == 30

    assert by_id["edwards_afb"]["status"] == "watch"
    assert by_id["patrick_sfb"]["status"] == "critical"
    assert by_id["patrick_sfb"]["branch"] == "USSF"

    # Context-only installation stays visible with an unknown status and
    # falls back to its id for the display name.
    assert by_id["context_only_afb"]["status"] == "unknown"
    assert by_id["context_only_afb"]["name"] == "context_only_afb"


def test_installations_map_points_require_coordinates() -> None:
    client, _loader = _client()

    body = client.get("/housing/installations").json()

    map_ids = {point["installation_id"] for point in body["map_points"]}
    # patrick_sfb (no coordinates) and context_only_afb (no umd row) are in
    # items but not on the map — surfaced as location-pending, never dropped.
    assert map_ids == {"eglin_afb", "edwards_afb"}
    eglin_point = next(
        point for point in body["map_points"] if point["installation_id"] == "eglin_afb"
    )
    assert eglin_point["latitude"] == 30.4832
    assert eglin_point["longitude"] == -86.5254
    assert eglin_point["branch"] == "USAF"
    assert eglin_point["status"] == "ok"


def test_installation_fields_recompute_every_overview_aggregate() -> None:
    """Semantic contract for filter-driven aggregate cards.

    Folding every installation's exposed inputs with the documented formulas
    must reproduce the ``/housing/overview`` portfolio summary and executive
    KPI values exactly — the frontend implements these formulas over any
    filtered subset:

    - occupancy = sum(occupancy_rate * occupancy_unit_weight)
      / sum(occupancy_unit_weight) over non-null weights
    - condition = sum(condition_index * condition_unit_weight)
      / sum(condition_unit_weight) over non-null weights
    - satisfaction = sum(resident_satisfaction * satisfaction_survey_count)
      / sum(satisfaction_survey_count) — identical to the overview's flat
      mean over every survey value
    - overdue rate = sum(overdue_work_orders) / sum(open_work_orders),
      unknown when the open sum is 0
    - supply ratio = sum(non-null <cat>_available_units)
      / sum(<cat>_authorized_units), unknown unless the authorized sum is
      positive and at least one installation reported that category
    - counts from status: total = row count, reporting = status != unknown,
      critical = status == critical
    """
    client, _loader = _client()

    overview = client.get("/housing/overview").json()
    items = client.get("/housing/installations").json()["items"]
    summary = overview["portfolio_summary"]
    kpis = {kpi["id"]: kpi["value"] for kpi in overview["executive_kpis"]}

    assert summary["total_installations"] == len(items)
    assert summary["installations_reporting"] == sum(
        1 for item in items if item["status"] != "unknown"
    )
    assert kpis["installations_critical"] == float(
        sum(1 for item in items if item["status"] == "critical")
    )

    open_orders = sum(item["open_work_orders"] for item in items)
    overdue_orders = sum(item["overdue_work_orders"] for item in items)
    assert summary["open_work_orders"] == open_orders
    assert summary["overdue_work_orders"] == overdue_orders
    assert open_orders > 0
    assert kpis["work_order_overdue_rate"] == round(
        overdue_orders / open_orders * 100.0, 3
    )

    occupancy_pairs = [
        (item["occupancy_rate"], item["occupancy_unit_weight"])
        for item in items
        if item["occupancy_unit_weight"] is not None
    ]
    occupancy = sum(rate * weight for rate, weight in occupancy_pairs) / sum(
        weight for _rate, weight in occupancy_pairs
    )
    assert summary["occupancy_rate"] == round(occupancy, 4)
    assert kpis["portfolio_occupancy"] == round(occupancy * 100.0, 3)

    condition_pairs = [
        (item["condition_index"], item["condition_unit_weight"])
        for item in items
        if item["condition_unit_weight"] is not None
    ]
    condition = sum(value * weight for value, weight in condition_pairs) / sum(
        weight for _value, weight in condition_pairs
    )
    assert kpis["average_condition_index"] == round(condition, 3)

    survey_count = sum(item["satisfaction_survey_count"] for item in items)
    assert survey_count > 0
    satisfaction = (
        sum(
            item["resident_satisfaction"] * item["satisfaction_survey_count"]
            for item in items
            if item["satisfaction_survey_count"] > 0
        )
        / survey_count
    )
    assert summary["resident_satisfaction"] == round(satisfaction, 2)
    assert kpis["resident_satisfaction"] == round(satisfaction, 3)

    uh_available = [
        item["uh_available_units"]
        for item in items
        if item["uh_available_units"] is not None
    ]
    uh_authorized = sum(item["uh_authorized_units"] for item in items)
    assert uh_available and uh_authorized > 0
    assert kpis["uh_supply_ratio"] == round(sum(uh_available) / uh_authorized, 3)

    # No MFH inventory landed anywhere: every mfh_available_units is None, so
    # the recomputation yields unknown even though authorizations exist —
    # exactly what the overview reports.
    assert all(item["mfh_available_units"] is None for item in items)
    assert sum(item["mfh_authorized_units"] for item in items) > 0
    assert kpis["mfh_supply_ratio"] is None


def test_installation_aggregate_inputs_are_null_where_unreported() -> None:
    """Aggregate inputs are null (or zero-count) when the feed never landed."""
    client, _loader = _client()

    by_id = {
        item["installation_id"]: item
        for item in client.get("/housing/installations").json()["items"]
    }

    eglin = by_id["eglin_afb"]
    assert eglin["occupancy_unit_weight"] == 1140  # available 1100 + offline 40
    assert eglin["condition_index"] == 88.0
    assert eglin["condition_unit_weight"] == 1100  # available units only
    assert eglin["resident_satisfaction"] == 82.0
    assert eglin["satisfaction_survey_count"] == 1
    assert eglin["overdue_work_orders"] == 1
    assert eglin["uh_available_units"] == 1100
    assert eglin["uh_authorized_units"] == 1000
    assert eglin["mfh_available_units"] is None  # no MFH inventory reported
    assert eglin["mfh_authorized_units"] == 900

    context_only = by_id["context_only_afb"]
    assert context_only["occupancy_rate"] is None
    assert context_only["occupancy_unit_weight"] is None
    assert context_only["condition_index"] is None
    assert context_only["condition_unit_weight"] is None
    assert context_only["resident_satisfaction"] is None
    assert context_only["satisfaction_survey_count"] == 0
    assert context_only["overdue_work_orders"] == 0
    assert context_only["uh_available_units"] is None
    assert context_only["uh_authorized_units"] == 0.0
    assert context_only["mfh_available_units"] is None
    assert context_only["mfh_authorized_units"] == 0.0


def _mixed_feed_records() -> list[SourceRecord]:
    """Two installations exercising every weighting subtlety at once:
    offline units (occupancy weight differs from condition weight), multiple
    inventory rows and surveys per installation, MFH inventory on both sides
    of the ratio, and a UH category reported by only one installation.
    """
    return [
        _record(
            "umd_authorizations",
            "umd-alpha",
            {
                "installation_id": "alpha_afb",
                "installation_name": "Alpha AFB",
                "unaccompanied_authorized": 700,
                "accompanied_authorized": 600,
            },
        ),
        _record(
            "housing_inventory",
            "inv-alpha-uh",
            {
                "installation_id": "alpha_afb",
                "category": "UH",
                "available_units": 500,
                "offline_units": 100,
                "utilization_rate": 0.9,
                "condition_index": 85.0,
            },
        ),
        _record(
            "housing_inventory",
            "inv-alpha-mfh",
            {
                "installation_id": "alpha_afb",
                "category": "MFH",
                "available_units": 500,
                "offline_units": 0,
                "utilization_rate": 0.79,
                "condition_index": 90.0,
            },
        ),
        _record(
            "resident_experience",
            "rex-alpha-1",
            {
                "installation_id": "alpha_afb",
                "satisfaction_score": 80.0,
                "work_orders_open": 10,
                "work_orders_overdue": 2,
            },
        ),
        _record(
            "resident_experience",
            "rex-alpha-2",
            {
                "installation_id": "alpha_afb",
                "satisfaction_score": 70.0,
                "work_orders_open": 30,
                "work_orders_overdue": 3,
            },
        ),
        _record(
            "umd_authorizations",
            "umd-bravo",
            {
                "installation_id": "bravo_afb",
                "installation_name": "Bravo AFB",
                "unaccompanied_authorized": 400,
                "accompanied_authorized": 400,
            },
        ),
        _record(
            "housing_inventory",
            "inv-bravo-mfh",
            {
                "installation_id": "bravo_afb",
                "category": "MFH",
                "available_units": 300,
                "offline_units": 0,
                "utilization_rate": 0.7,
                "condition_index": 60.0,
            },
        ),
        _record(
            "resident_experience",
            "rex-bravo",
            {
                "installation_id": "bravo_afb",
                "satisfaction_score": 60.0,
                "work_orders_open": 20,
                "work_orders_overdue": 5,
            },
        ),
    ]


def test_recompute_contract_pins_weights_on_mixed_feeds() -> None:
    """The exposed weights are the overview's actual weights.

    Occupancy weighs by total units (available + offline) of
    utilization-reporting rows; condition weighs by available units of
    condition-reporting rows; portfolio satisfaction weighs each
    installation's mean by its survey count (equal to the overview's flat
    mean over all surveys). Substituting available units for the occupancy
    weight in this fixture would recompute a different portfolio value —
    the wrong weight fails loudly here.
    """
    client, _loader = _client(loader=StubRecordLoader(_mixed_feed_records()))

    overview = client.get("/housing/overview").json()
    items = client.get("/housing/installations").json()["items"]
    by_id = {item["installation_id"]: item for item in items}
    summary = overview["portfolio_summary"]
    kpis = {kpi["id"]: kpi["value"] for kpi in overview["executive_kpis"]}

    alpha = by_id["alpha_afb"]
    # Occupancy weight counts offline units; condition weight does not.
    assert alpha["occupancy_unit_weight"] == 600 + 500
    assert alpha["occupancy_rate"] == round((0.9 * 600 + 0.79 * 500) / 1100, 4)
    assert alpha["condition_unit_weight"] == 500 + 500
    assert alpha["condition_index"] == (85.0 * 500 + 90.0 * 500) / 1000
    assert alpha["resident_satisfaction"] == 75.0
    assert alpha["satisfaction_survey_count"] == 2
    assert alpha["overdue_work_orders"] == 5
    assert alpha["uh_available_units"] == 500
    assert alpha["mfh_available_units"] == 500

    bravo = by_id["bravo_afb"]
    assert bravo["uh_available_units"] is None  # no UH inventory reported
    assert bravo["uh_authorized_units"] == 400  # still counts toward demand
    assert bravo["mfh_available_units"] == 300

    occupancy = sum(
        item["occupancy_rate"] * item["occupancy_unit_weight"] for item in items
    ) / sum(item["occupancy_unit_weight"] for item in items)
    assert summary["occupancy_rate"] == round(occupancy, 4)
    assert kpis["portfolio_occupancy"] == round(occupancy * 100.0, 3)

    condition = sum(
        item["condition_index"] * item["condition_unit_weight"] for item in items
    ) / sum(item["condition_unit_weight"] for item in items)
    assert kpis["average_condition_index"] == round(condition, 3)

    satisfaction = sum(
        item["resident_satisfaction"] * item["satisfaction_survey_count"]
        for item in items
    ) / sum(item["satisfaction_survey_count"] for item in items)
    assert summary["resident_satisfaction"] == round(satisfaction, 2)
    assert kpis["resident_satisfaction"] == round(satisfaction, 3)

    assert kpis["work_order_overdue_rate"] == round(
        sum(item["overdue_work_orders"] for item in items)
        / sum(item["open_work_orders"] for item in items)
        * 100.0,
        3,
    )
    assert kpis["uh_supply_ratio"] == round(
        sum(
            item["uh_available_units"]
            for item in items
            if item["uh_available_units"] is not None
        )
        / sum(item["uh_authorized_units"] for item in items),
        3,
    )
    # Both sides of MFH reported → the ratio recomputes instead of unknown.
    assert kpis["mfh_supply_ratio"] == round(
        sum(
            item["mfh_available_units"]
            for item in items
            if item["mfh_available_units"] is not None
        )
        / sum(item["mfh_authorized_units"] for item in items),
        3,
    )


def test_explicit_knowledge_base_id_overrides_default_resolution() -> None:
    client, loader = _client(knowledge_bases=[])

    response = client.get(
        "/housing/installations", params={"knowledge_base_id": "kb-explicit"}
    )

    assert response.status_code == 200
    assert loader.requested_kb_ids == ["kb-explicit"]
    assert response.json()["total"] == 4


def _inventory_only(
    utilization: float, condition: float | None = None
) -> list[SourceRecord]:
    """One installation with a single inventory row (no resident experience)."""
    values: dict[str, SourceValue] = {
        "installation_id": "solo_afb",
        "category": "UH",
        "available_units": 100,
        "offline_units": 0,
        "utilization_rate": utilization,
    }
    if condition is not None:
        values["condition_index"] = condition
    return [_record("housing_inventory", "inv-solo", values)]


def _experience_only(
    satisfaction: float, open_orders: int, overdue_orders: int
) -> list[SourceRecord]:
    """One installation with a single resident-experience row (no inventory)."""
    return [
        _record(
            "resident_experience",
            "rex-solo",
            {
                "installation_id": "solo_afb",
                "satisfaction_score": satisfaction,
                "work_orders_open": open_orders,
                "work_orders_overdue": overdue_orders,
            },
        )
    ]


@pytest.mark.parametrize(
    ("records", "expected_status", "expected_reasons"),
    [
        pytest.param(
            _inventory_only(utilization=0.67),
            "critical",
            [
                "Occupancy 67.0% is below the 75% financial-risk trigger "
                "(10 U.S.C. §2884(c)(2))"
            ],
            id="occupancy-critical",
        ),
        pytest.param(
            _inventory_only(utilization=0.80),
            "watch",
            ["Occupancy 80.0% is below the 85% watch threshold"],
            id="occupancy-watch",
        ),
        pytest.param(
            _inventory_only(utilization=0.95, condition=65.0),
            "critical",
            ["Condition index 65.0 is below the critical threshold of 70"],
            id="condition-critical",
        ),
        pytest.param(
            _inventory_only(utilization=0.95, condition=74.0),
            "watch",
            ["Condition index 74.0 is below the watch threshold of 80"],
            id="condition-watch",
        ),
        pytest.param(
            _experience_only(satisfaction=50.0, open_orders=0, overdue_orders=0),
            "critical",
            ["Resident satisfaction 50.0 is below the critical threshold of 60"],
            id="satisfaction-critical",
        ),
        pytest.param(
            _experience_only(satisfaction=68.0, open_orders=0, overdue_orders=0),
            "watch",
            ["Resident satisfaction 68.0 is below the watch threshold of 75"],
            id="satisfaction-watch",
        ),
        pytest.param(
            _experience_only(satisfaction=90.0, open_orders=40, overdue_orders=11),
            "critical",
            ["Overdue work-order ratio 27.5% exceeds the 25% critical threshold"],
            id="overdue-critical",
        ),
        pytest.param(
            _experience_only(satisfaction=90.0, open_orders=40, overdue_orders=5),
            "watch",
            ["Overdue work-order ratio 12.5% exceeds the 10% watch threshold"],
            id="overdue-watch",
        ),
        pytest.param(
            _inventory_only(utilization=0.75),
            "watch",
            ["Occupancy 75.0% is below the 85% watch threshold"],
            id="occupancy-boundary-75-is-watch-not-critical",
        ),
        pytest.param(
            _inventory_only(utilization=0.85),
            "ok",
            [],
            id="occupancy-boundary-85-is-ok-not-watch",
        ),
        pytest.param(
            _experience_only(satisfaction=90.0, open_orders=40, overdue_orders=10),
            "watch",
            ["Overdue work-order ratio 25.0% exceeds the 10% watch threshold"],
            id="overdue-boundary-25-is-watch-not-critical",
        ),
        pytest.param(
            _inventory_only(utilization=0.7496),
            "critical",
            [
                "Occupancy 74.9% is below the 75% financial-risk trigger "
                "(10 U.S.C. §2884(c)(2))"
            ],
            id="occupancy-near-boundary-renders-away-from-the-line",
        ),
        pytest.param(
            _experience_only(satisfaction=90.0, open_orders=2500, overdue_orders=626),
            "critical",
            ["Overdue work-order ratio 25.1% exceeds the 25% critical threshold"],
            id="overdue-near-boundary-renders-away-from-the-line",
        ),
        pytest.param(
            _inventory_only(utilization=0.95, condition=90.0),
            "ok",
            [],
            id="ok-empty-reasons",
        ),
    ],
)
def test_status_reasons_carry_metric_value_and_threshold(
    records: list[SourceRecord],
    expected_status: str,
    expected_reasons: list[str],
) -> None:
    """Each banded metric emits a reason naming the metric, value, and line."""
    client, _loader = _client(loader=StubRecordLoader(records))

    items = client.get("/housing/installations").json()["items"]

    assert len(items) == 1
    assert items[0]["status"] == expected_status
    assert items[0]["status_reasons"] == expected_reasons


def test_status_reasons_cover_every_tripped_band_per_installation() -> None:
    """Status and reasons come from one evaluation: all tripped bands listed."""
    client, _loader = _client()

    by_id = {
        item["installation_id"]: item
        for item in client.get("/housing/installations").json()["items"]
    }

    # Healthy installation → ok with no findings.
    assert by_id["eglin_afb"]["status"] == "ok"
    assert by_id["eglin_afb"]["status_reasons"] == []

    # Watch installation lists every watch-band finding, in metric order.
    assert by_id["edwards_afb"]["status"] == "watch"
    assert by_id["edwards_afb"]["status_reasons"] == [
        "Occupancy 80.0% is below the 85% watch threshold",
        "Condition index 74.0 is below the watch threshold of 80",
        "Resident satisfaction 68.0 is below the watch threshold of 75",
        "Overdue work-order ratio 15.0% exceeds the 10% watch threshold",
    ]

    # Critical installation lists every critical-band finding.
    assert by_id["patrick_sfb"]["status"] == "critical"
    assert by_id["patrick_sfb"]["status_reasons"] == [
        "Occupancy 70.0% is below the 75% financial-risk trigger "
        "(10 U.S.C. §2884(c)(2))",
        "Condition index 65.0 is below the critical threshold of 70",
        "Resident satisfaction 50.0 is below the critical threshold of 60",
        "Overdue work-order ratio 40.0% exceeds the 25% critical threshold",
    ]

    # Non-reporting installation explains why it is unknown.
    assert by_id["context_only_afb"]["status"] == "unknown"
    assert by_id["context_only_afb"]["status_reasons"] == [
        "No inventory or resident-experience data reported"
    ]


def test_open_work_orders_rank_covers_reporting_installations_only() -> None:
    """Rank is 1-based by open work orders (1 = most) among reporters."""
    client, _loader = _client()

    by_id = {
        item["installation_id"]: item
        for item in client.get("/housing/installations").json()["items"]
    }

    assert by_id["patrick_sfb"]["open_work_orders_rank"] == 1  # 50 open
    assert by_id["edwards_afb"]["open_work_orders_rank"] == 2  # 40 open
    assert by_id["eglin_afb"]["open_work_orders_rank"] == 3  # 30 open
    # Non-reporting installations do not compete with zeros they never sent.
    assert by_id["context_only_afb"]["open_work_orders_rank"] is None


def test_open_work_orders_rank_ties_share_the_smaller_rank() -> None:
    """Competition ranking: equal open work orders share the smaller rank."""
    records = [
        _record(
            "resident_experience",
            f"rex-{installation_id}",
            {
                "installation_id": installation_id,
                "satisfaction_score": 90.0,
                "work_orders_open": open_orders,
                "work_orders_overdue": 0,
            },
        )
        for installation_id, open_orders in [
            ("alpha_afb", 50),
            ("bravo_afb", 30),
            ("charlie_afb", 30),
        ]
    ]
    client, _loader = _client(loader=StubRecordLoader(records))

    by_id = {
        item["installation_id"]: item
        for item in client.get("/housing/installations").json()["items"]
    }

    assert by_id["alpha_afb"]["open_work_orders_rank"] == 1
    assert by_id["bravo_afb"]["open_work_orders_rank"] == 2
    assert by_id["charlie_afb"]["open_work_orders_rank"] == 2


def test_default_kb_resolution_prefers_ready_then_newest() -> None:
    knowledge_bases = [
        _kb("kb-old-ready", created=datetime(2026, 5, 1, tzinfo=UTC)),
        _kb("kb-new-ready", created=datetime(2026, 6, 15, tzinfo=UTC)),
        _kb(
            "kb-newest-active",
            status="active",
            created=datetime(2026, 7, 1, tzinfo=UTC),
        ),
    ]
    client, loader = _client(knowledge_bases=knowledge_bases)

    client.get("/housing/overview")

    assert loader.requested_kb_ids == ["kb-new-ready"]
