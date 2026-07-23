"""API-side assembly of the KB-delete cascade store bundle from DI.

The cascade itself (`KbDeletionStores` + `kb_deletion_steps`) lives in
`knowledgebases.cleanup` so the worker coordinator can share the same step list
(see `agent.coordinator.handle_knowledge_base_deleted`). This module only wires
the bundle from FastAPI dependencies for the `DELETE /knowledgebases/{id}` route.
"""

from __future__ import annotations

from fastapi import Depends

from analytics.explainability.repository import EvidencePackRepository
from analytics.gnn.adapters.cluster_store import ObjectStoreClusterSummaryStore
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.peerstats.adapters.protocols import DerivedRiskSignalWriterProtocol
from analytics.risk.adapters.protocols import RiskHistoryWriter
from api._alert_store import AlertProjectionRepository
from api.dependencies import (
    get_alert_history_writer,
    get_alert_repository,
    get_case_repository,
    get_conversation_repository,
    get_derived_signal_store,
    get_document_status_store,
    get_entity_metric_repository,
    get_evidence_pack_repository,
    get_graph_service,
    get_object_store,
    get_observation_writer,
    get_policy_repository,
    get_raw_record_store,
    get_risk_history_writer,
    get_scorecard_run_repository,
    get_timeseries_anomaly_store,
    get_vector_service,
)
from cases.adapters.protocols import CaseRepository
from conversations.adapters.protocols import ConversationRepository
from graph.protocols import GraphServiceProtocol
from ingestion.adapters.protocols import SourceDocumentStatusStore
from knowledgebases.cleanup import (
    KbDeletionStores,
    TimeseriesAnomalyPurger,
    kb_deletion_steps,
)
from monitoring.adapters.protocols import AlertHistoryWriter, ObservationWriter
from policy.adapters.protocols import PolicyItemRepository
from records.adapters.protocols import RawRecordStore
from scorecards.adapters.protocols import ScorecardRunRepository
from storage.protocols import ObjectStore
from vectorstore.protocols import VectorServiceProtocol


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
    scorecard_run_repository: ScorecardRunRepository = Depends(
        get_scorecard_run_repository
    ),
    document_status_store: SourceDocumentStatusStore = Depends(
        get_document_status_store
    ),
    object_store: ObjectStore = Depends(get_object_store),
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    timeseries_anomaly_store: TimeseriesAnomalyPurger = Depends(
        get_timeseries_anomaly_store
    ),
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
        scorecard_run_repository=scorecard_run_repository,
        document_status_store=document_status_store,
        object_store=object_store,
        gnn_cluster_store=ObjectStoreClusterSummaryStore(object_store),
        timeseries_anomaly_store=timeseries_anomaly_store,
        alert_projection_store=alert_repository,
    )


__all__ = [
    "KbDeletionStores",
    "get_kb_deletion_stores",
    "kb_deletion_steps",
]
