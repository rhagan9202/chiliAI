"""Qdrant-backed vector store adapter."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, cast
from uuid import NAMESPACE_URL, uuid5

from config.schema import VectorStoreConfig
from shared.provenance import SOURCE_DOCUMENT_ID_KEY
from vectorstore.exceptions import VectorDimensionMismatchError, VectorStoreError
from vectorstore.models import MetadataValue, VectorMatch, VectorRecord

if TYPE_CHECKING:
    from qdrant_client import QdrantClient as QdrantClientType
    from qdrant_client.http.models.models import (
        CountResult,
        Distance,
        FieldCondition,
        Filter,
        FilterSelector,
        MatchValue,
        PointIdsList,
        PointStruct,
        QueryResponse,
        Range,
        Record,
        ScoredPoint,
        VectorParams,
    )


class QdrantClientProtocol(Protocol):
    def collection_exists(self, collection_name: str, **kwargs: object) -> bool: ...

    def get_collection(self, collection_name: str, **kwargs: object) -> object: ...

    def create_collection(
        self,
        collection_name: str,
        vectors_config: object,
        **kwargs: object,
    ) -> bool: ...

    def upsert(
        self,
        collection_name: str,
        points: Sequence[PointStruct],
        **kwargs: object,
    ) -> object: ...

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        query_filter: Filter | None,
        limit: int,
        with_payload: bool,
        **kwargs: object,
    ) -> QueryResponse: ...

    def delete(
        self,
        collection_name: str,
        points_selector: PointIdsList | FilterSelector,
        **kwargs: object,
    ) -> object: ...

    def retrieve(
        self,
        collection_name: str,
        ids: Sequence[str],
        with_payload: bool,
        with_vectors: bool,
        **kwargs: object,
    ) -> list[Record]: ...

    def count(
        self,
        collection_name: str,
        exact: bool,
        count_filter: Filter | None = None,
        **kwargs: object,
    ) -> CountResult: ...

    def delete_collection(self, collection_name: str, **kwargs: object) -> bool: ...


class QdrantModelsProtocol(Protocol):
    Distance: type[Distance]
    VectorParams: type[VectorParams]
    PointStruct: type[PointStruct]
    Filter: type[Filter]
    FieldCondition: type[FieldCondition]
    MatchValue: type[MatchValue]
    PointIdsList: type[PointIdsList]
    FilterSelector: type[FilterSelector]
    Range: type[Range]

try:  # pragma: no cover - optional dependency
    from qdrant_client import QdrantClient
    from qdrant_client import models as qdrant_models
except ImportError:  # pragma: no cover - optional dependency
    QdrantClient = None
    qdrant_models = None

__all__ = ["QdrantVectorStore"]


class QdrantVectorStore:
    """Persist vector records and execute similarity search through Qdrant."""

    def __init__(
        self,
        config: VectorStoreConfig,
        *,
        client: QdrantClientProtocol | None = None,
    ) -> None:
        client_class = _require_qdrant_client_class()
        if client is None and (config.uri is None or config.uri.strip() == ""):
            raise ValueError("QdrantVectorStore requires VectorStoreConfig.uri to be set.")

        self._config = config
        self._client: QdrantClientProtocol = cast(
            QdrantClientProtocol,
            client
            or client_class(
                url=config.uri,
                prefer_grpc=False,
                # Client construction performs no network I/O here; server
                # version compatibility is exercised by the integration tests
                # that run against a live Qdrant instance.
                check_compatibility=False,
            ),
        )
        self._distance: Distance = _distance_for(config.distance_metric)

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]:
        if not records:
            return []

        dimension = self._validate_batch_dimensions(records)
        collection_name = self._collection_name(knowledge_base_id)

        try:
            self._ensure_collection(collection_name, dimension)
            self._client.upsert(
                collection_name=collection_name,
                points=[self._point_for(record) for record in records],
                wait=True,
            )
        except VectorDimensionMismatchError:
            raise
        except Exception as exc:
            raise VectorStoreError("Failed to upsert Qdrant vector records.") from exc

        return list(records)

    def search(
        self,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, MetadataValue] | None = None,
    ) -> list[VectorMatch]:
        self._validate_query_dimension(query_vector)
        collection_name = self._collection_name(knowledge_base_id)

        try:
            if not self._client.collection_exists(collection_name):
                return []

            response = self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=self._build_filter(filters),
                limit=limit,
                with_payload=True,
            )
        except VectorDimensionMismatchError:
            raise
        except Exception as exc:
            raise VectorStoreError("Failed to search Qdrant vector records.") from exc

        try:
            return [self._match_from_scored_point(point) for point in response.points]
        except Exception as exc:
            raise VectorStoreError("Failed to search Qdrant vector records.") from exc

    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None:
        collection_name = self._collection_name(knowledge_base_id)
        try:
            if not self._client.collection_exists(collection_name):
                return None
            records = self._client.retrieve(
                collection_name=collection_name,
                ids=[_point_id_for(record_id)],
                with_payload=True,
                with_vectors=True,
            )
            if not records:
                return None
            return self._record_from_qdrant_record(records[0], knowledge_base_id)
        except Exception as exc:
            raise VectorStoreError("Failed to retrieve Qdrant vector record.") from exc

    def count_records(self, knowledge_base_id: str) -> int:
        collection_name = self._collection_name(knowledge_base_id)
        try:
            if not self._client.collection_exists(collection_name):
                return 0
            result = self._client.count(collection_name=collection_name, exact=True)
        except Exception as exc:
            raise VectorStoreError("Failed to count Qdrant vector records.") from exc
        return int(result.count)

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        if self.get_record(knowledge_base_id, record_id) is None:
            return False
        self.delete_records(knowledge_base_id, [record_id])
        return True

    def delete_namespace(self, knowledge_base_id: str) -> int:
        collection_name = self._collection_name(knowledge_base_id)
        try:
            if not self._client.collection_exists(collection_name):
                return 0
            deleted_count = self.count_records(knowledge_base_id)
            if not self._client.delete_collection(collection_name=collection_name):
                raise VectorStoreError(
                    "Qdrant collection deletion was not acknowledged."
                )
        except Exception as exc:
            raise VectorStoreError("Failed to delete Qdrant vector namespace.") from exc
        return deleted_count

    def delete_records(self, knowledge_base_id: str, record_ids: Sequence[str]) -> int:
        """Delete the provided record IDs from the Qdrant collection."""

        if not record_ids:
            return 0

        collection_name = self._collection_name(knowledge_base_id)
        try:
            if not self._client.collection_exists(collection_name):
                return 0

            self._client.delete(
                collection_name=collection_name,
                points_selector=_require_qdrant_models().PointIdsList(
                    points=[_point_id_for(record_id) for record_id in record_ids]
                ),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Failed to delete Qdrant vector records.") from exc

        return len(record_ids)

    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> int:
        """Delete all vector records whose metadata matches the given source document ID."""

        collection_name = self._collection_name(knowledge_base_id)
        try:
            if not self._client.collection_exists(collection_name):
                return 0

            models_module = _require_qdrant_models()
            doc_filter = models_module.Filter(
                must=[
                    _field_condition_for_filter(SOURCE_DOCUMENT_ID_KEY, source_document_id),
                ]
            )
            # Count before deleting so we can return an accurate count.
            count_result = self._client.count(
                collection_name=collection_name,
                exact=True,
                count_filter=doc_filter,
            )
            deleted_count = int(count_result.count)
            if deleted_count == 0:
                return 0

            self._client.delete(
                collection_name=collection_name,
                points_selector=models_module.FilterSelector(filter=doc_filter),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError(
                "Failed to delete Qdrant vector records by source document."
            ) from exc

        return deleted_count

    def _validate_batch_dimensions(self, records: list[VectorRecord]) -> int:
        dimension = len(records[0].embedding)
        for record in records:
            if len(record.embedding) != dimension:
                raise VectorDimensionMismatchError(
                    "All records in a batch must have the same embedding dimension."
                )
        return dimension

    def _validate_query_dimension(self, query_vector: list[float]) -> None:
        if len(query_vector) != self._config.dimensions:
            raise VectorDimensionMismatchError(
                "Query vector dimension does not match the configured Qdrant collection dimension."
            )

    def _ensure_collection(self, collection_name: str, dimension: int) -> None:
        if self._client.collection_exists(collection_name):
            existing_dimension = self._collection_dimension(collection_name)
            if existing_dimension != dimension:
                raise VectorDimensionMismatchError(
                    "Embedding dimension does not match the existing Qdrant collection dimension."
                )
            return

        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=_require_qdrant_models().VectorParams(
                size=dimension,
                distance=self._distance,
            ),
        )

    def _collection_dimension(self, collection_name: str) -> int:
        collection = self._client.get_collection(collection_name)
        config = getattr(collection, "config", None)
        params = getattr(config, "params", None)
        vectors = getattr(params, "vectors", None)
        size = getattr(vectors, "size", None)
        if isinstance(size, int):
            return size
        raise VectorStoreError(
            "Failed to determine Qdrant collection vector dimension."
        )

    def _point_for(self, record: VectorRecord) -> PointStruct:
        return _require_qdrant_models().PointStruct(
            id=_point_id_for(record.id),
            vector=list(record.embedding),
            payload={
                "record_id": record.id,
                "content_id": record.content_id,
                "content": record.content,
                "metadata": dict(record.metadata),
                "knowledge_base_id": record.knowledge_base_id,
                "indexed_at": record.indexed_at.isoformat(),
            },
        )

    def _build_filter(
        self,
        filters: dict[str, MetadataValue] | None,
    ) -> Filter | None:
        if not filters:
            return None

        models_module = _require_qdrant_models()
        return models_module.Filter(
            must=[
                _field_condition_for_filter(key, value)
                for key, value in filters.items()
            ]
        )

    def _match_from_scored_point(self, point: ScoredPoint) -> VectorMatch:
        payload = cast(dict[str, object], point.payload or {})
        raw_metadata = payload.get("metadata", {})

        return VectorMatch(
            record_id=cast(str, payload.get("record_id", str(point.id))),
            content_id=cast(str, payload["content_id"]),
            score=float(point.score),
            content=cast(str | None, payload.get("content")),
            metadata=cast(dict[str, MetadataValue], raw_metadata),
        )

    def _record_from_qdrant_record(
        self,
        record: Record,
        knowledge_base_id: str,
    ) -> VectorRecord:
        payload = cast(dict[str, object], record.payload or {})
        raw_vector = record.vector
        if not isinstance(raw_vector, list) or any(
            isinstance(value, list) for value in raw_vector
        ):
            raise VectorStoreError("Qdrant record did not include a dense vector.")
        dense_vector = cast(list[float], raw_vector)
        record_data: dict[str, object] = {
            "id": cast(str, payload.get("record_id", str(record.id))),
            "knowledge_base_id": cast(
                str,
                payload.get("knowledge_base_id", knowledge_base_id),
            ),
            "content_id": cast(str, payload["content_id"]),
            "embedding": [float(value) for value in dense_vector],
            "content": cast(str | None, payload.get("content")),
            "metadata": cast(dict[str, MetadataValue], payload.get("metadata", {})),
        }
        indexed_at = payload.get("indexed_at")
        if indexed_at is not None:
            record_data["indexed_at"] = datetime.fromisoformat(cast(str, indexed_at))
        return VectorRecord.model_validate(record_data)

    @staticmethod
    def _collection_name(knowledge_base_id: str) -> str:
        return f"chili_{knowledge_base_id}"


def _point_id_for(record_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, record_id))


def _distance_for(distance_metric: str) -> Distance:
    models_module = _require_qdrant_models()
    distance_by_metric = {
        "cosine": models_module.Distance.COSINE,
        "dot": models_module.Distance.DOT,
        "euclidean": models_module.Distance.EUCLID,
    }
    try:
        return distance_by_metric[distance_metric]
    except KeyError as exc:  # pragma: no cover - schema validation should guard this
        raise ValueError(f"Unsupported Qdrant distance metric '{distance_metric}'.") from exc


def _coerce_filter_value(value: str | int | bool) -> str | int | bool:
    return value


def _field_condition_for_filter(key: str, value: MetadataValue) -> FieldCondition:
    models_module = _require_qdrant_models()
    if isinstance(value, float):
        return models_module.FieldCondition(
            key=f"metadata.{key}",
            range=models_module.Range(gte=value, lte=value),
        )
    return models_module.FieldCondition(
        key=f"metadata.{key}",
        match=models_module.MatchValue(value=_coerce_filter_value(value)),
    )


def _require_qdrant_client_class() -> type[QdrantClientType]:
    if QdrantClient is None:  # pragma: no cover - optional dependency guard
        raise ImportError("qdrant-client is required for QdrantVectorStore.")
    return QdrantClient


def _require_qdrant_models() -> QdrantModelsProtocol:
    if qdrant_models is None:  # pragma: no cover - optional dependency guard
        raise ImportError("qdrant-client is required for QdrantVectorStore.")
    return cast(QdrantModelsProtocol, qdrant_models)
