from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from config.loader import load_config
from config.schema import (
    DomainConfig,
    ScorecardMetricConfig,
    ScorecardSectionConfig,
    ScorecardTemplateConfig,
)
from scorecards.evaluation import ScorecardEvalState, SourceRecord, evaluate_template

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_PATH = (
    REPO_ROOT
    / "backend"
    / "config"
    / "defaults"
    / "department_air_force_housing.yaml"
)


@pytest.fixture()
def config(monkeypatch: pytest.MonkeyPatch) -> DomainConfig:
    monkeypatch.setenv("CHILI_CONFIG_PATH", str(PACK_PATH))
    return load_config()


def test_air_force_housing_pack_loads(config: DomainConfig) -> None:
    assert config.domain.name == "department_air_force_housing"
    assert config.domain.display_name == "Department of the Air Force Housing"
    assert config.capabilities.structured_ingestion is True
    assert config.capabilities.rag_chat is True


def test_housing_entities_and_relationships_are_declared(config: DomainConfig) -> None:
    entity_names = {entity.name for entity in config.entities}
    assert {
        "installation",
        "housing_asset",
        "housing_inventory_snapshot",
        "population_demand_snapshot",
        "allowance_market_snapshot",
        "demographic_snapshot",
        "resident_experience_snapshot",
        "scorecard_run",
    } <= entity_names
    relationship_names = {relationship.name for relationship in config.relationships}
    assert {
        "installation_has_asset",
        "asset_has_inventory_snapshot",
        "installation_has_population_demand",
        "installation_has_market_snapshot",
        "installation_has_demographic_snapshot",
        "scorecard_run_for_installation",
    } <= relationship_names


def test_housing_record_feeds_cover_required_exports(config: DomainConfig) -> None:
    assert config.records is not None
    feeds = {feed.name: feed for feed in config.records.feeds}
    assert {
        "umd_authorizations",
        "bah_rates",
        "housing_inventory",
        "market_availability",
        "area_demographics",
        "resident_experience",
    } <= set(feeds)
    assert feeds["umd_authorizations"].accepted_formats == ["csv", "jsonl"]
    assert feeds["housing_inventory"].allow_extra_fields is True
    for feed in feeds.values():
        assert feed.entities


def test_housing_observations_are_bounded_scores_only(config: DomainConfig) -> None:
    """Observations map only bounded score fields, normalized into [0, 1].

    Raw-count fields (unaccompanied_authorized, available_rentals,
    local_population) are not scores and carry no observation — the former
    unaccompanied_demand, rental_availability, and demographic_context
    observations produced out-of-bound MonitoringObservation scores and
    failed every housing ingestion run.
    """
    assert config.records is not None
    feeds = {feed.name: feed for feed in config.records.feeds}

    expected = {
        "umd_authorizations": [],
        "bah_rates": [("market_pressure", "affordability_index", 100.0)],
        "housing_inventory": [("housing_condition", "condition_index", 100.0)],
        "market_availability": [],
        "area_demographics": [],
        "resident_experience": [
            ("resident_satisfaction", "satisfaction_score", 100.0)
        ],
    }
    actual = {
        name: [
            (obs.metric_name, obs.score_field, obs.score_max)
            for obs in feed.observations
        ]
        for name, feed in feeds.items()
    }
    assert actual == expected

    # Every observed field declares bounds that prove the normalization.
    for feed in feeds.values():
        for obs in feed.observations:
            field_def = feed.record_schema[obs.score_field]
            assert field_def.min_value == 0
            assert field_def.max_value == 100
            assert obs.score_max == 100.0


def test_feed_contract_additions_are_declared(config: DomainConfig) -> None:
    """Interface 2 additive columns land in both feed schemas and entity properties."""
    assert config.records is not None
    feeds = {feed.name: feed for feed in config.records.feeds}
    entities = {entity.name: entity for entity in config.entities}

    umd_schema = feeds["umd_authorizations"].record_schema
    assert umd_schema["branch"].type.value == "string"
    assert "branch" in entities["installation"].properties
    umd_installation = next(
        mapping
        for mapping in feeds["umd_authorizations"].entities
        if mapping.entity_type == "installation"
    )
    assert umd_installation.property_fields["branch"] == "branch"

    inventory_schema = feeds["housing_inventory"].record_schema
    assert inventory_schema["repair_backlog_usd"].min_value == 0
    assert inventory_schema["replacement_cost_usd"].min_value == 0.01
    assert inventory_schema["average_unit_age_years"].min_value == 0
    snapshot_props = entities["housing_inventory_snapshot"].properties
    assert {
        "repair_backlog_usd",
        "replacement_cost_usd",
        "average_unit_age_years",
    } <= set(snapshot_props)
    inventory_snapshot = next(
        mapping
        for mapping in feeds["housing_inventory"].entities
        if mapping.entity_type == "housing_inventory_snapshot"
    )
    assert {
        "repair_backlog_usd",
        "replacement_cost_usd",
        "average_unit_age_years",
    } <= set(inventory_snapshot.property_fields)


def test_resident_experience_feed_is_declared(config: DomainConfig) -> None:
    """The new resident_experience feed matches the frozen column contract."""
    assert config.records is not None
    feed = next(
        feed for feed in config.records.feeds if feed.name == "resident_experience"
    )
    assert feed.id_field == "experience_id"
    assert feed.allow_extra_fields is True
    assert feed.accepted_formats == ["csv", "jsonl"]
    assert set(feed.record_schema) == {
        "experience_id",
        "installation_id",
        "category",
        "satisfaction_score",
        "maintenance_response_hours",
        "work_orders_open",
        "work_orders_overdue",
        "work_order_completion_rate",
        "disputes_filed",
        "disputes_resolved",
        "dispute_payments_usd",
        "safety_waiver_count",
        "snapshot_date",
    }
    assert feed.record_schema["experience_id"].required is True
    assert feed.record_schema["installation_id"].required is True
    assert feed.record_schema["snapshot_date"].required is True
    assert feed.record_schema["category"].enum_values == ["UH", "MFH"]
    assert feed.record_schema["satisfaction_score"].max_value == 100
    assert feed.record_schema["work_order_completion_rate"].max_value == 1

    mapped_entity_types = {mapping.entity_type for mapping in feed.entities}
    assert mapped_entity_types == {"installation", "resident_experience_snapshot"}
    snapshot_mapping = next(
        mapping
        for mapping in feed.entities
        if mapping.entity_type == "resident_experience_snapshot"
    )
    # Feed column work_orders_open lands on the existing entity property.
    assert snapshot_mapping.property_fields["open_work_orders"] == "work_orders_open"
    assert {feed_relationship.relationship_type for feed_relationship in feed.relationships} == {
        "installation_has_resident_experience"
    }
    assert feed.observations
    assert feed.observations[0].score_field == "satisfaction_score"
    # 0-100 survey scale normalized into the [0, 1] observation bound.
    assert feed.observations[0].score_max == 100.0


def test_scorecard_templates_are_configured(config: DomainConfig) -> None:
    template_ids = {template.id for template in config.scorecards.templates}
    assert {"uh_scorecard", "mfh_scorecard"} <= template_ids
    for template in config.scorecards.templates:
        assert template.sections
        assert template.export_formats == ["json", "markdown"]
        for section in template.sections:
            assert section.metrics
            for metric in section.metrics:
                assert metric.inputs
                assert metric.formula.operator in {
                    "ratio",
                    "sum",
                    "mean",
                    "weighted_mean",
                    "latest",
                }
                thresholds = metric.thresholds
                assert (
                    thresholds.pass_min is not None
                    or thresholds.fail_max is not None
                    or thresholds.pass_max is not None
                    or thresholds.fail_min is not None
                )
                assert thresholds.incomplete_when_missing is True


# Dossier docs/research/housing-scorecard-mandates.md § 4.1 / § 4.2:
# section id -> ordered metric ids.
UH_TEMPLATE_STRUCTURE = {
    "demand_supply": ["uh_supply_ratio", "uh_utilization_rate"],
    "condition_recapitalization": ["uh_condition_index", "uh_repair_backlog_ratio"],
    "maintenance_performance": [
        "uh_work_order_completion_rate",
        "uh_maintenance_response_hours",
    ],
    "resident_experience_safety": [
        "uh_resident_satisfaction",
        "uh_safety_waiver_count",
    ],
}
MFH_TEMPLATE_STRUCTURE = {
    "family_housing_supply": ["mfh_supply_ratio", "mfh_market_affordability"],
    "financial_management": ["mfh_occupancy_rate", "mfh_repair_backlog_ratio"],
    "condition_recapitalization": ["mfh_condition_index", "mfh_average_unit_age"],
    "maintenance_management": [
        "mfh_work_order_completion_rate",
        "mfh_maintenance_response_hours",
    ],
    "tenant_satisfaction": ["mfh_resident_satisfaction"],
    "safety": ["mfh_safety_waiver_count"],
    "dispute_resolution": ["mfh_dispute_resolution_rate", "mfh_dispute_payments"],
}


def _template_by_id(config: DomainConfig, template_id: str) -> ScorecardTemplateConfig:
    return next(
        template
        for template in config.scorecards.templates
        if template.id == template_id
    )


def _metric_by_id(
    template: ScorecardTemplateConfig, metric_id: str
) -> ScorecardMetricConfig:
    return next(
        metric
        for section in template.sections
        for metric in section.metrics
        if metric.id == metric_id
    )


@pytest.mark.parametrize(
    ("template_id", "structure", "metric_count"),
    [
        ("uh_scorecard", UH_TEMPLATE_STRUCTURE, 8),
        ("mfh_scorecard", MFH_TEMPLATE_STRUCTURE, 12),
    ],
)
def test_dossier_template_structure(
    config: DomainConfig,
    template_id: str,
    structure: dict[str, list[str]],
    metric_count: int,
) -> None:
    template = _template_by_id(config, template_id)
    assert [section.id for section in template.sections] == list(structure)
    for section in template.sections:
        assert [metric.id for metric in section.metrics] == structure[section.id]
    assert sum(len(section.metrics) for section in template.sections) == metric_count


def test_scorecard_filter_keys_must_be_declared_feed_fields(
    config: DomainConfig,
) -> None:
    """A typo'd metric-input filter key fails validation (red-cell B4/C1)."""
    dumped = config.model_dump()
    # Round-trip control: the unmodified pack re-validates cleanly.
    DomainConfig.model_validate(dumped)
    metric = dumped["scorecards"]["templates"][0]["sections"][0]["metrics"][0]
    metric["inputs"][0]["filter"] = {"categry": "UH"}
    with pytest.raises(ValueError, match="filter key 'categry'"):
        DomainConfig.model_validate(dumped)


def test_statutory_thresholds_match_dossier(config: DomainConfig) -> None:
    """The two hard statutory numbers land exactly (dossier § 6 item 5)."""
    backlog = _metric_by_id(
        _template_by_id(config, "uh_scorecard"), "uh_repair_backlog_ratio"
    )
    # 10 U.S.C. § 2856b(c): repair needs must not exceed 20% of replacement cost.
    assert backlog.thresholds.pass_max == 0.20
    assert backlog.freshness_days == 400

    occupancy = _metric_by_id(
        _template_by_id(config, "mfh_scorecard"), "mfh_occupancy_rate"
    )
    # 10 U.S.C. § 2884(c)(2): financial-risk trigger when occupancy < 75%.
    assert occupancy.thresholds.warn_min == 0.75


def _grade_metric(metric: ScorecardMetricConfig, records: list[SourceRecord]) -> str:
    as_of = datetime(2026, 7, 6, tzinfo=UTC)
    template = ScorecardTemplateConfig(
        id="worked-example",
        name="Worked example",
        category="combined",
        scope="installation",
        period="quarterly",
        sections=[ScorecardSectionConfig(id="s", label="Section", metrics=[metric])],
    )
    result = evaluate_template(
        template, ScorecardEvalState(as_of=as_of, records=records)
    )
    metric_result = result.sections[0].metrics[0]
    assert metric_result.completeness == "complete"
    return metric_result.health


@pytest.mark.parametrize(
    ("backlog_usd", "expected_health"),
    [(20.0, "pass"), (21.0, "warn"), (26.0, "fail")],
)
def test_uh_backlog_ratio_worked_example_lower_is_better(
    config: DomainConfig, backlog_usd: float, expected_health: str
) -> None:
    """Dossier UH #4 worked example: ratio 0.20 pass, 0.21 warn, 0.26 fail."""
    metric = _metric_by_id(
        _template_by_id(config, "uh_scorecard"), "uh_repair_backlog_ratio"
    )
    records = [
        SourceRecord(
            feed_name="housing_inventory",
            record_id="inv-uh-1",
            observed_at=datetime(2026, 7, 1, tzinfo=UTC),
            values={
                "category": "UH",
                "repair_backlog_usd": backlog_usd,
                "replacement_cost_usd": 100.0,
            },
        )
    ]
    assert _grade_metric(metric, records) == expected_health


@pytest.mark.parametrize(
    ("utilization", "expected_health"),
    [(0.90, "pass"), (0.75, "warn"), (0.70, "fail")],
)
def test_mfh_occupancy_worked_example_higher_is_better(
    config: DomainConfig, utilization: float, expected_health: str
) -> None:
    """Dossier MFH #3 worked example around the § 2884(c)(2) 75% trigger."""
    metric = _metric_by_id(
        _template_by_id(config, "mfh_scorecard"), "mfh_occupancy_rate"
    )
    records = [
        SourceRecord(
            feed_name="housing_inventory",
            record_id="inv-mfh-1",
            observed_at=datetime(2026, 7, 1, tzinfo=UTC),
            values={"category": "MFH", "utilization_rate": utilization},
        )
    ]
    assert _grade_metric(metric, records) == expected_health


MEDICARE_EXEMPLAR_PATH = (
    REPO_ROOT
    / "backend"
    / "config"
    / "defaults"
    / "medicare_fraud_cms_desynpuf.yaml"
)


def test_infra_pins_match_medicare_exemplar(
    config: DomainConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pack pins the dev-stack services with the exemplar pack's selections.

    Without these pins the KB store, records, and scorecard runs fall back to
    per-process in-memory defaults and the demo wipes on API restart.
    """
    monkeypatch.setenv("CHILI_CONFIG_PATH", str(MEDICARE_EXEMPLAR_PATH))
    exemplar = load_config()

    assert config.graph is not None and exemplar.graph is not None
    assert config.graph.backend == exemplar.graph.backend == "neo4j"
    assert config.graph.uri == exemplar.graph.uri

    assert config.vectorstore is not None and exemplar.vectorstore is not None
    assert config.vectorstore.backend == exemplar.vectorstore.backend == "qdrant"
    assert config.vectorstore.uri == exemplar.vectorstore.uri

    assert config.storage is not None and exemplar.storage is not None
    assert config.storage.backend == exemplar.storage.backend == "local"
    assert config.storage.base_path == exemplar.storage.base_path

    assert config.events is not None and exemplar.events is not None
    assert config.events.backend == exemplar.events.backend == "redis"
    assert config.events.uri == exemplar.events.uri
    assert config.events.stream_prefix == exemplar.events.stream_prefix
    assert config.events.consumer_group == exemplar.events.consumer_group

    assert config.database is not None and exemplar.database is not None
    assert config.database.backend == exemplar.database.backend == "postgres"
    assert (
        config.database.dsn_env_var
        == exemplar.database.dsn_env_var
        == "DATABASE_URL"
    )

    assert config.embeddings is not None and exemplar.embeddings is not None
    assert config.embeddings.provider == exemplar.embeddings.provider
    assert config.embeddings.dimensions == exemplar.embeddings.dimensions

    # Local LLM with the exemplar's fallback chain (config/README checklist).
    assert config.llm is not None
    assert config.llm.provider == "local"
    assert config.llm.fallback is not None
    assert config.llm.fallback.fallback is not None


def test_housing_ui_lands_on_housing_page(config: DomainConfig) -> None:
    assert config.ui is not None
    pages = (
        {page.id: page for page in config.ui.navigation.pages}
        if config.ui.navigation
        else {}
    )
    assert pages["housing"].route == "/housing"
    assert config.ui.roles["executive"].landing_page == "housing"
