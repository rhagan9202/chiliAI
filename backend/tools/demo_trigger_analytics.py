"""Explicitly trigger the analytics-review pass for a KB's top-risk providers.

D1 demo gap (Task 5 / analytics.34): a natural CMS records ingest runs the
records cascade far enough to compute derived risk *signals*
(``entity_derived_signals``), but nothing in that flow publishes a
``graph.updated`` event — so Flow B (GNN -> risk -> explainability ->
``alerts.created``) never runs, and the demo's alert/evidence-pack scenes
(probes (b)/(d) in ``scripts/demo_cms.sh``) have nothing to show. Automatic
triggering of Flow B from a records ingest is the chartered analytics.34
follow-up; this script is the disclosed, explicit stand-in for the demo
(see docs/demo/README.md and the presenter script's setup checklist).

What it does, for the top-N provider entities by risk score in a KB:

1. Selects entity ids via ``GET /analytics/risk-scores`` on the running API
   (over the compose network alias ``http://api:8000`` — see
   ``docker-compose.dev.yaml`` services ``api``/``worker``, both on
   ``chili-net``).
2. Stages two synthetic pipeline artifacts in the object store: a
   ``GraphUpsertResult`` (the "graph update" artifact) naming those entity
   ids, and a ``ValidationReport`` whose ``valid_entities`` is a superset of
   them (the BL-017 integrity guard in ``agent.coordinator`` requires
   ``upserted_entity_ids ⊆ {e.id for e in valid_entities}`` — see
   ``_select_upserted_entities`` in ``agent/coordinator.py``).
3. Publishes a ``graph.updated`` event referencing those two artifacts on
   the real Redis Streams event bus. The running worker's normal dispatch
   (``agent.coordinator.handle_event``) picks it up and runs both Flow A
   (embeddings, harmless re-embed of the same entities) and Flow B
   (GNN/risk/explainability/alerts) for real, exactly as it would for a
   naturally-ingested document.

Selection-route decision (risk signal source): the ``entity_derived_signals``
table is reachable from inside the worker container too (same
``DATABASE_URL``, same ``database.runtime.create_connection_provider`` the
worker uses to build ``analytics.risk.adapters.postgres.PostgresRiskSignalSource``),
but reproducing its "latest score per entity, ranked, sliced to N" query
would duplicate real service logic in a CLI script. The API already exposes
that exact ranking as ``GET /analytics/risk-scores`` (see
``api/routers/analytics.py::list_risk_scores`` ->
``RiskService.list_scores`` -> ``RiskSignalSourceProtocol.list_ranked_entries``,
which sorts by ``overall_score`` descending and slices to ``limit``) —
reusing it is simpler and equally honest: it is the same code path an
analyst's dashboard call would use, not a shortcut around it.

Usage (inside the worker container):

    docker compose -f docker-compose.dev.yaml exec -T worker \\
        python -m tools.demo_trigger_analytics --kb <kb-id> --top 3
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

import httpx

from analytics.risk.service_models import RiskScoreListResponse
from config.loader import load_active_config
from config.schema import DomainConfig, ObjectStoreConfig
from events.runtime import EventBusSettings, create_event_bus
from events.types import GraphUpdatedDocumentReference, GraphUpdatedEvent
from graph.models import GraphUpsertResult
from ingestion.models import ValidationReport
from shared.types import Entity
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from storage.adapters.s3_adapter import S3ObjectStore
from storage.protocols import ObjectStore

__all__ = [
    "main",
    "parse_args",
    "select_top_risk_entity_ids",
    "build_trigger_id",
    "artifact_storage_keys",
    "build_graph_upsert_result",
    "build_validation_report",
    "build_graph_updated_event",
    "build_object_store",
    "event_bus_settings",
]

# Tied to the CMS DE-SynPUF pack's entity type name (see
# backend/config/defaults/medicare_fraud_cms_desynpuf.yaml entity_types[0].name).
# This is a demo-specific tool scoped to the CMS fraud demo, not a generic
# platform module, so hardcoding it here does not violate the "no hardcoded
# domain types" rule (which is about shared/types.py staying domain-agnostic).
DEFAULT_ENTITY_TYPE = "provider"
DEFAULT_API_URL = "http://api:8000"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", required=True, help="Knowledge base id to trigger analytics for.")
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        metavar="N",
        help="Number of top-risk provider entities to trigger (default: 3).",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379"),
        help="Redis Streams URL (default: $REDIS_URL, matching the worker's own env).",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("CHILI_API_URL", DEFAULT_API_URL),
        help=(
            "Base URL of the running API used to select top-risk entities "
            f"(default: {DEFAULT_API_URL}, the compose network alias)."
        ),
    )
    parser.add_argument(
        "--entity-type",
        default=DEFAULT_ENTITY_TYPE,
        help=f"Entity type to rank and trigger (default: {DEFAULT_ENTITY_TYPE}).",
    )
    return parser.parse_args(argv)


def select_top_risk_entity_ids(
    client: httpx.Client,
    *,
    kb_id: str,
    entity_type: str,
    top: int,
) -> list[str]:
    """Return up to ``top`` entity ids, highest risk first, via the real API."""
    response = client.get(
        "/analytics/risk-scores",
        params={"kb_id": kb_id, "entity_type": entity_type, "limit": top},
    )
    response.raise_for_status()
    payload = RiskScoreListResponse.model_validate(response.json())
    return [item.entity_id for item in payload.items[:top]]


def build_trigger_id(now: datetime) -> str:
    """Build a demo correlation/document id stamped with a real-time timestamp."""
    return f"demo-trigger-{now.strftime('%Y%m%dT%H%M%SZ')}"


def artifact_storage_keys(kb_id: str, trigger_id: str) -> tuple[str, str]:
    """Object-store keys for the synthetic graph-update and validation artifacts.

    Deliberately outside the real pipeline's ``knowledgebases/<kb>/...``
    namespace (see ``agent.coordinator._build_validation_storage_key``) so
    demo-trigger artifacts can never collide with or be mistaken for
    naturally-produced pipeline output.
    """
    graph_update_key = f"graph-updates/{kb_id}/{trigger_id}.json"
    validation_key = f"validations/{kb_id}/{trigger_id}.json"
    return graph_update_key, validation_key


def build_graph_upsert_result(
    *,
    knowledge_base_id: str,
    trigger_id: str,
    entity_ids: list[str],
    now: datetime,
) -> GraphUpsertResult:
    """Build the synthetic ``GraphUpsertResult`` artifact naming the entities to trigger."""
    return GraphUpsertResult(
        knowledge_base_id=knowledge_base_id,
        source_document_id=trigger_id,
        parsed_document_id=trigger_id,
        validation_report_id=trigger_id,
        extraction_result_id=trigger_id,
        upserted_entity_ids=list(entity_ids),
        upserted_relationship_ids=[],
        created_at=now,
    )


def build_validation_report(
    *,
    trigger_id: str,
    entity_type: str,
    entity_ids: list[str],
    now: datetime,
) -> ValidationReport:
    """Build the minimal ``ValidationReport`` whose entities cover the trigger ids.

    Must be a superset of ``GraphUpsertResult.upserted_entity_ids`` — the
    BL-017 integrity guard (``agent.coordinator._select_upserted_entities``)
    raises if any upserted id is missing from ``valid_entities``. The real
    entities already exist in the graph from the natural ingest; these
    placeholders exist only to satisfy that guard and carry ``type`` for the
    embedding text fallback (see ``_build_entity_embedding_text``).
    """
    entities = [
        Entity(
            id=entity_id,
            type=entity_type,
            properties={},
            metadata={},
            created_at=now,
            version=1,
        )
        for entity_id in entity_ids
    ]
    return ValidationReport(
        id=trigger_id,
        extraction_result_id=trigger_id,
        source_document_id=trigger_id,
        valid_entities=entities,
        valid_relationships=[],
        entity_errors={},
        relationship_errors={},
        warnings=[
            "Synthetic validation artifact staged by tools.demo_trigger_analytics "
            "for a disclosed, explicit analytics-review trigger (D1 demo)."
        ],
        validated_at=now,
    )


def build_graph_updated_event(
    *,
    knowledge_base_id: str,
    trigger_id: str,
    entity_count: int,
    graph_update_storage_key: str,
    validation_storage_key: str,
) -> GraphUpdatedEvent:
    """Build the ``graph.updated`` event that fans out into Flow A + Flow B."""
    return GraphUpdatedEvent(
        correlation_id=trigger_id,
        source="tools.demo_trigger_analytics",
        documents=[
            GraphUpdatedDocumentReference(
                knowledge_base_id=knowledge_base_id,
                source_document_id=trigger_id,
                parsed_document_id=trigger_id,
                extraction_result_id=trigger_id,
                validation_report_id=trigger_id,
                upserted_entity_count=entity_count,
                upserted_relationship_count=0,
                validation_storage_key=validation_storage_key,
                graph_update_storage_key=graph_update_storage_key,
            )
        ],
    )


def build_object_store(config: DomainConfig) -> ObjectStore:
    """Select an object store adapter from the active domain config.

    Mirrors ``agent.coordinator.build_object_store``'s backend-selection
    logic exactly: ``DomainConfig``'s post-validator fills in a default
    ``ObjectStoreConfig()`` whenever a pack omits the ``storage:`` section
    entirely, so an absent section is indistinguishable from an
    all-Pydantic-defaults one — ``config.storage`` is never actually
    ``None`` after validation. Equality with a fresh default instance (not
    a ``None`` check) is the real signal, matching the worker/API DI layer.
    """
    storage_config = config.storage or ObjectStoreConfig()
    if storage_config == ObjectStoreConfig():
        return InMemoryObjectStore()
    if storage_config.backend == "local":
        return LocalFsObjectStore(storage_config)
    # Literal["s3", "minio", "local"] on ObjectStoreConfig.backend — the only
    # remaining values both mean the S3-compatible adapter.
    return S3ObjectStore(storage_config)


def event_bus_settings(config: DomainConfig, *, redis_url: str) -> EventBusSettings:
    """Build the settings needed to publish onto the worker's real event stream.

    Deliberately NOT a full reimplementation of
    ``agent.coordinator._resolve_worker_event_bus_settings`` — that function
    also handles: falling back to pure env-derived settings when a pack
    omits ``events:`` entirely or leaves it at ``EventBusConfig()`` defaults
    (``"events" not in config.model_fields_set`` / equality check), per-field
    env fallback for ``uri``/``stream_maxlen``/``reclaim_min_idle_ms``, and
    choosing between the "redis" and "in-memory" backends. Reusing it directly
    was considered and rejected: it is a leading-underscore (private) helper
    inside ``agent/coordinator.py`` — importing it would be both a
    `reportPrivateUsage` violation and a forbidden ad-hoc cross-module reach
    into another module's internals — and importing ``agent.coordinator`` at
    all drags in its full dependency graph (GNN/explainability adapters,
    optional `analytics` extras, health server wiring) for a CLI that only
    ever needs to *publish* one event, never consume.

    This function only needs two things to be right for this tool's actual
    use — ``backend`` (must be ``"redis"``: the worker runs as a separate
    process, so an in-memory bus here would be invisible to it regardless of
    what the pack declares) and ``stream_prefix`` (must match what the worker
    resolved, so the event lands on the stream it's actually consuming) —
    and is explicitly scoped to how the demo runs the CLI, not general-purpose:
    the active pack is always ``medicare_fraud_cms_desynpuf``, which pins an
    explicit ``events: {backend: redis, stream_prefix: chili, ...}`` section
    (see ``config/defaults/medicare_fraud_cms_desynpuf.yaml``), so
    ``config.events.stream_prefix`` (never actually ``None`` post-validation,
    see ``build_object_store``'s docstring for the same DomainConfig
    post-validator behavior) already equals what
    ``_resolve_worker_event_bus_settings`` would compute. A pack that leaves
    ``events:`` unset entirely (the bare, not-for-this-demo
    ``medicare_fraud.yaml`` — see ``scripts/demo_cms.sh``'s own guard against
    it) would silently diverge from the coordinator's env-fallback path;
    this tool is not meant to run against such a pack.
    """
    events_config = config.events
    stream_prefix = events_config.stream_prefix if events_config is not None else "chili"
    return EventBusSettings(backend="redis", redis_url=redis_url, stream_prefix=stream_prefix)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    config = load_active_config()
    object_store = build_object_store(config)

    with httpx.Client(base_url=args.api_url, timeout=30.0) as client:
        entity_ids = select_top_risk_entity_ids(
            client, kb_id=args.kb, entity_type=args.entity_type, top=args.top
        )

    if not entity_ids:
        print(
            f"No '{args.entity_type}' risk scores found for KB {args.kb}; "
            "nothing to trigger.",
            file=sys.stderr,
        )
        return 1

    now = utc_now()
    trigger_id = build_trigger_id(now)
    graph_update_key, validation_key = artifact_storage_keys(args.kb, trigger_id)

    graph_update = build_graph_upsert_result(
        knowledge_base_id=args.kb,
        trigger_id=trigger_id,
        entity_ids=entity_ids,
        now=now,
    )
    validation_report = build_validation_report(
        trigger_id=trigger_id,
        entity_type=args.entity_type,
        entity_ids=entity_ids,
        now=now,
    )

    object_store.put_bytes(
        graph_update_key,
        graph_update.model_dump_json().encode("utf-8"),
        media_type="application/json",
        metadata={
            "knowledge_base_id": args.kb,
            "trigger_id": trigger_id,
            "purpose": "demo-analytics-trigger",
        },
    )
    object_store.put_bytes(
        validation_key,
        validation_report.model_dump_json().encode("utf-8"),
        media_type="application/json",
        metadata={
            "knowledge_base_id": args.kb,
            "trigger_id": trigger_id,
            "purpose": "demo-analytics-trigger",
        },
    )

    event = build_graph_updated_event(
        knowledge_base_id=args.kb,
        trigger_id=trigger_id,
        entity_count=len(entity_ids),
        graph_update_storage_key=graph_update_key,
        validation_storage_key=validation_key,
    )

    event_bus = create_event_bus(event_bus_settings(config, redis_url=args.redis_url))
    message_id = event_bus.publish(event)

    print(
        f"demo analytics trigger: kb={args.kb} entity_type={args.entity_type} "
        f"n={len(entity_ids)} entity_ids={entity_ids} correlation_id={trigger_id} "
        f"graph_update_key={graph_update_key} validation_key={validation_key} "
        f"stream_message_id={message_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
