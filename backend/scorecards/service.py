"""Application service for durable scorecard run workflows."""

from __future__ import annotations

import hashlib
import json

from config.schema import DomainConfig, ScorecardTemplateConfig
from scorecards.adapters.protocols import ScorecardRunRepository
from scorecards.evaluation import ScorecardEvalState, evaluate_template
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

__all__ = ["ScorecardService", "create_scorecard_service"]


class ScorecardService:
    """Coordinates template lookup, pure evaluation, exports, and persistence."""

    def __init__(
        self, *, config: DomainConfig, repository: ScorecardRunRepository
    ) -> None:
        self._config = config
        self._repository = repository

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
        evaluation = evaluate_template(template, ScorecardEvalState(records=[]))
        now = utc_now()
        snapshot_hash = _source_snapshot_hash(request)
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
    config: DomainConfig, repository: ScorecardRunRepository
) -> ScorecardService:
    return ScorecardService(config=config, repository=repository)


def _source_snapshot_hash(request: ScorecardGenerateRequest) -> str:
    payload = {
        "knowledge_base_id": request.knowledge_base_id,
        "template_id": request.template_id,
        "scope_type": request.scope_type,
        "scope_id": request.scope_id,
        "period_start": request.period_start.isoformat(),
        "period_end": request.period_end.isoformat(),
        "version": 1,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


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
