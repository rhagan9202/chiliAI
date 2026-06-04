"""Durable analytics-overview aggregation (BL-012).

Computes the dashboard overview entirely from durable stores — the alert
projection repository, the durable case repository, and the knowledge base
metadata repository — replacing the previously seeded counts on ``ApiState``.

The overview is global (not KB-scoped), so case + entity counts aggregate
across every knowledge base the KB repository knows about.
"""

from __future__ import annotations

from api._alert_store import ACTIVE_ALERT_STATUSES, AlertProjectionRepository
from api.contracts import AnalyticsOverviewResponse
from cases.service import CaseService
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.alerts import normalize_severity

__all__ = ["HIGH_RISK_ALERT_SEVERITIES", "build_analytics_overview"]

# Active alerts at these severities are treated as the durable "high risk
# entity" signal for the dashboard tile (risk profiles are not durably
# enumerable across knowledge bases).
HIGH_RISK_ALERT_SEVERITIES = {"high", "critical"}

# Open cases are any case not in the terminal "closed" state.
_OPEN_CASE_STATUSES = ("open", "in_review")

_KB_PAGE_SIZE = 200
_ALERT_PAGE_SIZE = 500


def build_analytics_overview(
    *,
    alert_repository: AlertProjectionRepository,
    case_service: CaseService,
    kb_repository: KnowledgeBaseRepository,
) -> AnalyticsOverviewResponse:
    """Return the dashboard overview computed from durable stores."""
    knowledge_bases = _list_all_knowledge_base_ids(kb_repository)
    entities_monitored = _sum_entity_counts(kb_repository, knowledge_bases)
    open_cases = _count_open_cases(case_service, knowledge_bases)
    active_alerts, high_risk_entities = _count_alert_metrics(alert_repository)
    return AnalyticsOverviewResponse(
        active_alerts=active_alerts,
        open_cases=open_cases,
        entities_monitored=entities_monitored,
        high_risk_entities=high_risk_entities,
    )


def _count_alert_metrics(
    alert_repository: AlertProjectionRepository,
) -> tuple[int, int]:
    """Return (active alert count, active high-risk alert count).

    A single pass over the durable alert projections so the status- and
    severity-derived tiles stay consistent.
    """
    active = 0
    high_risk = 0
    offset = 0
    while True:
        records, total = alert_repository.list(limit=_ALERT_PAGE_SIZE, offset=offset)
        for record in records:
            if record.alert.status not in ACTIVE_ALERT_STATUSES:
                continue
            active += 1
            severity = normalize_severity(record.alert.severity, record.confidence)
            if severity in HIGH_RISK_ALERT_SEVERITIES:
                high_risk += 1
        offset += len(records)
        if not records or offset >= total:
            break
    return active, high_risk


def _list_all_knowledge_base_ids(
    kb_repository: KnowledgeBaseRepository,
) -> list[str]:
    ids: list[str] = []
    offset = 0
    while True:
        page, total = kb_repository.list(limit=_KB_PAGE_SIZE, offset=offset)
        ids.extend(kb.id for kb in page)
        offset += len(page)
        if not page or offset >= total:
            break
    return ids


def _sum_entity_counts(
    kb_repository: KnowledgeBaseRepository,
    knowledge_base_ids: list[str],
) -> int:
    total = 0
    for kb_id in knowledge_base_ids:
        record = kb_repository.get(kb_id)
        if record is not None:
            total += record.entity_count
    return total


def _count_open_cases(
    case_service: CaseService,
    knowledge_base_ids: list[str],
) -> int:
    total = 0
    for kb_id in knowledge_base_ids:
        for status in _OPEN_CASE_STATUSES:
            _, count = case_service.list(
                knowledge_base_id=kb_id, limit=0, offset=0, status=status
            )
            total += count
    return total
