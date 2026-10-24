"""The worker's KB-delete retry bundle selects the same backends as the API."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

from agent.coordinator import (
    build_derived_signal_writer,
    build_kb_deletion_stores,
    build_timeseries_anomaly_store,
)
from analytics.explainability.adapters.reviews_postgres import (
    PostgresExplanationReviewRepository,
)
from analytics.explainability.reviews import InMemoryExplanationReviewRepository
from analytics.identity_resolution.adapters.postgres import (
    PostgresIdentityLinkRepository,
)
from analytics.identity_resolution.repository import InMemoryIdentityLinkRepository
from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
from analytics.score_runs.adapters.in_memory import InMemoryScoreRunRepository
from analytics.score_runs.adapters.postgres import PostgresScoreRunRepository
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.adapters.postgres import PostgresConnectorRepository
from database.protocols import ConnectionProvider
from events.adapters.in_memory import InMemoryEventBus
from governance.adapters.in_memory import InMemoryGovernanceEvalRepository
from governance.adapters.postgres import PostgresGovernanceEvalRepository
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from knowledgebases.cleanup import KbDeletionStores
from monitoring.adapters.in_memory import (
    InMemoryAlertHistoryWriter,
    InMemoryObservationWriter,
)
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.adapters.postgres import PostgresPlaybookRepository
from records.adapters.in_memory import InMemoryRawRecordStore
from storage.adapters.in_memory import InMemoryObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.adapters.postgres import PostgresWorkflowDefinitionRepository


def _bundle(provider: ConnectionProvider | None) -> KbDeletionStores:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    return build_kb_deletion_stores(
        provider,
        graph_service=create_graph_service(
            InMemoryGraphRepository(), event_bus=event_bus, object_store=object_store
        ),
        vector_store=InMemoryVectorStore(),
        object_store=object_store,
        event_bus=event_bus,
        raw_record_store=InMemoryRawRecordStore(),
        derived_signal_store=build_derived_signal_writer(None),
        observation_writer=InMemoryObservationWriter(),
        risk_history_writer=InMemoryRiskHistoryWriter(),
        alert_history_writer=InMemoryAlertHistoryWriter(),
        entity_metric_repository=InMemoryEntityMetricRepository(),
        timeseries_anomaly_store=build_timeseries_anomaly_store(None),
    )


@pytest.mark.parametrize(
    ("field", "in_memory_type", "postgres_type"),
    [
        ("score_run_repository", InMemoryScoreRunRepository, PostgresScoreRunRepository),
        (
            "identity_link_repository",
            InMemoryIdentityLinkRepository,
            PostgresIdentityLinkRepository,
        ),
        (
            "explanation_review_repository",
            InMemoryExplanationReviewRepository,
            PostgresExplanationReviewRepository,
        ),
        (
            "workflow_definition_repository",
            InMemoryWorkflowDefinitionRepository,
            PostgresWorkflowDefinitionRepository,
        ),
        (
            "governance_eval_repository",
            InMemoryGovernanceEvalRepository,
            PostgresGovernanceEvalRepository,
        ),
        ("connector_repository", InMemoryConnectorRepository, PostgresConnectorRepository),
        ("playbook_repository", InMemoryPlaybookRepository, PostgresPlaybookRepository),
    ],
)
def test_retry_bundle_selects_backend_by_provider(
    field: str, in_memory_type: type, postgres_type: type
) -> None:
    provider = cast(ConnectionProvider, MagicMock())

    assert isinstance(getattr(_bundle(None), field), in_memory_type)
    assert isinstance(getattr(_bundle(provider), field), postgres_type)
