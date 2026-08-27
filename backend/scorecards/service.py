"""Application service for durable scorecard run workflows."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol, runtime_checkable

from config.schema import DomainConfig, ScorecardTemplateConfig
from scorecards.adapters.protocols import ScorecardRunRepository
from scorecards.evaluation import ScorecardEvalState, SourceRecord, evaluate_template
from scorecards.exceptions import (
    ScorecardExportNotFoundError,
    ScorecardRunNotFoundError,
    ScorecardTemplateNotFoundError,
)
from scorecards.models import ScorecardExportFormat, ScorecardRun
from scorecards.service_models import (
    ScorecardExportResponse,
    ScorecardGenerateRequest,
    ScorecardRunListRequest,
    ScorecardRunListResponse,
    ScorecardTemplateListResponse,
    ScorecardTemplateSummary,
)
from shared.utils import utc_now

__all__ = [
    "ScorecardService",
    "ScorecardSourceRecordLoader",
    "create_scorecard_service",
]


@runtime_checkable
class ScorecardSourceRecordLoader(Protocol):
    """Read boundary supplying a knowledge base's ingested feed records.

    Implemented outside this module (the API gateway bridges the records
    store through this protocol) so scorecards never import other backend
    modules directly.
    """

    def load_source_records(self, knowledge_base_id: str) -> list[SourceRecord]:
        """Return every ingested record for the KB as evaluator source records."""
        ...


class ScorecardService:
    """Coordinates template lookup, pure evaluation, exports, and persistence."""

    def __init__(
        self,
        *,
        config: DomainConfig,
        repository: ScorecardRunRepository,
        record_source: ScorecardSourceRecordLoader | None = None,
    ) -> None:
        self._config = config
        self._repository = repository
        self._record_source = record_source

    def list_templates(self) -> ScorecardTemplateListResponse:
        return ScorecardTemplateListResponse(
            items=[
                ScorecardTemplateSummary(
                    id=template.id,
                    name=template.name,
                    category=template.category,
                    scope=template.scope,
                    period=template.period,
                )
                for template in self._config.scorecards.templates
            ]
        )

    def get_template(self, template_id: str) -> ScorecardTemplateConfig:
        for template in self._config.scorecards.templates:
            if template.id == template_id:
                return template
        raise ScorecardTemplateNotFoundError(template_id)

    def generate(self, request: ScorecardGenerateRequest) -> ScorecardRun:
        template = self.get_template(request.template_id)
        records = self._select_records(request)
        evaluation = evaluate_template(template, ScorecardEvalState(records=records))
        now = utc_now()
        snapshot_hash = _source_snapshot_hash(request, records, template)
        run = ScorecardRun(
            id=_run_id(snapshot_hash),
            knowledge_base_id=request.knowledge_base_id,
            template_id=template.id,
            template_name=template.name,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            period_start=request.period_start,
            period_end=request.period_end,
            source_snapshot_hash=snapshot_hash,
            status="generated",
            overall_health=evaluation.overall_health,
            sections=evaluation.sections,
            created_at=now,
            updated_at=now,
        )
        run = run.model_copy(
            update={
                "export_payloads": {
                    "json": _render_json(run),
                    "markdown": _render_markdown(run),
                }
            }
        )
        return self._repository.upsert(run)

    def _select_records(
        self, request: ScorecardGenerateRequest
    ) -> list[SourceRecord]:
        """Return the KB's ingested records narrowed to the requested run.

        Scope: ``scope_type == "installation"`` keeps only records whose
        ``installation_id`` value matches ``scope_id`` — every housing feed
        carries that column. Broader scopes (enterprise, majcom, region,
        market_area) evaluate the full KB record set; the feeds do not carry
        a reliable roll-up key for them, so narrowing there would silently
        drop data.

        Period: records dated via ``observed_at`` (the feed's snapshot date)
        must fall inside ``[period_start, period_end]``. Undated records are
        kept — the evaluator's freshness check is the authority on staleness.
        """
        if self._record_source is None:
            return []
        records = self._record_source.load_source_records(request.knowledge_base_id)
        selected: list[SourceRecord] = []
        for record in records:
            if (
                request.scope_type == "installation"
                and record.values.get("installation_id") != request.scope_id
            ):
                continue
            if record.observed_at is not None:
                observed = record.observed_at.date()
                if observed < request.period_start or observed > request.period_end:
                    continue
            selected.append(record)
        return selected

    def list_runs(self, request: ScorecardRunListRequest) -> ScorecardRunListResponse:
        items, total = self._repository.list(
            knowledge_base_id=request.knowledge_base_id,
            template_id=request.template_id,
            status=request.status,
            limit=request.limit,
            offset=request.offset,
        )
        return ScorecardRunListResponse(items=items, total=total)

    def get_run(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun:
        run = self._repository.get(knowledge_base_id=knowledge_base_id, run_id=run_id)
        if run is None:
            raise ScorecardRunNotFoundError(knowledge_base_id, run_id)
        return run

    def export_run(
        self,
        *,
        knowledge_base_id: str,
        run_id: str,
        format: ScorecardExportFormat,
    ) -> ScorecardExportResponse:
        run = self.get_run(knowledge_base_id=knowledge_base_id, run_id=run_id)
        content = run.export_payloads.get(format)
        if content is None:
            raise ScorecardExportNotFoundError(run_id, format)
        return ScorecardExportResponse(run_id=run_id, format=format, content=content)


def create_scorecard_service(
    config: DomainConfig,
    repository: ScorecardRunRepository,
    record_source: ScorecardSourceRecordLoader | None = None,
) -> ScorecardService:
    return ScorecardService(
        config=config, repository=repository, record_source=record_source
    )


def _source_snapshot_hash(
    request: ScorecardGenerateRequest,
    records: list[SourceRecord],
    template: ScorecardTemplateConfig,
) -> str:
    """Fingerprint the run request, the records evaluated, and the template.

    Including per-record content digests means re-generating after new or
    changed source data produces a new run id, while an identical request
    over identical data stays idempotent.

    The template is fingerprinted too because the grades are a function of it:
    without it, retuning a threshold and re-running over unchanged records
    reuses the run computed under the *old* thresholds and silently returns
    the grade the change was meant to alter.
    """
    record_digests = sorted(
        f"{record.feed_name}:{record.record_id}:{_record_values_digest(record)}"
        for record in records
    )
    payload = {
        "knowledge_base_id": request.knowledge_base_id,
        "template_id": request.template_id,
        "scope_type": request.scope_type,
        "scope_id": request.scope_id,
        "period_start": request.period_start.isoformat(),
        "period_end": request.period_end.isoformat(),
        "records": record_digests,
        "template": _template_digest(template),
        "version": 2,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _template_digest(template: ScorecardTemplateConfig) -> str:
    """Content hash of the template definition the grades were computed from."""
    canonical = template.model_dump_json(by_alias=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _record_values_digest(record: SourceRecord) -> str:
    canonical = json.dumps(
        record.values, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _run_id(source_snapshot_hash: str) -> str:
    return f"scorecard-run-{source_snapshot_hash[:24]}"


def _render_json(run: ScorecardRun) -> str:
    return run.model_dump_json()


def _render_markdown(run: ScorecardRun) -> str:
    lines = [
        f"# {run.template_name}",
        "",
        f"Scope: {run.scope_type} {run.scope_id}",
        f"Period: {run.period_start.isoformat()} to {run.period_end.isoformat()}",
        f"Overall Health: {run.overall_health}",
        "",
    ]
    for section in run.sections:
        lines.extend([f"## {section.label}", ""])
        for metric in section.metrics:
            value = "n/a" if metric.value is None else str(metric.value)
            lines.append(
                f"- {metric.label}: {metric.health} "
                f"(value: {value}, completeness: {metric.completeness})"
            )
            for warning in metric.warnings:
                lines.append(f"  - Warning: {warning}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
