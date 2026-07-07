from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import inf, nan

import pytest

from config.schema import (
    ScorecardFormulaConfig,
    ScorecardMetricConfig,
    ScorecardMetricInputConfig,
    ScorecardSectionConfig,
    ScorecardTemplateConfig,
    ScorecardThresholdConfig,
)
from scorecards.evaluation import (
    ScorecardEvalState,
    SourceRecord,
    evaluate_template,
)
from scorecards.models import ScorecardRun
import scorecards.service_models as service_models


NOW = datetime(2026, 7, 1, tzinfo=UTC)


def _template(*, metric: ScorecardMetricConfig) -> ScorecardTemplateConfig:
    return ScorecardTemplateConfig(
        id="af-housing",
        name="Air Force housing scorecard",
        category="combined",
        scope="installation",
        period="monthly",
        sections=[
            ScorecardSectionConfig(
                id="supply-demand",
                label="Supply and demand",
                metrics=[metric],
            )
        ],
    )


def _ratio_metric(*, freshness_days: int = 30) -> ScorecardMetricConfig:
    return ScorecardMetricConfig(
        id="supply_demand_ratio",
        label="Supply demand ratio",
        description="Available housing supply divided by validated demand.",
        unit="ratio",
        housing_category="combined",
        inputs=[
            ScorecardMetricInputConfig(
                name="supply",
                source="record_feed",
                ref="housing_inventory",
                field="available_units",
                filter={"installation": "JBSA"},
            ),
            ScorecardMetricInputConfig(
                name="demand",
                source="record_feed",
                ref="umd_authorizations",
                field="authorized_units",
                filter={"installation": "JBSA"},
            ),
        ],
        formula=ScorecardFormulaConfig(
            operator="ratio",
            numerator="supply",
            denominator="demand",
        ),
        thresholds=ScorecardThresholdConfig(pass_min=0.95, warn_min=0.85),
        freshness_days=freshness_days,
    )


def _sum_metric(
    *,
    required: bool = True,
    field: str = "available_units",
) -> ScorecardMetricConfig:
    return ScorecardMetricConfig(
        id="available_units_total",
        label="Available units total",
        unit="units",
        housing_category="combined",
        inputs=[
            ScorecardMetricInputConfig(
                name="supply",
                source="record_feed",
                ref="housing_inventory",
                field=field,
                filter={"installation": "JBSA"},
            )
        ],
        formula=ScorecardFormulaConfig(operator="sum", value="supply"),
        thresholds=ScorecardThresholdConfig(pass_min=1.0, warn_min=0.0),
        freshness_days=30,
        required=required,
    )


def test_public_scorecard_models_cover_task_3_contract() -> None:
    assert {
        "id",
        "knowledge_base_id",
        "template_id",
        "template_name",
        "scope_type",
        "scope_id",
        "period_start",
        "period_end",
        "source_snapshot_hash",
        "status",
        "overall_health",
        "sections",
        "export_payloads",
        "created_at",
        "updated_at",
    } <= set(ScorecardRun.model_fields)
    assert hasattr(service_models, "ScorecardGenerateRequest")
    assert hasattr(service_models, "ScorecardRunListRequest")
    assert hasattr(service_models, "ScorecardTemplateSummary")
    assert hasattr(service_models, "ScorecardTemplateListResponse")
    assert hasattr(service_models, "ScorecardRunListResponse")
    assert hasattr(service_models, "ScorecardExportResponse")


def test_ratio_metric_scores_warn_with_record_feed_citations() -> None:
    result = evaluate_template(
        _template(metric=_ratio_metric()),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="housing_inventory",
                    record_id="inv-1",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "available_units": 1120},
                ),
                SourceRecord(
                    feed_name="umd_authorizations",
                    record_id="umd-1",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "authorized_units": 1250},
                ),
            ],
        ),
    )

    metric = result.sections[0].metrics[0]
    assert metric.value == 0.896
    assert metric.health == "warn"
    assert metric.completeness == "complete"
    assert [citation.citation_id for citation in metric.citations] == [
        "housing_inventory:inv-1",
        "umd_authorizations:umd-1",
    ]


def test_missing_required_source_marks_metric_incomplete() -> None:
    result = evaluate_template(
        _template(metric=_ratio_metric()),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="umd_authorizations",
                    record_id="umd-1",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "authorized_units": 1250},
                )
            ],
        ),
    )

    metric = result.sections[0].metrics[0]
    assert metric.value is None
    assert metric.health == "incomplete"
    assert metric.completeness == "missing_source"
    assert any("housing_inventory" in warning for warning in metric.warnings)


def test_stale_source_downgrades_passing_metric_to_warn() -> None:
    result = evaluate_template(
        _template(metric=_ratio_metric(freshness_days=30)),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="housing_inventory",
                    record_id="inv-1",
                    observed_at=NOW - timedelta(days=45),
                    values={"installation": "JBSA", "available_units": 1250},
                ),
                SourceRecord(
                    feed_name="umd_authorizations",
                    record_id="umd-1",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "authorized_units": 1250},
                ),
            ],
        ),
    )

    metric = result.sections[0].metrics[0]
    assert metric.value == 1.0
    assert metric.health == "warn"
    assert metric.completeness == "stale_source"
    assert any("housing_inventory" in warning for warning in metric.warnings)


def test_optional_missing_source_is_incomplete_not_formula_error() -> None:
    metric_config = _ratio_metric()
    metric_config.required = False

    result = evaluate_template(
        _template(metric=metric_config),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="housing_inventory",
                    record_id="inv-1",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "available_units": 1120},
                )
            ],
        ),
    )

    metric = result.sections[0].metrics[0]
    assert metric.value is None
    assert metric.health == "incomplete"
    assert metric.completeness == "missing_source"
    assert any("umd_authorizations" in warning for warning in metric.warnings)


def test_weighted_mean_uses_matching_value_and_weight_records() -> None:
    metric_config = ScorecardMetricConfig(
        id="condition_index",
        label="Condition index",
        unit="score",
        housing_category="UH",
        inputs=[
            ScorecardMetricInputConfig(
                name="condition",
                source="record_feed",
                ref="facility_condition",
                field="score",
                filter={"category": "UH"},
            ),
            ScorecardMetricInputConfig(
                name="bed_count",
                source="record_feed",
                ref="facility_condition",
                field="beds",
                filter={"category": "UH"},
            ),
        ],
        formula=ScorecardFormulaConfig(
            operator="weighted_mean",
            value="condition",
            weight="bed_count",
        ),
        thresholds=ScorecardThresholdConfig(pass_min=80.0, warn_min=70.0),
        freshness_days=90,
    )

    result = evaluate_template(
        _template(metric=metric_config),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="facility_condition",
                    record_id="facility-1",
                    observed_at=NOW,
                    values={"category": "UH", "score": 90, "beds": 10},
                ),
                SourceRecord(
                    feed_name="facility_condition",
                    record_id="facility-2",
                    observed_at=NOW,
                    values={"category": "UH", "score": 70, "beds": 30},
                ),
            ],
        ),
    )

    metric = result.sections[0].metrics[0]
    assert metric.value == 75.0
    assert metric.health == "warn"
    assert metric.completeness == "complete"


def test_formula_error_isolated_to_one_metric() -> None:
    bad_metric = ScorecardMetricConfig(
        id="bad_ratio",
        label="Bad ratio",
        inputs=[
            ScorecardMetricInputConfig(
                name="numerator",
                source="record_feed",
                ref="housing_inventory",
                field="available_units",
            ),
            ScorecardMetricInputConfig(
                name="denominator",
                source="record_feed",
                ref="umd_authorizations",
                field="authorized_units",
            ),
        ],
        formula=ScorecardFormulaConfig(
            operator="ratio",
            numerator="missing",
            denominator="denominator",
        ),
        thresholds=ScorecardThresholdConfig(pass_min=0.95),
    )
    good_metric = _ratio_metric()
    template = ScorecardTemplateConfig(
        id="af-housing",
        name="Air Force housing scorecard",
        category="combined",
        scope="installation",
        period="monthly",
        sections=[
            ScorecardSectionConfig(
                id="supply-demand",
                label="Supply and demand",
                metrics=[bad_metric, good_metric],
            )
        ],
    )

    result = evaluate_template(
        template,
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="housing_inventory",
                    record_id="inv-1",
                    observed_at=NOW,
                    values={"installation": "JBSA", "available_units": 100},
                ),
                SourceRecord(
                    feed_name="umd_authorizations",
                    record_id="umd-1",
                    observed_at=NOW,
                    values={"installation": "JBSA", "authorized_units": 1250},
                ),
            ],
        ),
    )

    bad_result, good_result = result.sections[0].metrics
    assert bad_result.value is None
    assert bad_result.health == "incomplete"
    assert bad_result.completeness == "formula_error"
    assert good_result.value == 0.08
    assert good_result.health == "fail"
    assert good_result.completeness == "complete"


@pytest.mark.parametrize("raw_value", [nan, inf, -inf])
def test_non_finite_numeric_inputs_are_not_treated_as_complete_metrics(
    raw_value: float,
) -> None:
    result = evaluate_template(
        _template(metric=_sum_metric()),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="housing_inventory",
                    record_id="inv-1",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "available_units": raw_value},
                )
            ],
        ),
    )

    metric = result.sections[0].metrics[0]
    assert metric.value is None
    assert metric.health == "incomplete"
    assert metric.completeness == "missing_source"
    assert any("housing_inventory" in warning for warning in metric.warnings)


def _response_hours_metric(
    thresholds: ScorecardThresholdConfig,
) -> ScorecardMetricConfig:
    return ScorecardMetricConfig(
        id="maintenance_response_hours",
        label="Maintenance response hours",
        unit="hours",
        housing_category="combined",
        inputs=[
            ScorecardMetricInputConfig(
                name="response_hours",
                source="record_feed",
                ref="resident_experience",
                field="maintenance_response_hours",
            )
        ],
        formula=ScorecardFormulaConfig(operator="mean", value="response_hours"),
        thresholds=thresholds,
        freshness_days=30,
    )


def _evaluate_response_hours(
    thresholds: ScorecardThresholdConfig,
    value: float,
    *,
    observed_at: datetime | None = None,
) -> tuple[str, str]:
    result = evaluate_template(
        _template(metric=_response_hours_metric(thresholds)),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="resident_experience",
                    record_id="exp-1",
                    observed_at=observed_at or NOW - timedelta(days=1),
                    values={"maintenance_response_hours": value},
                )
            ],
        ),
    )
    metric = result.sections[0].metrics[0]
    return metric.health, metric.completeness


@pytest.mark.parametrize(
    ("value", "expected_health"),
    [(20.0, "pass"), (24.0, "pass"), (30.0, "warn"), (48.0, "warn"), (60.0, "fail")],
)
def test_lower_is_better_thresholds_grade_in_reverse(
    value: float, expected_health: str
) -> None:
    thresholds = ScorecardThresholdConfig(pass_max=24.0, warn_max=48.0)
    health, completeness = _evaluate_response_hours(thresholds, value)
    assert health == expected_health
    assert completeness == "complete"


@pytest.mark.parametrize(
    ("value", "expected_health"),
    [(10.0, "pass"), (72.0, "fail"), (100.0, "fail")],
)
def test_lower_is_better_fail_min_only_mirrors_fail_max_only(
    value: float, expected_health: str
) -> None:
    thresholds = ScorecardThresholdConfig(fail_min=72.0)
    health, _ = _evaluate_response_hours(thresholds, value)
    assert health == expected_health


def test_stale_source_downgrades_lower_is_better_pass_to_warn() -> None:
    thresholds = ScorecardThresholdConfig(pass_max=24.0, warn_max=48.0)
    health, completeness = _evaluate_response_hours(
        thresholds, 10.0, observed_at=NOW - timedelta(days=45)
    )
    assert health == "warn"
    assert completeness == "stale_source"


def test_threshold_directions_cannot_be_mixed() -> None:
    with pytest.raises(ValueError, match="cannot mix"):
        ScorecardThresholdConfig(pass_min=0.9, pass_max=24.0)
    with pytest.raises(ValueError, match="cannot mix"):
        ScorecardThresholdConfig(warn_min=0.8, fail_min=72.0)


def test_thresholds_require_at_least_one_bound() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ScorecardThresholdConfig()


def test_threshold_bounds_must_be_ordered_within_direction() -> None:
    with pytest.raises(ValueError, match="pass_min 0.8 must be >= warn_min 0.9"):
        ScorecardThresholdConfig(pass_min=0.8, warn_min=0.9)
    with pytest.raises(ValueError, match="pass_min 0.9 must be > fail_max 0.9"):
        ScorecardThresholdConfig(pass_min=0.9, fail_max=0.9)
    with pytest.raises(ValueError, match="warn_min 0.8 must be > fail_max 0.85"):
        ScorecardThresholdConfig(pass_min=0.9, warn_min=0.8, fail_max=0.85)
    with pytest.raises(ValueError, match="pass_max 48.0 must be <= warn_max 24.0"):
        ScorecardThresholdConfig(pass_max=48.0, warn_max=24.0)
    with pytest.raises(ValueError, match="pass_max 24.0 must be < fail_min 24.0"):
        ScorecardThresholdConfig(pass_max=24.0, fail_min=24.0)
    with pytest.raises(ValueError, match="warn_max 48.0 must be < fail_min 40.0"):
        ScorecardThresholdConfig(pass_max=24.0, warn_max=48.0, fail_min=40.0)
    # Coherent chains in both directions are accepted.
    ScorecardThresholdConfig(pass_min=1.0, warn_min=0.9, fail_max=0.89)
    ScorecardThresholdConfig(pass_max=0.20, warn_max=0.25, fail_min=0.2501)


def _partial_input_metric(*, incomplete_when_missing: bool) -> ScorecardMetricConfig:
    """Optional metric whose formula uses only one of its two inputs."""

    return ScorecardMetricConfig(
        id="partial_metric",
        label="Partial metric",
        unit="units",
        housing_category="combined",
        required=False,
        inputs=[
            ScorecardMetricInputConfig(
                name="supply",
                source="record_feed",
                ref="housing_inventory",
                field="available_units",
            ),
            ScorecardMetricInputConfig(
                name="context",
                source="record_feed",
                ref="umd_authorizations",
                field="authorized_units",
            ),
        ],
        formula=ScorecardFormulaConfig(operator="mean", value="supply"),
        thresholds=ScorecardThresholdConfig(
            pass_min=1.0,
            warn_min=0.0,
            incomplete_when_missing=incomplete_when_missing,
        ),
        freshness_days=30,
    )


def _supply_only_records() -> list[SourceRecord]:
    return [
        SourceRecord(
            feed_name="housing_inventory",
            record_id="inv-1",
            observed_at=NOW - timedelta(days=1),
            values={"available_units": 100},
        )
    ]


def test_incomplete_when_missing_true_marks_optional_metric_incomplete() -> None:
    result = evaluate_template(
        _template(metric=_partial_input_metric(incomplete_when_missing=True)),
        ScorecardEvalState(as_of=NOW, records=_supply_only_records()),
    )
    metric = result.sections[0].metrics[0]
    assert metric.value is None
    assert metric.health == "incomplete"
    assert metric.completeness == "missing_source"
    assert any("umd_authorizations" in warning for warning in metric.warnings)


def test_incomplete_when_missing_false_grades_computable_partial_data() -> None:
    result = evaluate_template(
        _template(metric=_partial_input_metric(incomplete_when_missing=False)),
        ScorecardEvalState(as_of=NOW, records=_supply_only_records()),
    )
    metric = result.sections[0].metrics[0]
    assert metric.value == 100.0
    assert metric.health == "pass"
    assert metric.completeness == "complete"
    # The missing-input warning is retained even though grading proceeded.
    assert any("umd_authorizations" in warning for warning in metric.warnings)


def test_finite_inputs_that_overflow_formula_are_reported_as_formula_error() -> None:
    result = evaluate_template(
        _template(metric=_sum_metric()),
        ScorecardEvalState(
            as_of=NOW,
            records=[
                SourceRecord(
                    feed_name="housing_inventory",
                    record_id="inv-1",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "available_units": 1e308},
                ),
                SourceRecord(
                    feed_name="housing_inventory",
                    record_id="inv-2",
                    observed_at=NOW - timedelta(days=1),
                    values={"installation": "JBSA", "available_units": 1e308},
                ),
            ],
        ),
    )

    metric = result.sections[0].metrics[0]
    assert metric.value is None
    assert metric.health == "incomplete"
    assert metric.completeness == "formula_error"
    assert any("non-finite" in warning.lower() for warning in metric.warnings)
