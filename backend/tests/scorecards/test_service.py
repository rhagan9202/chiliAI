from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest

from config.loader import load_config
from config.schema import (
    AlertsConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    IngestionSourceConfig,
    RecordFeedConfig,
    RecordsConfig,
    ScorecardFormulaConfig,
    ScorecardMetricConfig,
    ScorecardMetricInputConfig,
    ScorecardSectionConfig,
    ScorecardsConfig,
    ScorecardTemplateConfig,
    ScorecardThresholdConfig,
)
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.evaluation import SourceRecord, SourceValue
from scorecards.exceptions import (
    ScorecardExportNotFoundError,
    ScorecardRunNotFoundError,
    ScorecardTemplateNotFoundError,
)
from scorecards.models import ScorecardExportFormat
from scorecards.service import ScorecardService, ScorecardSourceRecordLoader
from scorecards.service_models import ScorecardGenerateRequest, ScorecardRunListRequest
from shared.types import PropertyDefinition, PropertyType


CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "defaults"
    / "department_air_force_housing.yaml"
)


class StubRecordLoader:
    """ScorecardSourceRecordLoader double serving a fixed record set."""

    def __init__(self, records: list[SourceRecord]) -> None:
        self.records = records
        self.requested_kb_ids: list[str] = []

    def load_source_records(self, knowledge_base_id: str) -> list[SourceRecord]:
        self.requested_kb_ids.append(knowledge_base_id)
        return list(self.records)


def _source_record(
    feed_name: str,
    record_id: str,
    values: dict[str, SourceValue],
    *,
    observed: date = date(2026, 6, 30),
) -> SourceRecord:
    return SourceRecord(
        feed_name=feed_name,
        record_id=record_id,
        values=values,
        observed_at=datetime(observed.year, observed.month, observed.day, tzinfo=UTC),
    )


def _uh_records(
    *,
    installation_id: str = "jbsa",
    available_units: float = 1100,
    demand: float = 1000,
    condition_index: float = 86.0,
    observed: date = date(2026, 6, 30),
) -> list[SourceRecord]:
    """Records satisfying both uh_scorecard metrics for one installation."""
    return [
        _source_record(
            "housing_inventory",
            f"inv-{installation_id}-uh",
            {
                "installation_id": installation_id,
                "category": "UH",
                "available_units": available_units,
                "condition_index": condition_index,
            },
            observed=observed,
        ),
        _source_record(
            "umd_authorizations",
            f"umd-{installation_id}",
            {
                "installation_id": installation_id,
                "unaccompanied_authorized": demand,
            },
            observed=observed,
        ),
    ]


def _test_config() -> DomainConfig:
    """A minimal domain config with one fixed UH template.

    Built in-code (not from the pack YAML) so these behavioural tests stay
    stable while the shipped statutory templates evolve.
    """
    return DomainConfig(
        domain=DomainInfo(
            name="test_housing",
            display_name="Test Housing",
            description="Scorecard service test domain.",
        ),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(
            sources=[IngestionSourceConfig(type="file_upload", formats=["csv"])]
        ),
        alerts=AlertsConfig(thresholds={}),
        records=RecordsConfig(
            feeds=[
                RecordFeedConfig(
                    name="housing_inventory",
                    record_type="housing_inventory",
                    source="file_upload",
                    id_field="snapshot_id",
                    allow_extra_fields=True,
                    record_schema={
                        "snapshot_id": PropertyDefinition(
                            type=PropertyType.STRING, display="Snapshot ID"
                        ),
                        "category": PropertyDefinition(
                            type=PropertyType.STRING, display="Category"
                        ),
                        "available_units": PropertyDefinition(
                            type=PropertyType.INTEGER, display="Available Units"
                        ),
                        "condition_index": PropertyDefinition(
                            type=PropertyType.DECIMAL, display="Condition Index"
                        ),
                    },
                ),
                RecordFeedConfig(
                    name="umd_authorizations",
                    record_type="umd_authorization",
                    source="file_upload",
                    id_field="demand_id",
                    allow_extra_fields=True,
                    record_schema={
                        "demand_id": PropertyDefinition(
                            type=PropertyType.STRING, display="Demand ID"
                        ),
                        "unaccompanied_authorized": PropertyDefinition(
                            type=PropertyType.INTEGER,
                            display="Unaccompanied Authorized",
                        ),
                    },
                ),
            ]
        ),
        scorecards=ScorecardsConfig(
            templates=[
                ScorecardTemplateConfig(
                    id="uh_test",
                    name="UH Test Scorecard",
                    category="UH",
                    scope="installation",
                    period="quarterly",
                    sections=[
                        ScorecardSectionConfig(
                            id="supply",
                            label="Supply",
                            metrics=[
                                ScorecardMetricConfig(
                                    id="uh_supply_ratio",
                                    label="UH Supply Ratio",
                                    unit="ratio",
                                    housing_category="UH",
                                    inputs=[
                                        ScorecardMetricInputConfig(
                                            name="supply",
                                            source="record_feed",
                                            ref="housing_inventory",
                                            field="available_units",
                                            filter={"category": "UH"},
                                        ),
                                        ScorecardMetricInputConfig(
                                            name="demand",
                                            source="record_feed",
                                            ref="umd_authorizations",
                                            field="unaccompanied_authorized",
                                        ),
                                    ],
                                    formula=ScorecardFormulaConfig(
                                        operator="ratio",
                                        numerator="supply",
                                        denominator="demand",
                                    ),
                                    thresholds=ScorecardThresholdConfig(
                                        pass_min=1.0, warn_min=0.9, fail_max=0.89
                                    ),
                                )
                            ],
                        ),
                        ScorecardSectionConfig(
                            id="condition",
                            label="Condition",
                            metrics=[
                                ScorecardMetricConfig(
                                    id="uh_condition_index",
                                    label="UH Condition Index",
                                    unit="score",
                                    housing_category="UH",
                                    inputs=[
                                        ScorecardMetricInputConfig(
                                            name="condition",
                                            source="record_feed",
                                            ref="housing_inventory",
                                            field="condition_index",
                                            filter={"category": "UH"},
                                        )
                                    ],
                                    formula=ScorecardFormulaConfig(
                                        operator="mean", value="condition"
                                    ),
                                    thresholds=ScorecardThresholdConfig(
                                        pass_min=80, warn_min=70, fail_max=69
                                    ),
                                )
                            ],
                        ),
                    ],
                )
            ]
        ),
    )


def _service(
    record_source: ScorecardSourceRecordLoader | None = None,
    *,
    config: DomainConfig | None = None,
) -> tuple[ScorecardService, InMemoryScorecardRunRepository]:
    repo = InMemoryScorecardRunRepository()
    service = ScorecardService(
        config=config if config is not None else load_config(CONFIG_PATH),
        repository=repo,
        record_source=record_source,
    )
    return service, repo


def _request(template_id: str = "uh_scorecard") -> ScorecardGenerateRequest:
    return ScorecardGenerateRequest(
        knowledge_base_id="kb-1",
        template_id=template_id,
        scope_type="installation",
        scope_id="jbsa",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
    )


def test_list_templates_and_get_template_use_configured_scorecards() -> None:
    service, _repo = _service()

    templates = service.list_templates()
    template = service.get_template("uh_scorecard")

    assert [item.id for item in templates.items] == ["uh_scorecard", "mfh_scorecard"]
    assert template.name == "Unaccompanied Housing Scorecard"


def test_get_template_raises_domain_error_for_missing_template() -> None:
    service, _repo = _service()

    with pytest.raises(ScorecardTemplateNotFoundError):
        service.get_template("missing")


def test_generate_evaluates_empty_state_persists_and_renders_exports() -> None:
    service, repo = _service()

    run = service.generate(_request())

    stored = repo.get(knowledge_base_id="kb-1", run_id=run.id)
    assert stored == run
    assert run.template_name == "Unaccompanied Housing Scorecard"
    assert run.scope_type == "installation"
    assert run.period_start == date(2026, 4, 1)
    assert run.period_end == date(2026, 6, 30)
    assert run.status == "generated"
    assert run.overall_health == "incomplete"
    assert set(run.export_payloads) == {"json", "markdown"}

    payload = json.loads(run.export_payloads["json"])
    assert payload["id"] == run.id
    assert payload["sections"][0]["metrics"][0]["health"] == "incomplete"

    markdown = run.export_payloads["markdown"]
    assert "# Unaccompanied Housing Scorecard" in markdown
    assert "Scope: installation jbsa" in markdown
    assert "Period: 2026-04-01 to 2026-06-30" in markdown
    assert "Overall Health: incomplete" in markdown
    # Every configured section and metric renders (labels come from the pack).
    template = service.get_template("uh_scorecard")
    for section in template.sections:
        assert f"## {section.label}" in markdown
        for metric in section.metrics:
            assert f"- {metric.label}: incomplete" in markdown
    assert "section health" not in markdown.lower()


def test_generate_reuses_existing_run_for_same_snapshot_key() -> None:
    service, _repo = _service()

    first = service.generate(_request())
    second = service.generate(_request())

    assert second.id == first.id
    assert second.source_snapshot_hash == first.source_snapshot_hash


def test_list_get_and_export_runs_raise_domain_errors_for_missing_data() -> None:
    service, _repo = _service()
    run = service.generate(_request())

    listed = service.list_runs(
        ScorecardRunListRequest(knowledge_base_id="kb-1", template_id="uh_scorecard")
    )
    assert listed.total == 1
    assert listed.items == [run]
    assert service.get_run(knowledge_base_id="kb-1", run_id=run.id) == run

    export = service.export_run(
        knowledge_base_id="kb-1", run_id=run.id, format="markdown"
    )
    assert export.run_id == run.id
    assert export.format == "markdown"
    assert export.content == run.export_payloads["markdown"]

    with pytest.raises(ScorecardRunNotFoundError):
        service.get_run(knowledge_base_id="kb-1", run_id="missing")

    with pytest.raises(ScorecardRunNotFoundError):
        service.export_run(knowledge_base_id="kb-1", run_id="missing", format="json")

    missing_format = cast(ScorecardExportFormat, "csv")
    with pytest.raises(ScorecardExportNotFoundError):
        service.export_run(
            knowledge_base_id="kb-1",
            run_id=run.id,
            format=missing_format,
        )


def _fresh_request(template_id: str = "uh_test") -> ScorecardGenerateRequest:
    """A request whose period ends today, so freshness windows always pass."""
    today = date.today()
    return ScorecardGenerateRequest(
        knowledge_base_id="kb-1",
        template_id=template_id,
        scope_type="installation",
        scope_id="jbsa",
        period_start=today.replace(day=1),
        period_end=today,
    )


def test_generate_with_records_produces_passing_grades() -> None:
    loader = StubRecordLoader(
        _uh_records(
            available_units=1100,
            demand=1000,
            condition_index=86.0,
            observed=date.today(),
        )
    )
    service, _repo = _service(record_source=loader, config=_test_config())

    run = service.generate(_fresh_request())

    assert loader.requested_kb_ids == ["kb-1"]
    assert run.overall_health == "pass"
    supply = run.sections[0].metrics[0]
    condition = run.sections[1].metrics[0]
    assert supply.value == pytest.approx(1.1)
    assert supply.health == "pass"
    assert supply.completeness == "complete"
    assert {c.feed_name for c in supply.citations} == {
        "housing_inventory",
        "umd_authorizations",
    }
    assert condition.value == pytest.approx(86.0)
    assert condition.health == "pass"


def test_generate_grades_vary_with_record_values() -> None:
    loader = StubRecordLoader(
        _uh_records(
            available_units=850,
            demand=1000,
            condition_index=74.0,
            observed=date.today(),
        )
    )
    service, _repo = _service(record_source=loader, config=_test_config())

    run = service.generate(_fresh_request())

    supply = run.sections[0].metrics[0]
    condition = run.sections[1].metrics[0]
    assert supply.health == "fail"
    assert supply.value == pytest.approx(0.85)
    assert condition.health == "warn"
    assert run.overall_health == "fail"


def test_generate_scopes_records_to_requested_installation() -> None:
    records = _uh_records(
        installation_id="jbsa",
        available_units=1100,
        demand=1000,
        condition_index=86.0,
        observed=date.today(),
    ) + _uh_records(
        installation_id="failing_afb",
        available_units=500,
        demand=1000,
        condition_index=55.0,
        observed=date.today(),
    )
    service, _repo = _service(
        record_source=StubRecordLoader(records), config=_test_config()
    )

    scoped = service.generate(_fresh_request())

    # The failing installation's records must not bleed into the jbsa run.
    assert scoped.overall_health == "pass"
    assert {
        citation.record_id
        for section in scoped.sections
        for metric in section.metrics
        for citation in metric.citations
    } == {"inv-jbsa-uh", "umd-jbsa"}


def test_generate_excludes_records_outside_period() -> None:
    stale = _uh_records(observed=date(2020, 1, 15))
    service, _repo = _service(
        record_source=StubRecordLoader(stale), config=_test_config()
    )

    run = service.generate(_fresh_request())

    # All records predate the period, so every metric is missing its source.
    assert run.overall_health == "incomplete"
    for section in run.sections:
        for metric in section.metrics:
            assert metric.completeness == "missing_source"


def test_snapshot_hash_reflects_evaluated_records() -> None:
    empty_service, _repo = _service(
        record_source=StubRecordLoader([]), config=_test_config()
    )
    data_service, _repo2 = _service(
        record_source=StubRecordLoader(_uh_records(observed=date.today())),
        config=_test_config(),
    )
    data_service_again, _repo3 = _service(
        record_source=StubRecordLoader(_uh_records(observed=date.today())),
        config=_test_config(),
    )

    empty_run = empty_service.generate(_fresh_request())
    data_run = data_service.generate(_fresh_request())
    repeat_run = data_service_again.generate(_fresh_request())

    # New source data must mint a new run; identical data stays idempotent.
    assert data_run.id != empty_run.id
    assert repeat_run.id == data_run.id
    assert repeat_run.source_snapshot_hash == data_run.source_snapshot_hash


def _config_with_supply_pass_min(pass_min: float) -> DomainConfig:
    """``_test_config()`` with the UH supply-ratio pass threshold moved."""
    config = _test_config()
    template = config.scorecards.templates[0]
    supply_section = template.sections[0]
    metric = supply_section.metrics[0]
    retuned_metric = metric.model_copy(
        update={
            "thresholds": ScorecardThresholdConfig(
                pass_min=pass_min, warn_min=0.9, fail_max=0.89
            )
        }
    )
    retuned_template = template.model_copy(
        update={
            "sections": [
                supply_section.model_copy(update={"metrics": [retuned_metric]}),
                *template.sections[1:],
            ]
        }
    )
    return config.model_copy(
        update={"scorecards": ScorecardsConfig(templates=[retuned_template])}
    )


def test_retuning_a_threshold_produces_a_fresh_run_over_unchanged_records() -> None:
    """A template change must not be served the previous run's grades.

    Run reuse is keyed on the source snapshot, so an operator who tightens a
    threshold and re-runs over identical records would otherwise be handed the
    row computed under the old thresholds — the grade the change was meant to
    alter.
    """
    records = _uh_records(available_units=1100, demand=1000, observed=date.today())
    lenient, repo = _service(
        StubRecordLoader(records), config=_config_with_supply_pass_min(1.0)
    )
    first = lenient.generate(_fresh_request())
    assert first.overall_health == "pass"

    strict = ScorecardService(
        config=_config_with_supply_pass_min(1.2),
        repository=repo,
        record_source=StubRecordLoader(records),
    )
    second = strict.generate(_fresh_request())

    assert second.id != first.id
    assert second.overall_health == "warn"


def test_identical_template_and_records_still_reuse_the_run() -> None:
    """The fingerprint must not defeat idempotency for an unchanged template."""
    records = _uh_records(observed=date.today())
    service, _repo = _service(StubRecordLoader(records), config=_test_config())

    first = service.generate(_fresh_request())
    second = service.generate(_fresh_request())

    assert second.id == first.id
