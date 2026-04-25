"""Qdrant-backed vector store adapter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, cast

from config.schema import VectorStoreConfig
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.exceptions import VectorDimensionMismatchError, VectorStoreError
from vectorstore.models import MetadataValue, VectorMatch, VectorRecord

if TYPE_CHECKING:
    from qdrant_client import QdrantClient as QdrantClientType
    from qdrant_client.http.models.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointIdsList,
        PointStruct,
        QueryResponse,
        Range,
        ScoredPoint,
        VectorParams,
    )


class QdrantClientProtocol(Protocol):
    def collection_exists(self, collection_name: str, **kwargs: object) -> bool: ...

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
        points_selector: PointIdsList,
        **kwargs: object,
    ) -> object: ...


class QdrantModelsProtocol(Protocol):
    Distance: type[Distance]
    VectorParams: type[VectorParams]
    PointStruct: type[PointStruct]
    Filter: type[Filter]
    FieldCondition: type[FieldCondition]
    MatchValue: type[MatchValue]
    PointIdsList: type[PointIdsList]
    Range: type[Range]

try:  # pragma: no cover - optional dependency
    from qdrant_client import QdrantClient
    from qdrant_client import models as qdrant_models
except ImportError:  # pragma: no cover - optional dependency
    QdrantClient = None
    qdrant_models = None

__all__ = ["QdrantVectorStore"]


class QdrantVectorStore(VectorStoreProtocol):
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
            client or client_class(url=config.uri, prefer_grpc=True),
        )
        self._distance: Distance = _distance_for(config.distance_metric)

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]:
        if not records:
            return []

        self._validate_batch_dimensions(records)
        collection_name = self._collection_name(knowledge_base_id)
        self._ensure_collection(collection_name)

        try:
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

        return [self._match_from_scored_point(point) for point in response.points]

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
                points_selector=_require_qdrant_models().PointIdsList(points=list(record_ids)),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Failed to delete Qdrant vector records.") from exc

        return len(record_ids)

    def _validate_batch_dimensions(self, records: list[VectorRecord]) -> None:
        for record in records:
            if len(record.embedding) != self._config.dimensions:
                raise VectorDimensionMismatchError(
                    "Embedding dimension does not match the configured Qdrant collection dimension."
                )

    def _validate_query_dimension(self, query_vector: list[float]) -> None:
        if len(query_vector) != self._config.dimensions:
            raise VectorDimensionMismatchError(
                "Query vector dimension does not match the configured Qdrant collection dimension."
            )

    def _ensure_collection(self, collection_name: str) -> None:
        if self._client.collection_exists(collection_name):
            return

        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=_require_qdrant_models().VectorParams(
                size=self._config.dimensions,
                distance=self._distance,
            ),
        )

    def _point_for(self, record: VectorRecord) -> PointStruct:
        return _require_qdrant_models().PointStruct(
            id=record.id,
            vector=list(record.embedding),
            payload={
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
            record_id=str(point.id),
            content_id=cast(str, payload["content_id"]),
            score=float(point.score),
            content=cast(str | None, payload.get("content")),
            metadata=cast(dict[str, MetadataValue], raw_metadata),
        )

    @staticmethod
    def _collection_name(knowledge_base_id: str) -> str:
        return f"chili_{knowledge_base_id}"


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