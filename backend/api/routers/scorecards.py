"""Scorecard API endpoints for Air Force housing dashboards."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query

from api.contracts import (
    ScorecardCitationResponse,
    ScorecardExportResponse,
    ScorecardMetricResponse,
    ScorecardRunGenerateRequest,
    ScorecardRunListResponse,
    ScorecardRunResponse,
    ScorecardSectionResponse,
    ScorecardTemplateListResponse,
    ScorecardTemplateResponse,
)
from api.dependencies import get_scorecard_service
from api.middleware.rbac import require_role
from scorecards.exceptions import (
    ScorecardExportNotFoundError,
    ScorecardRunNotFoundError,
    ScorecardTemplateNotFoundError,
)
from scorecards.models import (
    ScorecardExportFormat,
    ScorecardRun,
    ScorecardRunStatus,
)
from scorecards.service import ScorecardService
from scorecards.service_models import (
    ScorecardGenerateRequest,
    ScorecardRunListRequest,
)

__all__ = ["router"]


TemplateCategory = Literal["UH", "MFH", "combined"]
TemplateScope = Literal["enterprise", "majcom", "region", "installation", "market_area"]
TemplatePeriod = Literal["monthly", "quarterly", "annual", "ad_hoc"]

router = APIRouter(prefix="/scorecards", tags=["scorecards"])


@router.get(
    "/templates",
    response_model=ScorecardTemplateListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_templates(
    service: ScorecardService = Depends(get_scorecard_service),
) -> ScorecardTemplateListResponse:
    """Return configured scorecard templates."""
    response = service.list_templates()
    return ScorecardTemplateListResponse(
        items=[
            ScorecardTemplateResponse(
                id=item.id,
                name=item.name,
                category=cast(TemplateCategory, item.category),
                scope=cast(TemplateScope, item.scope),
                period=cast(TemplatePeriod, item.period),
            )
            for item in response.items
        ]
    )


@router.post(
    "/runs",
    response_model=ScorecardRunResponse,
    dependencies=[Depends(require_role("analyst"))],
)
def generate_run(
    payload: ScorecardRunGenerateRequest,
    service: ScorecardService = Depends(get_scorecard_service),
) -> ScorecardRunResponse:
    """Generate and persist a scorecard run."""
    try:
        run = service.generate(
            ScorecardGenerateRequest(
                knowledge_base_id=payload.knowledge_base_id,
                template_id=payload.template_id,
                scope_type=payload.scope_type,
                scope_id=payload.scope_id,
                period_start=payload.period_start,
                period_end=payload.period_end,
            )
        )
    except ScorecardTemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _run_response(run)


@router.get(
    "/runs",
    response_model=ScorecardRunListResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def list_runs(
    knowledge_base_id: str = Query(..., min_length=1),
    template_id: str | None = Query(default=None),
    status: ScorecardRunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ScorecardService = Depends(get_scorecard_service),
) -> ScorecardRunListResponse:
    """Return scorecard runs scoped to one knowledge base."""
    request = ScorecardRunListRequest(
        knowledge_base_id=knowledge_base_id,
        template_id=template_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    response = service.list_runs(request)
    return ScorecardRunListResponse(
        items=[_run_response(run) for run in response.items],
        total=response.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/runs/{run_id}",
    response_model=ScorecardRunResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def get_run(
    run_id: str,
    knowledge_base_id: str = Query(..., min_length=1),
    service: ScorecardService = Depends(get_scorecard_service),
) -> ScorecardRunResponse:
    """Return one scorecard run by ID and knowledge-base scope."""
    try:
        return _run_response(service.get_run(knowledge_base_id=knowledge_base_id, run_id=run_id))
    except ScorecardRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/runs/{run_id}/export",
    response_model=ScorecardExportResponse,
    dependencies=[Depends(require_role("viewer"))],
)
def export_run(
    run_id: str,
    knowledge_base_id: str = Query(..., min_length=1),
    format: ScorecardExportFormat = Query(default="json"),
    service: ScorecardService = Depends(get_scorecard_service),
) -> ScorecardExportResponse:
    """Return a stored JSON or Markdown export for one scorecard run."""
    try:
        response = service.export_run(
            knowledge_base_id=knowledge_base_id,
            run_id=run_id,
            format=format,
        )
    except (ScorecardRunNotFoundError, ScorecardExportNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScorecardExportResponse(
        run_id=response.run_id,
        format=response.format,
        content=response.content,
    )


def _run_response(run: ScorecardRun) -> ScorecardRunResponse:
    return ScorecardRunResponse(
        id=run.id,
        knowledge_base_id=run.knowledge_base_id,
        template_id=run.template_id,
        template_name=run.template_name,
        scope_type=run.scope_type,
        scope_id=run.scope_id,
        period_start=run.period_start,
        period_end=run.period_end,
        source_snapshot_hash=run.source_snapshot_hash,
        status=run.status,
        overall_health=run.overall_health,
        sections=[
            ScorecardSectionResponse(
                id=section.id,
                label=section.label,
                metrics=[
                    ScorecardMetricResponse(
                        metric_id=metric.id,
                        label=metric.label,
                        description=metric.description,
                        unit=metric.unit,
                        housing_category=metric.housing_category,
                        value=metric.value,
                        health=metric.health,
                        completeness=metric.completeness,
                        citations=[
                            ScorecardCitationResponse(
                                citation_id=citation.citation_id,
                                feed_name=citation.feed_name,
                                record_id=citation.record_id,
                                field=citation.field,
                            )
                            for citation in metric.citations
                        ],
                        warnings=metric.warnings,
                    )
                    for metric in section.metrics
                ],
            )
            for section in run.sections
        ],
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
