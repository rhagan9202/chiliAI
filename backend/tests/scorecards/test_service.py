from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from config.loader import load_config
from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.exceptions import (
    ScorecardExportNotFoundError,
    ScorecardRunNotFoundError,
    ScorecardTemplateNotFoundError,
)
from scorecards.models import ScorecardExportFormat
from scorecards.service import ScorecardService
from scorecards.service_models import ScorecardGenerateRequest, ScorecardRunListRequest


CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "defaults"
    / "department_air_force_housing.yaml"
)


def _service() -> tuple[ScorecardService, InMemoryScorecardRunRepository]:
    repo = InMemoryScorecardRunRepository()
    return ScorecardService(config=load_config(CONFIG_PATH), repository=repo), repo


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
    assert "## Demand And Supply" in markdown
    assert "- UH Supply Ratio: incomplete" in markdown
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
