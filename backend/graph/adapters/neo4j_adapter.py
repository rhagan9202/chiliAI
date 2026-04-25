"""Neo4j graph repository adapter."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
import importlib
from types import TracebackType
from typing import Literal, Protocol, cast

from config.schema import GraphDbConfig
from graph.adapters.protocols import GraphRepository
from graph.exceptions import GraphPersistenceError
from graph.models import SubgraphResult
from shared.types import Entity, Relationship


class Neo4jRecordProtocol(Protocol):
    def __getitem__(self, key: str) -> object: ...


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

    def close(self) -> None:
        self._driver.close()

    def transaction(self, knowledge_base_id: str) -> AbstractContextManager[None]:
        return self._transaction_scope()

    def upsert_entities(self, knowledge_base_id: str, entities: list[Entity]) -> list[Entity]:
        payload = [
            {
                "entity_id": entity.id,
                "type": entity.type,
                "properties": entity.properties,
                "metadata": entity.metadata,
                "created_at": entity.created_at.isoformat(),
                "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
                "version": entity.version,
            }
            for entity in entities
        ]
        query = f"""
        UNWIND $rows AS row
        MERGE (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.entity_id}})
        ON CREATE SET entity.created_at = row.created_at
        SET entity.type = row.type,
            entity.properties = row.properties,
            entity.metadata = row.metadata,
            entity.updated_at = row.updated_at,
            entity.version = row.version
        RETURN entity
        """

        try:
            with self._session() as session:
                records = session.execute_write(
                    self._run_query,
                    query,
                    knowledge_base_id=knowledge_base_id,
                    rows=payload,
                )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to upsert Neo4j entities.") from exc

        return [self._record_to_entity(record, "entity") for record in records]

    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
    ) -> list[Relationship]:
        payload = [
            {
                "relationship_id": relationship.id,
                "type": relationship.type,
                "source_id": relationship.source_id,
                "target_id": relationship.target_id,
                "properties": relationship.properties,
                "created_at": relationship.created_at.isoformat(),
                "updated_at": relationship.updated_at.isoformat()
                if relationship.updated_at
                else None,
                "version": relationship.version,
                "weight": relationship.weight,
            }
            for relationship in relationships
        ]
        query = f"""
        UNWIND $rows AS row
        MERGE (source:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.source_id}})
        MERGE (target:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: row.target_id}})
        MERGE (source)-[relationship:{_RELATIONSHIP_LABEL} {{
            knowledge_base_id: $knowledge_base_id,
            relationship_id: row.relationship_id
        }}]->(target)
        ON CREATE SET relationship.created_at = row.created_at
        SET relationship.type = row.type,
            relationship.properties = row.properties,
            relationship.updated_at = row.updated_at,
            relationship.version = row.version,
            relationship.weight = row.weight
        RETURN relationship, source.entity_id AS source_id, target.entity_id AS target_id
        """

        try:
            with self._session() as session:
                records = session.execute_write(
                    self._run_query,
                    query,
                    knowledge_base_id=knowledge_base_id,
                    rows=payload,
                )
        except Neo4jError as exc:
            raise GraphPersistenceError("Failed to upsert Neo4j relationships.") from exc

        return [self._record_to_relationship(record) for record in records]

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

    def get_entity(self, knowledge_base_id: str, entity_id: str) -> Entity | None:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id, entity_id: $entity_id}})
        RETURN entity
        LIMIT 1
        """
        entities = self._query_entities(
            query,
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
        )
        return entities[0] if entities else None

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

        root_entity = self.get_entity(knowledge_base_id, entity_id)
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
            with self._session() as session:
                records = session.execute_read(
                    self._run_query,
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
        knowledge_base_id: str,
        query: str,
        limit: int,
    ) -> list[Entity]:
        normalized_query = query.strip().lower()
        if normalized_query == "":
            return []

        cypher = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        WHERE any(
            key IN keys(entity.properties)
            WHERE entity.properties[key] IS STRING
              AND toLower(entity.properties[key]) CONTAINS $normalized_query
        )
        RETURN entity
        ORDER BY entity.entity_id
        LIMIT $limit
        """
        return self._query_entities(
            cypher,
            knowledge_base_id=knowledge_base_id,
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
            properties=cast(dict[str, object], container.get("properties", {})),
            metadata=cast(dict[str, object], container.get("metadata", {})),
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
            properties=cast(dict[str, object], container.get("properties", {})),
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