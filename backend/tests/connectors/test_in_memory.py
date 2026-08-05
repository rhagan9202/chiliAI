from __future__ import annotations

from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorQuarantineRecordCreate,
    ConnectorSchedule,
    ConnectorSyncCounters,
    ConnectorSyncRunCreate,
    ConnectorSyncRunUpdate,
)
from connectors.adapters.in_memory import InMemoryConnectorRepository


def _definition_payload() -> ConnectorDefinitionCreate:
    return ConnectorDefinitionCreate(
        connector_id="cms-claims-drop",
        name="CMS Claims Drop",
        source_type="filesystem",
        knowledge_base_id="kb-cms",
        domain_name="medicare_fraud",
        credentials_ref="env:CMS_CONNECTOR_TOKEN",
        schedule=ConnectorSchedule(mode="manual"),
        mapping=ConnectorMappingRef(
            mapping_id="claims-feed",
            mapping_version="v1",
            feed_name="claims_feed",
        ),
        config={"path": "/imports/cms/claims.csv"},
    )


def test_repository_saves_definitions_without_exposing_credentials() -> None:
    repository = InMemoryConnectorRepository()

    definition = repository.save_definition(_definition_payload())

    assert definition.connector_id == "cms-claims-drop"
    assert definition.credentials_ref == "env:CMS_CONNECTOR_TOKEN"
    assert definition.credentials_display == "env:CMS...OKEN"
    assert definition.config == {"path": "/imports/cms/claims.csv"}
    page = repository.list_definitions(knowledge_base_id="kb-cms")
    assert page.total_items == 1
    assert page.items[0].connector_id == "cms-claims-drop"


def test_repository_tracks_runs_and_quarantine_by_connector() -> None:
    repository = InMemoryConnectorRepository()
    repository.save_definition(_definition_payload())

    run = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            requested_by="operator-1",
            idempotency_key="run-key-1",
        )
    )
    updated = repository.update_run(
        run.run_id,
        ConnectorSyncRunUpdate(
            status="completed",
            counters=ConnectorSyncCounters(
                pulled=12,
                accepted=10,
                quarantined=2,
                failed=0,
            ),
            ingest_correlation_id="ingest-1",
            source_cursor="cursor-12",
        ),
    )
    quarantine = repository.add_quarantine_record(
        ConnectorQuarantineRecordCreate(
            run_id=run.run_id,
            connector_id="cms-claims-drop",
            knowledge_base_id="kb-cms",
            source_record_id="claim-99",
            reason="missing provider_npi",
            raw_ref="object://connector/cms-claims-drop/claim-99.json",
        )
    )

    assert updated.status == "completed"
    assert updated.counters.quarantined == 2
    assert updated.completed_at is not None
    assert quarantine.quarantine_id.startswith(f"{run.run_id}:")
    assert repository.list_runs(connector_id="cms-claims-drop").total_items == 1
    assert repository.list_quarantine(run_id=run.run_id).items[0].source_record_id == "claim-99"
