"""Pure scorecard template evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from pydantic import BaseModel, Field

from config.schema import (
    ScorecardFormulaConfig,
    ScorecardMetricConfig,
    ScorecardMetricInputConfig,
    ScorecardTemplateConfig,
)
from scorecards.exceptions import ScorecardFormulaError
from scorecards.models import (
    ScorecardCitation,
    ScorecardCompleteness,
    ScorecardHealth,
    ScorecardMetricResult,
    ScorecardRun,
    ScorecardSectionResult,
)
from shared.utils import utc_now

SourceValue = str | float | int | bool | None


class SourceRecord(BaseModel):
    """One normalized source record available to the evaluator."""

    feed_name: str
    record_id: str
    values: dict[str, SourceValue] = Field(default_factory=dict)
    observed_at: datetime | None = None


class ScorecardEvalState(BaseModel):
    """All source data for one pure scorecard evaluation."""

    as_of: datetime = Field(default_factory=utc_now)
    records: list[SourceRecord] = Field(
        default_factory=lambda: cast(list[SourceRecord], [])
    )


@dataclass(frozen=True)
class _InputValue:
    value: float
    citation: ScorecardCitation
    observed_at: datetime | None


@dataclass(frozen=True)
class _InputSelection:
    values: list[_InputValue]
    missing_warning: str | None
    stale_warnings: list[str]


def evaluate_template(
    template: ScorecardTemplateConfig,
    state: ScorecardEvalState,
) -> ScorecardRun:
    """Evaluate a scorecard template against already-loaded source records."""

    sections = [
        ScorecardSectionResult(
            id=section.id,
            label=section.label,
            metrics=[_evaluate_metric(metric, state) for metric in section.metrics],
        )
        for section in template.sections
    ]
    return ScorecardRun(
        template_id=template.id,
        template_name=template.name,
        category=template.category,
        scope=template.scope,
        period=template.period,
        health=_overall_health(sections),
        export_formats=list(template.export_formats),
        sections=sections,
        evaluated_at=state.as_of,
    )


def _evaluate_metric(
    metric: ScorecardMetricConfig,
    state: ScorecardEvalState,
) -> ScorecardMetricResult:
    selections = {
        input_config.name: _select_input(input_config, metric, state)
        for input_config in metric.inputs
    }
    missing = [
        selection.missing_warning
        for selection in selections.values()
        if selection.missing_warning is not None
    ]
    stale_warnings = [
        warning
        for selection in selections.values()
        for warning in selection.stale_warnings
    ]

    if missing and metric.required:
        return _metric_result(
            metric,
            value=None,
            health="incomplete",
            completeness="missing_source",
            citations=_citations(selections),
            warnings=missing,
        )

    try:
        value = _evaluate_formula(metric.formula, selections)
        health = _classify_health(metric, value)
        completeness: ScorecardCompleteness = "complete"
        warnings = list(missing)
        if stale_warnings:
            completeness = "stale_source"
            warnings.extend(stale_warnings)
            if health == "pass":
                health = "warn"
    except ScorecardFormulaError as exc:
        return _metric_result(
            metric,
            value=None,
            health="incomplete",
            completeness="formula_error",
            citations=_citations(selections),
            warnings=[str(exc)],
        )

    return _metric_result(
        metric,
        value=value,
        health=health,
        completeness=completeness,
        citations=_citations(selections),
        warnings=warnings,
    )


def _metric_result(
    metric: ScorecardMetricConfig,
    *,
    value: float | None,
    health: ScorecardHealth,
    completeness: ScorecardCompleteness,
    citations: list[ScorecardCitation],
    warnings: list[str],
) -> ScorecardMetricResult:
    return ScorecardMetricResult(
        id=metric.id,
        label=metric.label,
        description=metric.description,
        unit=metric.unit,
        housing_category=metric.housing_category,
        value=None if value is None else round(value, 3),
        health=health,
        completeness=completeness,
        citations=citations,
        warnings=warnings,
    )


def _select_input(
    input_config: ScorecardMetricInputConfig,
    metric: ScorecardMetricConfig,
    state: ScorecardEvalState,
) -> _InputSelection:
    if input_config.source != "record_feed":
        return _InputSelection(
            values=[],
            missing_warning=(
                f"Input '{input_config.name}' uses unsupported source "
                f"'{input_config.source}'."
            ),
            stale_warnings=[],
        )
    if input_config.field is None:
        return _InputSelection(
            values=[],
            missing_warning=(
                f"Record feed input '{input_config.name}' for "
                f"{input_config.ref} is missing a field."
            ),
            stale_warnings=[],
        )

    records = [
        record
        for record in state.records
        if record.feed_name == input_config.ref
        and _matches_filter(record, input_config.filter)
    ]
    values: list[_InputValue] = []
    stale_warnings: list[str] = []
    for record in records:
        raw_value = record.values.get(input_config.field)
        numeric_value = _as_float(raw_value)
        if numeric_value is None:
            continue
        citation = ScorecardCitation(
            citation_id=f"{record.feed_name}:{record.record_id}",
            feed_name=record.feed_name,
            record_id=record.record_id,
            field=input_config.field,
        )
        values.append(
            _InputValue(
                value=numeric_value,
                citation=citation,
                observed_at=record.observed_at,
            )
        )
        if _is_stale(record.observed_at, metric.freshness_days, state.as_of):
            stale_warnings.append(
                f"Source {record.feed_name}:{record.record_id} is older than "
                f"{metric.freshness_days} days."
            )

    missing_warning = (
        f"Missing required source records for {input_config.ref}."
        if not values
        else None
    )
    return _InputSelection(
        values=values,
        missing_warning=missing_warning,
        stale_warnings=stale_warnings,
    )


def _evaluate_formula(
    formula: ScorecardFormulaConfig,
    selections: dict[str, _InputSelection],
) -> float:
    if formula.operator == "ratio":
        numerator = _sum_input(_required_input(formula.numerator, selections))
        denominator = _sum_input(_required_input(formula.denominator, selections))
        if denominator == 0:
            raise ScorecardFormulaError("Ratio denominator is zero.")
        return numerator / denominator
    if formula.operator == "sum":
        return _sum_input(_required_input(formula.value, selections))
    if formula.operator == "mean":
        values = _required_values(formula.value, selections)
        return sum(value.value for value in values) / len(values)
    if formula.operator == "latest":
        values = _required_values(formula.value, selections)
        return _latest_value(values).value
    if formula.operator == "weighted_mean":
        value_selection = _required_input(formula.value, selections)
        weight_selection = _required_input(formula.weight, selections)
        return _weighted_mean(value_selection, weight_selection)

    raise ScorecardFormulaError(
        f"Unhandled scorecard formula operator: {formula.operator}"
    )


def _required_input(
    input_name: str | None,
    selections: dict[str, _InputSelection],
) -> _InputSelection:
    if input_name is None:
        raise ScorecardFormulaError("Formula is missing an input reference.")
    try:
        return selections[input_name]
    except KeyError as exc:
        raise ScorecardFormulaError(
            f"Formula references unknown input '{input_name}'."
        ) from exc


def _required_values(
    input_name: str | None,
    selections: dict[str, _InputSelection],
) -> list[_InputValue]:
    selected = _required_input(input_name, selections).values
    if not selected:
        raise ScorecardFormulaError(f"Formula input '{input_name}' has no values.")
    return selected


def _sum_input(selection: _InputSelection) -> float:
    if not selection.values:
        raise ScorecardFormulaError("Formula input has no values.")
    return sum(value.value for value in selection.values)


def _latest_value(values: list[_InputValue]) -> _InputValue:
    return max(
        enumerate(values),
        key=lambda item: (_observed_sort_key(item[1]), item[0]),
    )[1]


def _observed_sort_key(value: _InputValue) -> datetime:
    if value.observed_at is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.observed_at.tzinfo is None:
        return value.observed_at.replace(tzinfo=UTC)
    return value.observed_at


def _weighted_mean(
    value_selection: _InputSelection,
    weight_selection: _InputSelection,
) -> float:
    values_by_citation = {
        value.citation.citation_id: value.value for value in value_selection.values
    }
    weights_by_citation = {
        weight.citation.citation_id: weight.value for weight in weight_selection.values
    }
    shared_citations = sorted(values_by_citation.keys() & weights_by_citation.keys())
    if not shared_citations:
        raise ScorecardFormulaError("Weighted mean has no matched value/weight pairs.")
    total_weight = sum(weights_by_citation[citation_id] for citation_id in shared_citations)
    if total_weight == 0:
        raise ScorecardFormulaError("Weighted mean total weight is zero.")
    weighted_sum = sum(
        values_by_citation[citation_id] * weights_by_citation[citation_id]
        for citation_id in shared_citations
    )
    return weighted_sum / total_weight


def _classify_health(
    metric: ScorecardMetricConfig,
    value: float,
) -> ScorecardHealth:
    thresholds = metric.thresholds
    if thresholds.pass_min is not None and value >= thresholds.pass_min:
        return "pass"
    if thresholds.warn_min is not None and value >= thresholds.warn_min:
        return "warn"
    if thresholds.fail_max is not None and value <= thresholds.fail_max:
        return "fail"
    if thresholds.pass_min is not None or thresholds.warn_min is not None:
        return "fail"
    return "pass"


def _overall_health(sections: list[ScorecardSectionResult]) -> ScorecardHealth:
    metric_health = [
        metric.health for section in sections for metric in section.metrics
    ]
    if not metric_health:
        return "pass"
    for health in ("incomplete", "fail", "warn"):
        if health in metric_health:
            return cast(ScorecardHealth, health)
    return "pass"


def _citations(
    selections: dict[str, _InputSelection],
) -> list[ScorecardCitation]:
    seen: set[str] = set()
    citations: list[ScorecardCitation] = []
    for selection in selections.values():
        for value in selection.values:
            if value.citation.citation_id in seen:
                continue
            seen.add(value.citation.citation_id)
            citations.append(value.citation)
    return citations


def _matches_filter(
    record: SourceRecord,
    filters: dict[str, str | float | int | bool],
) -> bool:
    return all(record.values.get(key) == expected for key, expected in filters.items())


def _is_stale(
    observed_at: datetime | None,
    freshness_days: int,
    as_of: datetime,
) -> bool:
    if observed_at is None:
        return False
    return observed_at < as_of - timedelta(days=freshness_days)


def _as_float(value: SourceValue) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)
    except ValueError:
        return None


__all__ = [
    "ScorecardEvalState",
    "SourceRecord",
    "SourceValue",
    "evaluate_template",
]
