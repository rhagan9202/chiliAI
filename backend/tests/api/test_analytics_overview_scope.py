"""`build_analytics_overview` can be scoped to one knowledge base (UXA-408).

The dashboard's four KPI tiles reported workspace-wide totals while every
other panel on the page was scoped to the active knowledge base. The numbers
agreed only because a single KB held all the data.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api._analytics_overview import build_analytics_overview
from cases.adapters.in_memory import InMemoryCaseRepository
from cases.service import CaseService
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.models import AlertHistoryRecord
from shared.types import KnowledgeBase
from shared.utils import utc_now


def _alert(alert_id: str, *, knowledge_base_id: str, severity: str = "high") -> AlertHistoryRecord:
    return AlertHistoryRecord(
        knowledge_base_id=knowledge_base_id,
        alert_id=alert_id,
        entity_id="provider-1",
        entity_type="provider",
        severity=severity,
        status="open",
        title="Outlier billing",
        reasoning="Above peers.",
        metric_name="billing",
        confidence=0.9,
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )


@pytest.fixture
def stores() -> tuple[InMemoryAlertHistoryWriter, CaseService, InMemoryKnowledgeBaseRepository]:
    kb_repository = InMemoryKnowledgeBaseRepository()
    kb_repository.create(
        KnowledgeBase(id="kb-1", name="One", description="", entity_count=10, created_at=utc_now())
    )
    kb_repository.create(
        KnowledgeBase(id="kb-2", name="Two", description="", entity_count=4, created_at=utc_now())
    )

    alert_store = InMemoryAlertHistoryWriter()
    alert_store.write_alerts(
        [
            _alert("a-1", knowledge_base_id="kb-1", severity="critical"),
            _alert("a-2", knowledge_base_id="kb-1", severity="low"),
            _alert("a-3", knowledge_base_id="kb-2", severity="high"),
        ]
    )

    case_service = CaseService(InMemoryCaseRepository())
    case_service.create(knowledge_base_id="kb-1", title="Case one", priority="high")
    case_service.create(knowledge_base_id="kb-2", title="Case two", priority="high")
    case_service.create(knowledge_base_id="kb-2", title="Case three", priority="low")

    return alert_store, case_service, kb_repository


def test_unscoped_overview_still_aggregates_every_knowledge_base(
    stores: tuple[InMemoryAlertHistoryWriter, CaseService, InMemoryKnowledgeBaseRepository],
) -> None:
    alert_store, case_service, kb_repository = stores

    overview = build_analytics_overview(
        alert_store=alert_store, case_service=case_service, kb_repository=kb_repository
    )

    assert overview.active_alerts == 3
    assert overview.open_cases == 3
    assert overview.entities_monitored == 14
    assert overview.high_risk_entities == 2


def test_scoped_overview_counts_only_the_named_knowledge_base(
    stores: tuple[InMemoryAlertHistoryWriter, CaseService, InMemoryKnowledgeBaseRepository],
) -> None:
    alert_store, case_service, kb_repository = stores

    overview = build_analytics_overview(
        alert_store=alert_store,
        case_service=case_service,
        kb_repository=kb_repository,
        knowledge_base_id="kb-1",
    )

    assert overview.active_alerts == 2
    assert overview.open_cases == 1
    assert overview.entities_monitored == 10
    # Only the critical alert; the low-severity one is not high risk.
    assert overview.high_risk_entities == 1


def test_scoped_overview_for_a_knowledge_base_with_nothing_in_it(
    stores: tuple[InMemoryAlertHistoryWriter, CaseService, InMemoryKnowledgeBaseRepository],
) -> None:
    _, case_service, kb_repository = stores
    kb_repository.create(KnowledgeBase(id="kb-3", name="Three", description="", created_at=utc_now()))

    overview = build_analytics_overview(
        alert_store=InMemoryAlertHistoryWriter(),
        case_service=case_service,
        kb_repository=kb_repository,
        knowledge_base_id="kb-3",
    )

    assert overview.active_alerts == 0
    assert overview.open_cases == 0
    assert overview.entities_monitored == 0


def test_unknown_knowledge_base_reads_as_empty_rather_than_workspace_wide(
    stores: tuple[InMemoryAlertHistoryWriter, CaseService, InMemoryKnowledgeBaseRepository],
) -> None:
    # Falling back to workspace-wide totals would silently answer a different
    # question than the one asked.
    alert_store, case_service, kb_repository = stores

    overview = build_analytics_overview(
        alert_store=alert_store,
        case_service=case_service,
        kb_repository=kb_repository,
        knowledge_base_id="kb-ghost",
    )

    assert overview.active_alerts == 0
    assert overview.open_cases == 0
    assert overview.entities_monitored == 0
    assert overview.high_risk_entities == 0
