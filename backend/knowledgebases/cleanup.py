"""The authoritative KB-delete cascade: which per-KB stores are purged, in order.

Lives in ``knowledgebases`` so both orchestration points can share one step list
without a cycle: the API gateway (``api._kb_cleanup`` assembles the bundle from DI
and the DELETE endpoint iterates the steps) and the worker coordinator (which
retries the same cascade on a ``KnowledgeBaseDeletedEvent`` with
``cleanup_pending=True``). This module imports only protocol contracts.

Adding a new per-KB durable store is one field on :class:`KbDeletionStores` plus
one entry in :func:`kb_deletion_steps`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from analytics.explainability.repository import EvidencePackRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.peerstats.adapters.protocols import DerivedRiskSignalWriterProtocol
from analytics.risk.adapters.protocols import RiskHistoryWriter
from cases.adapters.protocols import CaseRepository
from conversations.adapters.protocols import ConversationRepository
from graph.protocols import GraphServiceProtocol
from monitoring.adapters.protocols import AlertHistoryWriter, ObservationWriter
from policy.adapters.protocols import PolicyItemRepository
from records.adapters.protocols import RawRecordStore
from scorecards.adapters.protocols import ScorecardRunRepository
from storage.protocols import ObjectStore
from vectorstore.protocols import VectorServiceProtocol


@dataclass(frozen=True, slots=True)
class KbDeletionStores:
    """Every durable store purged by the KB-delete cascade."""

    graph_service: GraphServiceProtocol
    vector_service: VectorServiceProtocol
    raw_record_store: RawRecordStore
    derived_signal_store: DerivedRiskSignalWriterProtocol
    risk_history_writer: RiskHistoryWriter
    observation_writer: ObservationWriter
    alert_history_writer: AlertHistoryWriter
    entity_metric_repository: EntityMetricRepository
    conversation_repository: ConversationRepository
    case_repository: CaseRepository
    policy_item_repository: PolicyItemRepository
    evidence_pack_repository: EvidencePackRepository
    scorecard_run_repository: ScorecardRunRepository
    object_store: ObjectStore


def delete_object_store_prefix(
    object_store: ObjectStore, knowledge_base_id: str
) -> None:
    """Remove all object-store keys under the KB prefix."""

    prefix = f"knowledgebases/{knowledge_base_id}/"
    for key in object_store.list_keys(prefix):
        object_store.delete(key)


def kb_deletion_steps(
    stores: KbDeletionStores, knowledge_base_id: str
) -> list[tuple[str, Callable[[], object]]]:
    """The ordered KB-delete cascade: (step name, deletion callable) pairs.

    Graph/vector namespaces and object-store payloads are cleared alongside every
    per-KB durable table (each via its ``delete_by_kb``). KB metadata deletion
    (and event publication) is owned by the caller.
    """

    kb = knowledge_base_id
    return [
        ("graph", lambda: stores.graph_service.delete_knowledge_base(kb)),
        ("vector", lambda: stores.vector_service.delete_knowledge_base(kb)),
        ("raw_records", lambda: stores.raw_record_store.delete_by_kb(kb)),
        ("derived_signals", lambda: stores.derived_signal_store.delete_by_kb(kb)),
        ("risk_history", lambda: stores.risk_history_writer.delete_by_kb(kb)),
        ("observations", lambda: stores.observation_writer.delete_by_kb(kb)),
        ("alert_history", lambda: stores.alert_history_writer.delete_by_kb(kb)),
        ("metrics", lambda: stores.entity_metric_repository.delete_by_kb(kb)),
        ("conversations", lambda: stores.conversation_repository.delete_by_kb(kb)),
        ("cases", lambda: stores.case_repository.delete_by_kb(kb)),
        ("policy", lambda: stores.policy_item_repository.delete_by_kb(kb)),
        ("evidence", lambda: stores.evidence_pack_repository.delete_by_kb(kb)),
        ("scorecards", lambda: stores.scorecard_run_repository.delete_by_kb(kb)),
        ("object_store", lambda: delete_object_store_prefix(stores.object_store, kb)),
    ]


__all__ = [
    "KbDeletionStores",
    "delete_object_store_prefix",
    "kb_deletion_steps",
]
