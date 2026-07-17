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
from typing import Protocol

from analytics.explainability.repository import EvidencePackRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.peerstats.adapters.protocols import DerivedRiskSignalWriterProtocol
from analytics.risk.adapters.protocols import RiskHistoryWriter
from cases.adapters.protocols import CaseRepository
from conversations.adapters.protocols import ConversationRepository
from graph.protocols import GraphServiceProtocol
from ingestion.adapters.protocols import SourceDocumentStatusStore
from monitoring.adapters.protocols import AlertHistoryWriter, ObservationWriter
from policy.adapters.protocols import PolicyItemRepository
from records.adapters.protocols import RawRecordStore
from scorecards.adapters.protocols import ScorecardRunRepository
from storage.protocols import ObjectStore
from vectorstore.protocols import VectorServiceProtocol


class AlertProjectionPurger(Protocol):
    """The slice of the API's alert read-model store the cascade needs.

    Defined structurally here (rather than importing the API-owned
    ``AlertProjectionRepository``) so this module keeps its no-``api``-imports
    rule; ``api._alert_store`` repositories satisfy it without registration.
    """

    def remove_by_knowledge_base(self, knowledge_base_id: str) -> int: ...


class GnnClusterPurger(Protocol):
    """The slice of the GNN cluster-summary store the cascade needs.

    Defined structurally here (rather than importing the analytics-owned
    ``ClusterSummaryStoreProtocol``) so this module keeps its
    no-cross-module-imports rule; ``ObjectStoreClusterSummaryStore``
    satisfies it without registration.
    """

    def delete_by_kb(self, knowledge_base_id: str) -> None: ...


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
    document_status_store: SourceDocumentStatusStore
    object_store: ObjectStore
    # Analytics-owned (not API-owned): unlike alert_projection_store below,
    # both the API's bundle and the worker's retry bundle build their own
    # ObjectStoreClusterSummaryStore, so this field is always required.
    gnn_cluster_store: GnnClusterPurger
    # The API gateway owns the alert read projection, so only the API's bundle
    # carries it; the worker's retry bundle leaves it None and the step is
    # skipped (never reported as a phantom success). The projection is a
    # non-authoritative read model, so an orphan surviving that rare path
    # (API-side step failed AND only the worker retried) costs a stale feed
    # row, not data integrity.
    alert_projection_store: AlertProjectionPurger | None = None


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
    alert_projection_store = stores.alert_projection_store
    maybe_alert_projection: tuple[str, Callable[[], object]] | None = (
        ("alert_projection", lambda: alert_projection_store.remove_by_knowledge_base(kb))
        if alert_projection_store is not None
        else None
    )
    steps: list[tuple[str, Callable[[], object]] | None] = [
        ("graph", lambda: stores.graph_service.delete_knowledge_base(kb)),
        ("vector", lambda: stores.vector_service.delete_knowledge_base(kb)),
        ("raw_records", lambda: stores.raw_record_store.delete_by_kb(kb)),
        ("derived_signals", lambda: stores.derived_signal_store.delete_by_kb(kb)),
        ("risk_history", lambda: stores.risk_history_writer.delete_by_kb(kb)),
        ("observations", lambda: stores.observation_writer.delete_by_kb(kb)),
        ("alert_history", lambda: stores.alert_history_writer.delete_by_kb(kb)),
        maybe_alert_projection,
        ("gnn_clusters", lambda: stores.gnn_cluster_store.delete_by_kb(kb)),
        ("metrics", lambda: stores.entity_metric_repository.delete_by_kb(kb)),
        ("conversations", lambda: stores.conversation_repository.delete_by_kb(kb)),
        ("cases", lambda: stores.case_repository.delete_by_kb(kb)),
        ("policy", lambda: stores.policy_item_repository.delete_by_kb(kb)),
        ("evidence", lambda: stores.evidence_pack_repository.delete_by_kb(kb)),
        ("scorecards", lambda: stores.scorecard_run_repository.delete_by_kb(kb)),
        ("document_status", lambda: stores.document_status_store.delete_by_kb(kb)),
        ("object_store", lambda: delete_object_store_prefix(stores.object_store, kb)),
    ]
    return [step for step in steps if step is not None]


__all__ = [
    "AlertProjectionPurger",
    "GnnClusterPurger",
    "KbDeletionStores",
    "delete_object_store_prefix",
    "kb_deletion_steps",
]
