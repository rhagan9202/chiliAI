"""Durable analytics-overview aggregation (BL-012).

Computes the dashboard overview entirely from durable stores — the alert
feed store (``alert_history``), the durable case repository, and the
knowledge base metadata repository — replacing the previously seeded counts
on ``ApiState``.

The overview is workspace-wide by default, aggregating across every knowledge
base the KB repository knows about. Passing ``knowledge_base_id`` scopes every
figure to that one KB (UXA-408) so the dashboard's tiles agree with the rest of
the page, which has been KB-scoped since UXA-101.
"""

from __future__ import annotations

from api.contracts import AnalyticsOverviewResponse
from cases.service import CaseService
from knowledgebases.protocols import KnowledgeBaseRepository
from monitoring.adapters.protocols import AlertFeedStoreProtocol
from shared.alerts import ACTIVE_ALERT_STATUSES, normalize_severity

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
    alert_store: AlertFeedStoreProtocol,
    case_service: CaseService,
    kb_repository: KnowledgeBaseRepository,
    knowledge_base_id: str | None = None,
) -> AnalyticsOverviewResponse:
    """Return the dashboard overview computed from durable stores.

    ``knowledge_base_id=None`` keeps the workspace-wide behaviour existing
    callers rely on. An unknown id deliberately reads as empty rather than
    falling back to workspace-wide totals — answering a different question
    than the one asked would be worse than answering zero.
    """
    knowledge_bases = (
        [knowledge_base_id]
        if knowledge_base_id is not None
        else _list_all_knowledge_base_ids(kb_repository)
    )
    entities_monitored = _sum_entity_counts(kb_repository, knowledge_bases)
    open_cases = _count_open_cases(case_service, knowledge_bases)
    active_alerts, high_risk_entities = _count_alert_metrics(
        alert_store, knowledge_base_id=knowledge_base_id
    )
    return AnalyticsOverviewResponse(
        active_alerts=active_alerts,
        open_cases=open_cases,
        entities_monitored=entities_monitored,
        high_risk_entities=high_risk_entities,
    )


def _count_alert_metrics(
    alert_store: AlertFeedStoreProtocol,
    *,
    knowledge_base_id: str | None = None,
) -> tuple[int, int]:
    """Return (active alert count, active high-risk alert count).

    A single pass over the durable alert history so the status- and
    severity-derived tiles stay consistent.
    """
    active = 0
    high_risk = 0
    offset = 0
    while True:
        records, total = alert_store.list_alerts(
            knowledge_base_id=knowledge_base_id, limit=_ALERT_PAGE_SIZE, offset=offset
        )
        for record in records:
            if record.status not in ACTIVE_ALERT_STATUSES:
                continue
            active += 1
            severity = normalize_severity(record.severity, record.confidence)
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
