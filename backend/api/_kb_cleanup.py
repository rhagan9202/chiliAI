"""KB-delete cascade: the authoritative set of stores purged when a KB is deleted.

`DELETE /knowledgebases/{id}` runs every step in :func:`kb_deletion_steps`
best-effort, recording per-step status (so a partial failure surfaces in the 207
body and flags the KB ``pending_cleanup``). Centralising the step list here keeps
the cascade complete: a new per-KB durable store is purged by adding one field +
one ``Depends`` to :class:`KbDeletionStores` and one entry to ``kb_deletion_steps``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends

from analytics.explainability.repository import EvidencePackRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.peerstats.adapters.protocols import DerivedRiskSignalWriterProtocol
from analytics.risk.adapters.protocols import RiskHistoryWriter
from api.dependencies import (
    get_alert_history_writer,
    get_case_repository,
    get_conversation_repository,
    get_derived_signal_store,
    get_entity_metric_repository,
    get_evidence_pack_repository,
    get_graph_service,
    get_object_store,
    get_observation_writer,
    get_policy_repository,
    get_raw_record_store,
    get_risk_history_writer,
    get_vector_service,
)
from cases.adapters.protocols import CaseRepository
from conversations.adapters.protocols import ConversationRepository
from graph.protocols import GraphServiceProtocol
from monitoring.adapters.protocols import AlertHistoryWriter, ObservationWriter
from policy.adapters.protocols import PolicyItemRepository
from records.adapters.protocols import RawRecordStore
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
    object_store: ObjectStore


def get_kb_deletion_stores(
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    vector_service: VectorServiceProtocol = Depends(get_vector_service),
    raw_record_store: RawRecordStore = Depends(get_raw_record_store),
    derived_signal_store: DerivedRiskSignalWriterProtocol = Depends(
        get_derived_signal_store
    ),
    risk_history_writer: RiskHistoryWriter = Depends(get_risk_history_writer),
    observation_writer: ObservationWriter = Depends(get_observation_writer),
    alert_history_writer: AlertHistoryWriter = Depends(get_alert_history_writer),
    entity_metric_repository: EntityMetricRepository = Depends(
        get_entity_metric_repository
    ),
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
    case_repository: CaseRepository = Depends(get_case_repository),
    policy_item_repository: PolicyItemRepository = Depends(get_policy_repository),
    evidence_pack_repository: EvidencePackRepository = Depends(
        get_evidence_pack_repository
    ),
    object_store: ObjectStore = Depends(get_object_store),
) -> KbDeletionStores:
    """Assemble the KB-delete cascade store bundle from DI."""

    return KbDeletionStores(
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        derived_signal_store=derived_signal_store,
        risk_history_writer=risk_history_writer,
        observation_writer=observation_writer,
        alert_history_writer=alert_history_writer,
        entity_metric_repository=entity_metric_repository,
        conversation_repository=conversation_repository,
        case_repository=case_repository,
        policy_item_repository=policy_item_repository,
        evidence_pack_repository=evidence_pack_repository,
        object_store=object_store,
    )


def _delete_object_store_prefix(
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

    Graph/vector namespaces and object-store payloads are cleared first, then
    every per-KB durable table is purged via its ``delete_by_kb``. KB metadata
    deletion (and event publication) is owned by the caller.
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
        ("object_store", lambda: _delete_object_store_prefix(stores.object_store, kb)),
    ]


__all__ = [
    "KbDeletionStores",
    "get_kb_deletion_stores",
    "kb_deletion_steps",
]
