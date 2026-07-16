"""Neo4j graph repository adapter."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
import importlib
from types import TracebackType
from typing import Literal, Protocol, cast

from config.schema import GraphDbConfig
from graph.adapters.protocols import GraphRepository
from graph.exceptions import (
    GraphIntegrityError,
    GraphPersistenceError,
    GraphVersionConflictError,
)
from graph.models import GraphDeleteByProvenance, GraphUpsertOptions, SubgraphResult
from shared.provenance import SOURCE_DOCUMENT_ID_KEY
from shared.types import Entity, Relationship
from shared.utils import utc_now


class Neo4jRecordProtocol(Protocol):
    def __getitem__(self, key: str) -> object: ...

    def get(self, key: str, default: object | None = None) -> object | None: ...


class Neo4jPropertyContainerProtocol(Protocol):
    def __getitem__(self, key: str) -> object: ...

    def get(self, key: str, default: object | None = None) -> object | None: ...


class Neo4jPathProtocol(Protocol):
    @property
    def nodes(self) -> Sequence[Neo4jPropertyContainerProtocol]: ...

    @property
    def relationships(self) -> Sequence[Neo4jPropertyContainerProtocol]: ...


class Neo4jTransactionProtocol(Protocol):
    def run(self, query: str, **parameters: object) -> Iterable[Neo4jRecordProtocol]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class Neo4jSessionProtocol(Protocol):
    def __enter__(self) -> Neo4jSessionProtocol: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    def begin_transaction(self) -> Neo4jTransactionProtocol: ...

    def execute_read(
        self,
        callback: Callable[..., list[Neo4jRecordProtocol]],
        query: str,
        **parameters: object,
    ) -> list[Neo4jRecordProtocol]: ...

    def execute_write(
        self,
        callback: Callable[..., list[Neo4jRecordProtocol]],
        query: str,
        **parameters: object,
    ) -> list[Neo4jRecordProtocol]: ...


class Neo4jDriverProtocol(Protocol):
    def close(self) -> None: ...

    def session(self, *, database: str | None = None) -> Neo4jSessionProtocol: ...


class GraphDatabaseFactoryProtocol(Protocol):
    def driver(
        self,
        uri: str,
        *,
        auth: tuple[str, str] | None = None,
        max_connection_pool_size: int,
    ) -> Neo4jDriverProtocol: ...

try:  # pragma: no cover - exercised through monkeypatched unit tests
    _neo4j_module = importlib.import_module("neo4j")
    _neo4j_exceptions = importlib.import_module("neo4j.exceptions")
except ImportError:  # pragma: no cover - optional dependency
    GraphDatabase: GraphDatabaseFactoryProtocol | None = None
    Neo4jError = Exception
else:
    GraphDatabase = cast(GraphDatabaseFactoryProtocol, _neo4j_module.GraphDatabase)
    Neo4jError = cast(type[Exception], _neo4j_exceptions.Neo4jError)

__all__ = ["Neo4jGraphRepository"]

logger = logging.getLogger(__name__)

_MAX_NEIGHBOR_DEPTH = 5
_ENTITY_LABEL = "Entity"
_RELATIONSHIP_LABEL = "RELATES"


class Neo4jGraphRepository(GraphRepository):
    """Persist and query graph objects using the Neo4j Python driver."""

    def __init__(
        self,
        config: GraphDbConfig,
        *,
        auth: tuple[str, str] | None = None,
        database: str | None = None,
    ) -> None:
        if GraphDatabase is None:
            raise ImportError(
                "The optional neo4j dependency is not installed. Install chili-backend[neo4j]."
            )
        if config.uri is None or config.uri.strip() == "":
            raise ValueError("Neo4jGraphRepository requires GraphDbConfig.uri to be set.")

        self._database = database
        self._driver = GraphDatabase.driver(
            config.uri,
            auth=auth,
            max_connection_pool_size=config.pool_size,
        )
        self._active_transaction: Neo4jTransactionProtocol | None = None
        self._active_session: Neo4jSessionProtocol | None = None
        self._ensure_schema()

    def close(self) -> None:
        self._driver.close()

    def _ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT entity_kb_id_unique IF NOT EXISTS "
            "FOR (e:Entity) "
            "REQUIRE (e.knowledge_base_id, e.entity_id) IS UNIQUE",
            "CREATE INDEX entity_kb_id IF NOT EXISTS "
            "FOR (e:Entity) "
            "ON (e.knowledge_base_id)",
            "CREATE INDEX rel_kb_id_relationship_id IF NOT EXISTS "
            "FOR ()-[r:RELATES]-() "
            "ON (r.knowledge_base_id, r.relationship_id)",
            "CREATE INDEX rel_kb_id IF NOT EXISTS "
            "FOR ()-[r:RELATES]-() "
            "ON (r.knowledge_base_id)",
            "CREATE FULLTEXT INDEX entity_properties_fulltext IF NOT EXISTS "
            "FOR (e:Entity) "
            "ON EACH [e.properties_json]",
        ]
        for stmt in statements:
            try:
                with self._session() as session:
                    session.execute_write(self._run_query, stmt)
            except Neo4jError as exc:
                logger.warning("Failed to ensure Neo4j schema: %s — %s", stmt, exc)

    def transaction(self, knowledge_base_id: str) -> AbstractContextManager[None]:
        return self._transaction_scope()

    def upsert_entities(
        self,
        knowledge_base_id: str,
        entities: list[Entity],
        options: GraphUpsertOptions | None = None,
    ) -> list[Entity]:
        opts = options or GraphUpsertOptions()
        existing_rows = self._read_existing_entities(
            knowledge_base_id, [entity.id for entity in entities]
        )
        if opts.expected_version is not None:
            # Conflict pre-pass over the whole batch (against persisted state,
            # not intra-batch fold state): a conflict anywhere writes nothing.
            for entity in entities:
                existing = existing_rows.get(entity.id)
                if existing is not None and existing["version"] != opts.expected_version:
                    raise GraphVersionConflictError(
                        entity.id, opts.expected_version, cast(int, existing["version"])
                    )
        payload_by_id: dict[str, dict[str, object]] = {}
        for entity in entities:
            payload_by_id[entity.id] = self._fold_entity_row(
                entity,
                persisted=existing_rows.get(entity.id),
                prior_row=payload_by_id.get(entity.id),
                merge_mode=opts.merge_mode,
            )
        payload = list(payload_by_id.values())
        query = f"""
        UNWIND $rows AS row
        MERGE (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.entity_id}})
        ON CREATE SET entity.created_at = row.created_at
        SET entity.type = row.type,
            entity.properties_json = row.properties_json,
            entity.metadata_json = row.metadata_json,
            entity.updated_at = row.updated_at,
            entity.version = row.version
        RETURN entity
        """
        try:
            records = self._run_write(
                query, knowledge_base_id=knowledge_base_id, rows=payload
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to upsert Neo4j entities.") from exc
        return [self._record_to_entity(record, "entity") for record in records]

    def _read_existing_entities(
        self, knowledge_base_id: str, entity_ids: list[str]
    ) -> dict[str, dict[str, object]]:
        query = f"""
        UNWIND $ids AS id
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: id}})
        RETURN entity.entity_id AS entity_id, entity.type AS type,
               entity.properties_json AS properties_json,
               entity.metadata_json AS metadata_json, entity.version AS version
        """
        try:
            records = self._run_read(
                query, knowledge_base_id=knowledge_base_id, ids=entity_ids
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to read existing Neo4j entities.") from exc
        return {
            cast(str, record["entity_id"]): {
                "type": record["type"],
                "properties_json": record["properties_json"],
                "metadata_json": record.get("metadata_json") or "{}",
                "version": record["version"],
            }
            for record in records
        }

    def _entity_row(
        self,
        entity: Entity,
        *,
        version: int,
        properties_json: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, object]:
        return {
            "entity_id": entity.id,
            "type": entity.type,
            "properties_json": (
                properties_json
                if properties_json is not None
                else _dump_json_property(entity.properties)
            ),
            "metadata_json": (
                metadata_json
                if metadata_json is not None
                else _dump_json_property(entity.metadata)
            ),
            "created_at": entity.created_at.isoformat(),
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
            "version": version,
        }

    def _fold_entity_row(
        self,
        entity: Entity,
        *,
        persisted: dict[str, object] | None,
        prior_row: dict[str, object] | None,
        merge_mode: Literal["merge_properties", "replace_properties"],
    ) -> dict[str, object]:
        """Compute the write payload row for one entity occurrence.

        `persisted` is the row read from Neo4j before this batch ran (constant
        across all occurrences of this id within the batch). `prior_row` is
        the row already computed for an earlier occurrence of the same id
        *within this same batch* (BL-017 tail: intra-batch duplicate-id fold).
        Property/metadata merging cascades through `prior_row` when present so
        later occurrences merge onto earlier ones; version/effective-change
        arithmetic always compares against `persisted` so folding duplicates
        within one call still yields a single logical version transition.
        """

        if persisted is None and prior_row is None:
            return self._entity_row(entity, version=1)

        base_row = prior_row if prior_row is not None else persisted
        assert base_row is not None  # narrows for type-checking; guaranteed by the guard above
        base_properties_json = cast(str, base_row["properties_json"])
        base_metadata_json = cast(str, base_row["metadata_json"])

        new_properties_json = _dump_json_property(entity.properties)
        new_metadata_json = _dump_json_property(entity.metadata)
        if merge_mode == "merge_properties":
            merged_properties = {
                **json.loads(base_properties_json),
                **entity.properties,
            }
            merged_metadata = {
                **json.loads(base_metadata_json),
                **entity.metadata,
            }
            new_properties_json = _dump_json_property(merged_properties)
            new_metadata_json = _dump_json_property(merged_metadata)

        if persisted is not None:
            effective_change = (
                new_properties_json != persisted["properties_json"]
                or entity.type != persisted["type"]
            )
            version = cast(int, persisted["version"]) + (1 if effective_change else 0)
        else:
            version = 1

        row = self._entity_row(
            entity,
            version=version,
            properties_json=new_properties_json,
            metadata_json=new_metadata_json,
        )
        if persisted is not None:
            # UPDATE path: stamp updated_at even when the row is written
            # unconditionally (Neo4j has no true no-op skip, unlike in-memory).
            row["updated_at"] = (entity.updated_at or utc_now()).isoformat()
        return row

    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
        options: GraphUpsertOptions | None = None,
    ) -> list[Relationship]:
        opts = options or GraphUpsertOptions()
        if opts.integrity_mode == "strict":
            endpoint_ids = sorted(
                {r.source_id for r in relationships} | {r.target_id for r in relationships}
            )
            found = self._read_existing_entity_ids(knowledge_base_id, endpoint_ids)
            missing = [eid for eid in endpoint_ids if eid not in found]
            if missing:
                missing_set = set(missing)
                offending = [
                    r.id
                    for r in relationships
                    if r.source_id in missing_set or r.target_id in missing_set
                ]
                raise GraphIntegrityError(
                    knowledge_base_id=knowledge_base_id,
                    missing_entity_ids=missing,
                    relationship_ids=offending,
                )
        existing_rows = self._read_existing_relationships(
            knowledge_base_id, [r.id for r in relationships]
        )
        if opts.expected_version is not None:
            # Conflict pre-pass over the whole batch (against persisted state,
            # not intra-batch fold state): a conflict anywhere writes nothing.
            for relationship in relationships:
                existing = existing_rows.get(relationship.id)
                if existing is not None and existing["version"] != opts.expected_version:
                    raise GraphVersionConflictError(
                        relationship.id,
                        opts.expected_version,
                        cast(int, existing["version"]),
                    )
        payload_by_id: dict[str, dict[str, object]] = {}
        for relationship in relationships:
            payload_by_id[relationship.id] = self._fold_relationship_row(
                relationship,
                persisted=existing_rows.get(relationship.id),
                prior_row=payload_by_id.get(relationship.id),
                merge_mode=opts.merge_mode,
            )
        payload = list(payload_by_id.values())
        endpoint_clause = (
            f"MATCH (source:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.source_id}})\n"
            f"        MATCH (target:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.target_id}})"
            if opts.integrity_mode == "strict"
            else f"MERGE (source:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.source_id}})\n"
            f"        MERGE (target:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.target_id}})"
        )
        query = f"""
        UNWIND $rows AS row
        {endpoint_clause}
        MERGE (source)-[relationship:{_RELATIONSHIP_LABEL} {{
            knowledge_base_id: $knowledge_base_id,
            relationship_id: row.relationship_id
        }}]->(target)
        ON CREATE SET relationship.created_at = row.created_at
        SET relationship.type = row.type,
            relationship.properties_json = row.properties_json,
            relationship.metadata_json = row.metadata_json,
            relationship.updated_at = row.updated_at,
            relationship.version = row.version,
            relationship.weight = row.weight
        RETURN relationship, source.entity_id AS source_id, target.entity_id AS target_id
        """
        try:
            records = self._run_write(
                query, knowledge_base_id=knowledge_base_id, rows=payload
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to upsert Neo4j relationships.") from exc
        return [self._record_to_relationship(record) for record in records]

    def _read_existing_entity_ids(
        self, knowledge_base_id: str, entity_ids: list[str]
    ) -> set[str]:
        query = f"""
        UNWIND $ids AS id
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: id}})
        RETURN entity.entity_id AS entity_id
        """
        try:
            records = self._run_read(
                query, knowledge_base_id=knowledge_base_id, ids=entity_ids
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to verify Neo4j entity endpoints.") from exc
        return {cast(str, record["entity_id"]) for record in records}

    def _read_existing_relationships(
        self, knowledge_base_id: str, relationship_ids: list[str]
    ) -> dict[str, dict[str, object]]:
        query = f"""
        UNWIND $ids AS id
        MATCH ()-[relationship:{_RELATIONSHIP_LABEL} {{knowledge_base_id: $knowledge_base_id, relationship_id: id}}]->()
        RETURN relationship.relationship_id AS relationship_id,
               relationship.type AS type,
               relationship.properties_json AS properties_json,
               relationship.metadata_json AS metadata_json,
               relationship.version AS version, relationship.weight AS weight
        """
        try:
            records = self._run_read(
                query, knowledge_base_id=knowledge_base_id, ids=relationship_ids
            )
        except Neo4jError as exc:
            raise GraphPersistenceError(
                "Failed to read existing Neo4j relationships."
            ) from exc
        return {
            cast(str, record["relationship_id"]): {
                "type": record["type"],
                "properties_json": record["properties_json"],
                # Legacy rows (pre-metadata) return null / lack the key entirely
                # in fake records — normalize to an empty JSON object.
                "metadata_json": record.get("metadata_json") or "{}",
                "version": record["version"],
                "weight": record["weight"],
            }
            for record in records
        }

    def _relationship_row(
        self,
        relationship: Relationship,
        *,
        version: int,
        properties_json: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, object]:
        return {
            "relationship_id": relationship.id,
            "type": relationship.type,
            "source_id": relationship.source_id,
            "target_id": relationship.target_id,
            "properties_json": (
                properties_json
                if properties_json is not None
                else _dump_json_property(relationship.properties)
            ),
            "metadata_json": (
                metadata_json
                if metadata_json is not None
                else _dump_json_property(relationship.metadata)
            ),
            "created_at": relationship.created_at.isoformat(),
            "updated_at": relationship.updated_at.isoformat()
            if relationship.updated_at
            else None,
            "version": version,
            "weight": relationship.weight,
        }

    def _fold_relationship_row(
        self,
        relationship: Relationship,
        *,
        persisted: dict[str, object] | None,
        prior_row: dict[str, object] | None,
        merge_mode: Literal["merge_properties", "replace_properties"],
    ) -> dict[str, object]:
        """Compute the write payload row for one relationship occurrence.

        Mirrors `_fold_entity_row`: `persisted` is the pre-batch Neo4j row,
        `prior_row` is the row computed for an earlier occurrence of the same
        id within this batch. Merging cascades through `prior_row`; the
        version/effective-change arithmetic compares against `persisted` only,
        and metadata changes alone never bump the version.
        """

        if persisted is None and prior_row is None:
            return self._relationship_row(relationship, version=1)

        base_row = prior_row if prior_row is not None else persisted
        assert base_row is not None  # narrows for type-checking; guaranteed by the guard above
        base_properties_json = cast(str, base_row["properties_json"])
        base_metadata_json = cast(str, base_row["metadata_json"])

        new_properties_json = _dump_json_property(relationship.properties)
        new_metadata_json = _dump_json_property(relationship.metadata)
        if merge_mode == "merge_properties":
            merged_properties = {
                **json.loads(base_properties_json),
                **relationship.properties,
            }
            merged_metadata = {
                **json.loads(base_metadata_json),
                **relationship.metadata,
            }
            new_properties_json = _dump_json_property(merged_properties)
            new_metadata_json = _dump_json_property(merged_metadata)

        if persisted is not None:
            effective_change = (
                new_properties_json != persisted["properties_json"]
                or relationship.type != persisted["type"]
                or relationship.weight != persisted["weight"]
            )
            version = cast(int, persisted["version"]) + (1 if effective_change else 0)
        else:
            version = 1

        row = self._relationship_row(
            relationship,
            version=version,
            properties_json=new_properties_json,
            metadata_json=new_metadata_json,
        )
        if persisted is not None:
            # UPDATE path: stamp updated_at even when the row is written
            # unconditionally (Neo4j has no true no-op skip, unlike in-memory).
            row["updated_at"] = (relationship.updated_at or utc_now()).isoformat()
        return row

    def get_entities(self, knowledge_base_id: str) -> list[Entity]:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        RETURN entity
        ORDER BY entity.entity_id
        """
        return self._query_entities(query, knowledge_base_id=knowledge_base_id)

    def get_relationships(self, knowledge_base_id: str) -> list[Relationship]:
        query = f"""
        MATCH (source:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
              -[relationship:{_RELATIONSHIP_LABEL} {{knowledge_base_id: $knowledge_base_id}}]->
              (target:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        RETURN relationship, source.entity_id AS source_id, target.entity_id AS target_id
        ORDER BY relationship.relationship_id
        """
        return self._query_relationships(query, knowledge_base_id=knowledge_base_id)

    def get_entity(self, knowledge_base_ids: list[str], entity_id: str) -> Entity | None:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{entity_id: $entity_id}})
        WHERE entity.knowledge_base_id IN $knowledge_base_ids
        RETURN entity
        LIMIT 1
        """
        entities = self._query_entities(
            query,
            knowledge_base_ids=knowledge_base_ids,
            entity_id=entity_id,
        )
        return entities[0] if entities else None

    def update_entity_properties(
        self,
        knowledge_base_id: str,
        entity_id: str,
        properties: dict[str, object],
    ) -> Entity:
        existing = self.get_entity([knowledge_base_id], entity_id)
        if existing is None:
            raise KeyError(
                f"Entity '{entity_id}' not found in knowledge base '{knowledge_base_id}'."
            )
        merged_properties: dict[str, object] = dict(existing.properties)
        for key, value in properties.items():
            merged_properties[key] = value
        updated = existing.model_copy(update={"properties": merged_properties})
        self.upsert_entities(knowledge_base_id, [updated])
        return updated

    def get_neighbors(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
        direction: Literal["in", "out", "both"],
    ) -> SubgraphResult:
        if direction not in {"in", "out", "both"}:
            msg = "direction must be one of 'in', 'out', or 'both'"
            raise ValueError(msg)

        root_entity = self.get_entity([knowledge_base_id], entity_id)
        if root_entity is None:
            return SubgraphResult()
        if depth == 0:
            return SubgraphResult(entities=[root_entity], relationships=[])
        if depth < 0 or depth > _MAX_NEIGHBOR_DEPTH:
            raise ValueError(
                f"Neo4j neighborhood depth must be between 0 and {_MAX_NEIGHBOR_DEPTH}."
            )

        pattern = self._path_pattern_for(direction, depth)
        query = f"""
        MATCH (root:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: $entity_id}})
        OPTIONAL MATCH path = {pattern}
        WHERE path IS NULL
           OR all(relationship IN relationships(path) WHERE relationship.knowledge_base_id = $knowledge_base_id)
        RETURN root,
               path,
               CASE
                   WHEN path IS NULL THEN []
                   ELSE [relationship IN relationships(path) | startNode(relationship).entity_id]
               END AS relationship_source_ids,
               CASE
                   WHEN path IS NULL THEN []
                   ELSE [relationship IN relationships(path) | endNode(relationship).entity_id]
               END AS relationship_target_ids
        """

        try:
            records = self._run_read(
                query,
                knowledge_base_id=knowledge_base_id,
                entity_id=entity_id,
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to query Neo4j neighborhood.") from exc

        entities_by_id: dict[str, Entity] = {root_entity.id: root_entity}
        relationships_by_id: dict[str, Relationship] = {}

        for record in records:
            root_node = cast(Neo4jPropertyContainerProtocol, record["root"])
            entities_by_id.setdefault(
                cast(str, root_node["entity_id"]),
                self._node_to_entity(root_node),
            )
            path = cast(Neo4jPathProtocol | None, record["path"])
            if path is None:
                continue

            relationship_source_ids = cast(Sequence[str], record["relationship_source_ids"])
            relationship_target_ids = cast(Sequence[str], record["relationship_target_ids"])

            for node in path.nodes:
                entity = self._node_to_entity(node)
                entities_by_id.setdefault(entity.id, entity)
            for index, relationship in enumerate(path.relationships):
                materialized = self._relationship_to_model(
                    relationship,
                    source_id=relationship_source_ids[index],
                    target_id=relationship_target_ids[index],
                )
                relationships_by_id.setdefault(materialized.id, materialized)

        return SubgraphResult(
            entities=list(entities_by_id.values()),
            relationships=list(relationships_by_id.values()),
        )

    def get_subgraph(
        self,
        knowledge_base_id: str,
        seed_entity_ids: list[str],
        depth: int = 1,
    ) -> SubgraphResult:
        seeds = list(dict.fromkeys(seed_entity_ids))
        if not seeds:
            return SubgraphResult()
        if depth < 0 or depth > _MAX_NEIGHBOR_DEPTH:
            raise ValueError(
                f"Neo4j subgraph depth must be between 0 and {_MAX_NEIGHBOR_DEPTH}."
            )

        if depth == 0:
            query = f"""
            MATCH (root:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
            WHERE root.entity_id IN $seed_entity_ids
            RETURN root
            """
            try:
                records = self._run_read(
                    query,
                    knowledge_base_id=knowledge_base_id,
                    seed_entity_ids=seeds,
                )
            except Neo4jError as exc:
                raise GraphPersistenceError("Failed to query Neo4j subgraph.") from exc
            seed_entities_by_id: dict[str, Entity] = {}
            for record in records:
                node = cast(Neo4jPropertyContainerProtocol, record["root"])
                entity = self._node_to_entity(node)
                seed_entities_by_id.setdefault(entity.id, entity)
            return SubgraphResult(entities=list(seed_entities_by_id.values()), relationships=[])

        pattern = self._path_pattern_for("both", depth)
        query = f"""
        MATCH (root:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        WHERE root.entity_id IN $seed_entity_ids
        OPTIONAL MATCH path = {pattern}
        WHERE path IS NULL
           OR all(relationship IN relationships(path) WHERE relationship.knowledge_base_id = $knowledge_base_id)
        RETURN root,
               path,
               CASE
                   WHEN path IS NULL THEN []
                   ELSE [relationship IN relationships(path) | startNode(relationship).entity_id]
               END AS relationship_source_ids,
               CASE
                   WHEN path IS NULL THEN []
                   ELSE [relationship IN relationships(path) | endNode(relationship).entity_id]
               END AS relationship_target_ids
        """

        try:
            records = self._run_read(
                query,
                knowledge_base_id=knowledge_base_id,
                seed_entity_ids=seeds,
            )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to query Neo4j subgraph.") from exc

        entities_by_id: dict[str, Entity] = {}
        relationships_by_id: dict[str, Relationship] = {}

        for record in records:
            root_node = cast(Neo4jPropertyContainerProtocol, record["root"])
            root_entity = self._node_to_entity(root_node)
            entities_by_id.setdefault(root_entity.id, root_entity)
            path = cast(Neo4jPathProtocol | None, record["path"])
            if path is None:
                continue

            relationship_source_ids = cast(Sequence[str], record["relationship_source_ids"])
            relationship_target_ids = cast(Sequence[str], record["relationship_target_ids"])

            for node in path.nodes:
                entity = self._node_to_entity(node)
                entities_by_id.setdefault(entity.id, entity)
            for index, relationship in enumerate(path.relationships):
                materialized = self._relationship_to_model(
                    relationship,
                    source_id=relationship_source_ids[index],
                    target_id=relationship_target_ids[index],
                )
                relationships_by_id.setdefault(materialized.id, materialized)

        return SubgraphResult(
            entities=list(entities_by_id.values()),
            relationships=list(relationships_by_id.values()),
        )

    def get_entities_by_type(
        self,
        knowledge_base_id: str,
        entity_type: str,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        WHERE entity.type = $entity_type
        RETURN entity
        ORDER BY entity.entity_id
        SKIP $offset
        LIMIT $limit
        """
        return self._query_entities(
            query,
            knowledge_base_id=knowledge_base_id,
            entity_type=entity_type,
            limit=limit,
            offset=offset,
        )

    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
    ) -> list[Entity]:
        normalized_query = query.strip()
        if normalized_query == "":
            return []

        # Use the entity_properties_fulltext index created in _ensure_schema
        # so the lookup is an indexed seek rather than a sequential
        # CONTAINS scan over properties_json. The kb-id WHERE clause is a
        # cheap predicate on the already-seeked rows. Results are ordered
        # by Lucene relevance, then by entity_id for stable ties.
        cypher = """
        CALL db.index.fulltext.queryNodes('entity_properties_fulltext', $normalized_query)
        YIELD node, score
        WHERE node.knowledge_base_id IN $knowledge_base_ids
        RETURN node AS entity
        ORDER BY score DESC, node.entity_id
        LIMIT $limit
        """
        return self._query_entities(
            cypher,
            knowledge_base_ids=knowledge_base_ids,
            normalized_query=normalized_query,
            limit=limit,
        )

    def count_entities(self, knowledge_base_id: str) -> int:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        RETURN count(entity) AS count
        """
        return self._query_count(query, knowledge_base_id=knowledge_base_id)

    def count_relationships(self, knowledge_base_id: str) -> int:
        query = f"""
        MATCH ()-[relationship:{_RELATIONSHIP_LABEL} {{knowledge_base_id: $knowledge_base_id}}]->()
        RETURN count(relationship) AS count
        """
        return self._query_count(query, knowledge_base_id=knowledge_base_id)

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        DETACH DELETE entity
        """
        self._execute_write(query, knowledge_base_id=knowledge_base_id)

    def delete_entity(self, knowledge_base_id: str, entity_id: str) -> None:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: $entity_id}})
        DETACH DELETE entity
        """
        self._execute_write(query, knowledge_base_id=knowledge_base_id, entity_id=entity_id)

    def delete_relationship(self, knowledge_base_id: str, relationship_id: str) -> None:
        query = f"""
        MATCH ()-[relationship:{_RELATIONSHIP_LABEL} {{
            knowledge_base_id: $knowledge_base_id,
            relationship_id: $relationship_id
        }}]->()
        DELETE relationship
        """
        self._execute_write(
            query,
            knowledge_base_id=knowledge_base_id,
            relationship_id=relationship_id,
        )

    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance:
        # NOTE: metadata is stored as a JSON-serialized string (metadata_json) rather than as
        # flattened node properties — this is Pattern B.  We filter by checking that the
        # metadata_json string contains the expected key-value pair encoded exactly as it would
        # be by json.dumps with sort_keys=True.  The filter may over-match if a value contains
        # the literal substring, but in practice source_document_id values are UUIDs or slugs
        # that make false positives negligible.  A future schema migration that promotes
        # source_document_id to a first-class indexed node/relationship property would make
        # this query exact and efficient (add an index on e.source_document_id to support it).
        doc_id_fragment = f'"{SOURCE_DOCUMENT_ID_KEY}": "{source_document_id}"'

        # Using a two-step approach: count before delete, then delete.
        rel_count_fetch = f"""
        MATCH ()-[r:{_RELATIONSHIP_LABEL} {{knowledge_base_id: $knowledge_base_id}}]->()
        WHERE r.metadata_json CONTAINS $doc_id_fragment
        RETURN count(r) AS count
        """
        entity_count_fetch = f"""
        MATCH (e:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        WHERE e.metadata_json CONTAINS $doc_id_fragment
        RETURN count(e) AS count
        """
        del_rels_query = f"""
        MATCH ()-[r:{_RELATIONSHIP_LABEL} {{knowledge_base_id: $knowledge_base_id}}]->()
        WHERE r.metadata_json CONTAINS $doc_id_fragment
        DELETE r
        """
        del_entities_query = f"""
        MATCH (e:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        WHERE e.metadata_json CONTAINS $doc_id_fragment
        DETACH DELETE e
        """

        try:
            rel_count = self._query_count(
                rel_count_fetch,
                knowledge_base_id=knowledge_base_id,
                doc_id_fragment=doc_id_fragment,
            )
            entity_count = self._query_count(
                entity_count_fetch,
                knowledge_base_id=knowledge_base_id,
                doc_id_fragment=doc_id_fragment,
            )
            self._run_write(del_rels_query, knowledge_base_id=knowledge_base_id, doc_id_fragment=doc_id_fragment)
            self._run_write(del_entities_query, knowledge_base_id=knowledge_base_id, doc_id_fragment=doc_id_fragment)
        except Neo4jError as exc:
            raise GraphPersistenceError(
                "Failed to delete Neo4j nodes/relationships by source document."
            ) from exc

        return GraphDeleteByProvenance(
            knowledge_base_id=knowledge_base_id,
            source_document_id=source_document_id,
            entity_count=entity_count,
            relationship_count=rel_count,
        )

    def _execute_write(self, query: str, **parameters: object) -> None:
        try:
            self._run_write(query, **parameters)
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to execute Neo4j write operation.") from exc

    def _query_entities(self, query: str, **parameters: object) -> list[Entity]:
        try:
            records = self._run_read(query, **parameters)
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to query Neo4j entities.") from exc
        return [self._record_to_entity(record, "entity") for record in records]

    def _query_relationships(self, query: str, **parameters: object) -> list[Relationship]:
        try:
            records = self._run_read(query, **parameters)
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to query Neo4j relationships.") from exc
        return [self._record_to_relationship(record) for record in records]

    def _query_count(self, query: str, **parameters: object) -> int:
        try:
            records = self._run_read(query, **parameters)
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to query Neo4j aggregate count.") from exc
        return cast(int, records[0]["count"]) if records else 0

    @contextmanager
    def _transaction_scope(self) -> Generator[None, None, None]:
        if self._active_transaction is not None:
            raise RuntimeError("Nested Neo4j transactions are not supported.")

        with self._session() as session:
            transaction = session.begin_transaction()
            self._active_session = session
            self._active_transaction = transaction
            try:
                yield
            except Exception:
                transaction.rollback()
                raise
            else:
                transaction.commit()
            finally:
                self._active_transaction = None
                self._active_session = None

    def _run_read(self, query: str, **parameters: object) -> list[Neo4jRecordProtocol]:
        if self._active_transaction is not None:
            return self._run_query(self._active_transaction, query, **parameters)

        with self._session() as session:
            return session.execute_read(self._run_query, query, **parameters)

    def _run_write(self, query: str, **parameters: object) -> list[Neo4jRecordProtocol]:
        if self._active_transaction is not None:
            return self._run_query(self._active_transaction, query, **parameters)

        with self._session() as session:
            return session.execute_write(self._run_query, query, **parameters)

    def _session(self) -> Neo4jSessionProtocol:
        if self._database is None:
            return self._driver.session()
        return self._driver.session(database=self._database)

    @staticmethod
    def _run_query(
        transaction: Neo4jTransactionProtocol,
        query: str,
        **parameters: object,
    ) -> list[Neo4jRecordProtocol]:
        return list(transaction.run(query, **parameters))

    @staticmethod
    def _record_to_entity(record: Neo4jRecordProtocol, key: str) -> Entity:
        return Neo4jGraphRepository._node_to_entity(record[key])

    @staticmethod
    def _record_to_relationship(record: Neo4jRecordProtocol) -> Relationship:
        return Neo4jGraphRepository._relationship_to_model(
            record["relationship"],
            source_id=cast(str, record["source_id"]),
            target_id=cast(str, record["target_id"]),
        )

    @staticmethod
    def _node_to_entity(node: object) -> Entity:
        container = cast(Neo4jPropertyContainerProtocol, node)
        return Entity(
            id=cast(str, container["entity_id"]),
            type=cast(str, container["type"]),
            properties=_load_json_mapping(container, "properties"),
            metadata=_load_json_mapping(container, "metadata"),
            created_at=cast(datetime, container["created_at"]),
            updated_at=cast(datetime | None, container.get("updated_at")),
            version=cast(int, container.get("version", 1)),
        )

    @staticmethod
    def _relationship_to_model(
        relationship: object,
        *,
        source_id: str,
        target_id: str,
    ) -> Relationship:
        container = cast(Neo4jPropertyContainerProtocol, relationship)
        return Relationship(
            id=cast(str, container["relationship_id"]),
            type=cast(str, container["type"]),
            source_id=source_id,
            target_id=target_id,
            properties=_load_json_mapping(container, "properties"),
            metadata=_load_json_mapping(container, "metadata"),
            created_at=cast(datetime, container["created_at"]),
            updated_at=cast(datetime | None, container.get("updated_at")),
            version=cast(int, container.get("version", 1)),
            weight=cast(float | None, container.get("weight")),
        )

    @staticmethod
    def _path_pattern_for(direction: Literal["in", "out", "both"], depth: int) -> str:
        if direction == "out":
            return f"(root)-[:{_RELATIONSHIP_LABEL}*1..{depth}]->(neighbor:{_ENTITY_LABEL})"
        if direction == "in":
            return f"(root)<-[:{_RELATIONSHIP_LABEL}*1..{depth}]-(neighbor:{_ENTITY_LABEL})"
        return f"(root)-[:{_RELATIONSHIP_LABEL}*1..{depth}]-(neighbor:{_ENTITY_LABEL})"


def _dump_json_property(value: dict[str, object]) -> str:
    """Serialize nested entity data into a Neo4j-safe scalar property."""

    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)


def _load_json_mapping(
    container: Neo4jPropertyContainerProtocol,
    property_name: str,
) -> dict[str, object]:
    """Load JSON-backed mappings while tolerating legacy fake/test records."""

    legacy_value = container.get(property_name, None)
    if isinstance(legacy_value, dict):
        return cast(dict[str, object], legacy_value)

    json_value = container.get(f"{property_name}_json", None)
    if not isinstance(json_value, str) or json_value.strip() == "":
        return {}
    parsed = json.loads(json_value)
    if not isinstance(parsed, dict):
        return {}
    return cast(dict[str, object], parsed)