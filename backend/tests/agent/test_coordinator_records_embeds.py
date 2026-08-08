"""handle_records_ingested writes vector points for every entity it persists."""

from __future__ import annotations

from unittest.mock import MagicMock


from agent.coordinator import handle_records_ingested
from config.schema import (
    RecordEntityMapping,
    RecordFeedConfig,
    RecordObservationMapping,
    RecordRelationshipMapping,
    RecordsConfig,
)
from embeddings.service_models import EmbedResponse, EmbeddedItem
from events.types import RecordsIngestedEvent
from shared.provenance import EMBEDDING_CHANNEL_KEY, EMBEDDING_CHANNEL_TEXT
from records.models import RawRecord, content_hash_for
from records.adapters.in_memory import InMemoryRawRecordStore
from shared.utils import generate_id


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _records_config() -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="carrier_claims_a",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                entities=[
                    RecordEntityMapping(
                        entity_type="provider",
                        id_field="npi",
                    ),
                    RecordEntityMapping(
                        entity_type="claim",
                        id_field="claim_id",
                    ),
                ],
                relationships=[
                    RecordRelationshipMapping(
                        relationship_type="submitted_by",
                        source_entity_type="claim",
                        target_entity_type="provider",
                    )
                ],
                observations=[
                    RecordObservationMapping(
                        metric_name="claim_anomaly",
                        entity_type="claim",
                        score_field="anomaly_score",
                        rationale="feed score",
                    )
                ],
            )
        ]
    )


def _seed_store(store: InMemoryRawRecordStore, correlation_id: str) -> None:
    payload: dict[str, object] = {
        "claim_id": "C1",
        "npi": "1234567890",
        "anomaly_score": 0.5,
    }
    store.persist(
        [
            RawRecord(
                knowledge_base_id="kb-1",
                record_type="claim_record",
                record_id="C1",
                payload=payload,
                source_type="file_upload",
                source_ref="claims.csv",
                correlation_id=correlation_id,
                content_hash=content_hash_for(payload),
            )
        ]
    )


def _embed_response(content_ids: list[str], dim: int = 8) -> EmbedResponse:
    return EmbedResponse(
        request_id=generate_id(),
        model_name="in-memory-embedder",
        dimensions=dim,
        items=[
            EmbeddedItem(
                content_id=cid,
                vector=[0.0] * dim,
                channel="text",
            )
            for cid in content_ids
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_handler_indexes_vectors_for_persisted_entities() -> None:
    """embed is called and vector_store.upsert_records is called once with
    one submission per entity produced by map_batch."""

    # Arrange
    store = InMemoryRawRecordStore()
    corr = "corr-embed-1"
    _seed_store(store, corr)
    records_config = _records_config()

    graph_service = MagicMock()
    # upsert_records_graph returns (entities, relationships); we need two entities.
    # Use MagicMock so the call passes through without real graph logic.
    # The coordinator captures the return value as stored_entities/stored_relationships.
    import shared.types as st

    provider_entity = st.Entity(
        id="provider:1234567890",
        type="provider",
        properties={"npi": "1234567890"},
    )
    claim_entity = st.Entity(
        id="claim:C1",
        type="claim",
        properties={"claim_id": "C1"},
    )
    graph_service.upsert_records_graph.return_value = (
        [provider_entity, claim_entity],
        [],
    )

    # embeddings_service.embed() returns an EmbedResponse with one item per entity.
    embeddings_service = MagicMock()
    embeddings_service.embed.return_value = _embed_response(
        ["provider:1234567890", "claim:C1"], dim=8
    )

    # vector_store.upsert_records returns a list of VectorRecord.
    vector_store = MagicMock()
    from vectorstore.models import VectorRecord

    vector_store.upsert_records.return_value = [
        VectorRecord(
            id="vr-1",
            knowledge_base_id="kb-1",
            content_id="provider:1234567890",
            embedding=[0.0] * 8,
        ),
        VectorRecord(
            id="vr-2",
            knowledge_base_id="kb-1",
            content_id="claim:C1",
            embedding=[0.0] * 8,
        ),
    ]

    observation_writer = MagicMock()

    event = RecordsIngestedEvent(
        correlation_id=corr,
        knowledge_base_id="kb-1",
        feed_name="carrier_claims_a",
        record_type="claim_record",
        record_count=1,
    )

    # Act
    result = handle_records_ingested(
        event,
        records_config=records_config,
        raw_record_store=store,
        graph_service=graph_service,
        observation_writer=observation_writer,
        embeddings_service=embeddings_service,
        vector_store=vector_store,
    )

    # Assert
    assert result == 1

    # embed() called once with an EmbedRequest covering both entities
    assert embeddings_service.embed.call_count == 1
    embed_req = embeddings_service.embed.call_args.args[0]
    submitted_ids = {s.content_id for s in embed_req.submissions}
    assert submitted_ids == {"provider:1234567890", "claim:C1"}

    # upsert_records called once for the kb namespace
    assert vector_store.upsert_records.call_count == 1
    ns, records = vector_store.upsert_records.call_args.args
    assert ns == "kb-1"
    assert {r.content_id for r in records} == {"provider:1234567890", "claim:C1"}

    # Every record vector must carry the text channel, or RAG retrieval cannot
    # see it: `ServiceContextRetriever` filters every search on this key, and
    # this path did not stamp it until 2026-08-08. Removing the stamp used to
    # break no test in this file — the vectors were written, indexed, and
    # unreachable.
    assert all(
        r.metadata[EMBEDDING_CHANNEL_KEY] == EMBEDDING_CHANNEL_TEXT for r in records
    )


def test_handler_skips_embedding_when_embeddings_service_is_none() -> None:
    """When embeddings_service=None the handler completes without touching vector_store."""

    store = InMemoryRawRecordStore()
    corr = "corr-embed-2"
    _seed_store(store, corr)
    records_config = _records_config()

    graph_service = MagicMock()
    import shared.types as st

    graph_service.upsert_records_graph.return_value = (
        [st.Entity(id="claim:C1", type="claim", properties={})],
        [],
    )

    vector_store = MagicMock()
    observation_writer = MagicMock()

    event = RecordsIngestedEvent(
        correlation_id=corr,
        knowledge_base_id="kb-1",
        feed_name="carrier_claims_a",
        record_type="claim_record",
        record_count=1,
    )

    result = handle_records_ingested(
        event,
        records_config=records_config,
        raw_record_store=store,
        graph_service=graph_service,
        observation_writer=observation_writer,
        embeddings_service=None,
        vector_store=vector_store,
    )

    assert result == 1
    vector_store.upsert_records.assert_not_called()


def test_handler_skips_embedding_when_vector_store_is_none() -> None:
    """When vector_store=None the handler completes without calling embed."""

    store = InMemoryRawRecordStore()
    corr = "corr-embed-3"
    _seed_store(store, corr)
    records_config = _records_config()

    graph_service = MagicMock()
    import shared.types as st

    graph_service.upsert_records_graph.return_value = (
        [st.Entity(id="claim:C1", type="claim", properties={})],
        [],
    )

    embeddings_service = MagicMock()
    observation_writer = MagicMock()

    event = RecordsIngestedEvent(
        correlation_id=corr,
        knowledge_base_id="kb-1",
        feed_name="carrier_claims_a",
        record_type="claim_record",
        record_count=1,
    )

    result = handle_records_ingested(
        event,
        records_config=records_config,
        raw_record_store=store,
        graph_service=graph_service,
        observation_writer=observation_writer,
        embeddings_service=embeddings_service,
        vector_store=None,
    )

    assert result == 1
    embeddings_service.embed.assert_not_called()
