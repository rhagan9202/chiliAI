"""Tests for the scorecards API router."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_scorecard_service
from api.routers.scorecards import router
from scorecards.exceptions import (
    ScorecardExportNotFoundError,
    ScorecardRunNotFoundError,
    ScorecardTemplateNotFoundError,
)
from scorecards.models import (
    ScorecardCitation,
    ScorecardExportFormat,
    ScorecardMetricResult,
    ScorecardRun,
    ScorecardSectionResult,
)
from scorecards.service_models import (
    ScorecardExportResponse,
    ScorecardGenerateRequest,
    ScorecardRunListRequest,
    ScorecardRunListResponse,
    ScorecardTemplateListResponse,
    ScorecardTemplateSummary,
)


class StubScorecardService:
    """Small scorecard service double that records router request models."""

    def __init__(self) -> None:
        self.generate_request: ScorecardGenerateRequest | None = None
        self.list_request: ScorecardRunListRequest | None = None
        self.get_request: tuple[str, str] | None = None
        self.export_request: tuple[str, str, ScorecardExportFormat] | None = None
        self.run = _scorecard_run("run-1")

    def list_templates(self) -> ScorecardTemplateListResponse:
        return ScorecardTemplateListResponse(
            items=[
                ScorecardTemplateSummary(
                    id="uh_scorecard",
                    name="Unaccompanied Housing",
                    category="UH",
                    scope="installation",
                    period="monthly",
                )
            ]
        )

    def generate(self, request: ScorecardGenerateRequest) -> ScorecardRun:
        self.generate_request = request
        if request.template_id == "missing-template":
            raise ScorecardTemplateNotFoundError(request.template_id)
        return self.run.model_copy(
            update={
                "knowledge_base_id": request.knowledge_base_id,
                "template_id": request.template_id,
                "scope_type": request.scope_type,
                "scope_id": request.scope_id,
                "period_start": request.period_start,
                "period_end": request.period_end,
            }
        )

    def list_runs(self, request: ScorecardRunListRequest) -> ScorecardRunListResponse:
        self.list_request = request
        return ScorecardRunListResponse(items=[self.run], total=1)

    def get_run(self, *, knowledge_base_id: str, run_id: str) -> ScorecardRun:
        self.get_request = (knowledge_base_id, run_id)
        if run_id == "missing-run":
            raise ScorecardRunNotFoundError(knowledge_base_id, run_id)
        return self.run

    def export_run(
        self,
        *,
        knowledge_base_id: str,
        run_id: str,
        format: ScorecardExportFormat,
    ) -> ScorecardExportResponse:
        self.export_request = (knowledge_base_id, run_id, format)
        if run_id == "missing-run":
            raise ScorecardRunNotFoundError(knowledge_base_id, run_id)
        if format == "markdown":
            raise ScorecardExportNotFoundError(run_id, format)
        return ScorecardExportResponse(run_id=run_id, format=format, content='{"ok": true}')


def _client(service: StubScorecardService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_scorecard_service] = lambda: service
    return TestClient(app)


def _scorecard_run(run_id: str) -> ScorecardRun:
    now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    return ScorecardRun(
        id=run_id,
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        template_name="Unaccompanied Housing",
        scope_type="installation",
        scope_id="base-1",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source_snapshot_hash="snapshot-1",
        status="generated",
        overall_health="warn",
        sections=[
            ScorecardSectionResult(
                id="readiness",
                label="Readiness",
                metrics=[
                    ScorecardMetricResult(
                        id="occupancy_rate",
                        label="Occupancy Rate",
                        description="Percent occupied",
                        unit="percent",
                        housing_category="UH",
                        value=91.2,
                        health="warn",
                        completeness="complete",
                        citations=[
                            ScorecardCitation(
                                citation_id="cite-1",
                                feed_name="housing",
                                record_id="record-1",
                                field="occupancy_rate",
                            )
                        ],
                        warnings=["Below target"],
                    )
                ],
            )
        ],
        export_payloads={"json": "{\"internal\": true}", "markdown": "# Internal\n"},
        created_at=now,
        updated_at=now,
    )


def test_list_templates_returns_configured_templates() -> None:
    client = _client(StubScorecardService())

    response = client.get("/scorecards/templates")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "uh_scorecard",
                "name": "Unaccompanied Housing",
                "category": "UH",
                "scope": "installation",
                "period": "monthly",
            }
        ]
    }


def test_generate_run_maps_request_and_hides_export_payloads() -> None:
    service = StubScorecardService()
    client = _client(service)

    response = client.post(
        "/scorecards/runs",
        json={
            "knowledge_base_id": "kb-2",
            "template_id": "uh_scorecard",
            "scope_type": "installation",
            "scope_id": "base-2",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb-2"
    assert payload["template_id"] == "uh_scorecard"
    assert payload["sections"][0]["metrics"][0]["metric_id"] == "occupancy_rate"
    assert payload["sections"][0]["metrics"][0]["citations"][0]["citation_id"] == "cite-1"
    assert "export_payloads" not in payload
    assert service.generate_request == ScorecardGenerateRequest(
        knowledge_base_id="kb-2",
        template_id="uh_scorecard",
        scope_type="installation",
        scope_id="base-2",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )


def test_generate_missing_template_returns_404() -> None:
    response = _client(StubScorecardService()).post(
        "/scorecards/runs",
        json={
            "knowledge_base_id": "kb-1",
            "template_id": "missing-template",
            "scope_type": "installation",
            "scope_id": "base-1",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Scorecard template 'missing-template' was not found."


def test_list_runs_forwards_filters_and_pagination() -> None:
    service = StubScorecardService()
    client = _client(service)

    response = client.get(
        "/scorecards/runs",
        params={
            "knowledge_base_id": "kb-1",
            "template_id": "uh_scorecard",
            "status": "generated",
            "limit": 10,
            "offset": 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 20
    assert payload["items"][0]["id"] == "run-1"
    assert service.list_request == ScorecardRunListRequest(
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        status="generated",
        limit=10,
        offset=20,
    )


def test_get_run_uses_knowledge_base_scope() -> None:
    service = StubScorecardService()
    client = _client(service)

    response = client.get("/scorecards/runs/run-1", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    assert response.json()["id"] == "run-1"
    assert service.get_request == ("kb-1", "run-1")


def test_missing_run_returns_404() -> None:
    response = _client(StubScorecardService()).get(
        "/scorecards/runs/missing-run", params={"knowledge_base_id": "kb-1"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Scorecard run 'missing-run' was not found for knowledge base 'kb-1'."
    )


def test_export_run_returns_stored_content() -> None:
    service = StubScorecardService()
    client = _client(service)

    response = client.get(
        "/scorecards/runs/run-1/export",
        params={"knowledge_base_id": "kb-1", "format": "json"},
    )

    assert response.status_code == 200
    assert response.json() == {"run_id": "run-1", "format": "json", "content": "{\"ok\": true}"}
    assert service.export_request == ("kb-1", "run-1", cast(ScorecardExportFormat, "json"))


def test_missing_export_returns_404() -> None:
    response = _client(StubScorecardService()).get(
        "/scorecards/runs/run-1/export",
        params={"knowledge_base_id": "kb-1", "format": "markdown"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Scorecard run 'run-1' does not have a 'markdown' export."
