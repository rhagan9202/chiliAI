# Vectorstore 1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `backend/vectorstore` as a production-ready, synchronous vector storage module with Qdrant isolated behind an adapter.

**Architecture:** Complete the backend-neutral service and adapter contracts, then make in-memory and Qdrant implement the same behavior. `VectorService` remains backend-agnostic; Qdrant SDK imports stay in `vectorstore/adapters/qdrant_adapter.py`, dependency factories, and Qdrant-specific tests only.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, pytest-cov, pyright strict, ruff, qdrant-client, existing event bus and object store protocols.

---

## Files And Responsibilities

- Modify `backend/vectorstore/service_models.py`: add delete and audit DTOs, keep service request/response validation.
- Modify `backend/vectorstore/models.py`: keep adapter-neutral persisted record and match models; no Qdrant imports.
- Modify `backend/vectorstore/adapters/protocols.py`: expand backend-neutral storage protocol.
- Modify `backend/vectorstore/protocols.py`: expand public service protocol.
- Modify `backend/vectorstore/adapters/in_memory.py`: implement full protocol parity for dev/tests.
- Modify `backend/vectorstore/adapters/qdrant_adapter.py`: implement full protocol against Qdrant while hiding Qdrant APIs.
- Modify `backend/vectorstore/service.py`: implement service workflows, chunking, audit persistence, deletion, batch search, and error normalization.
- Modify `backend/api/dependencies.py`: pass object storage into the assembled vectorstore service.
- Modify `backend/vectorstore/__init__.py`: export new service DTOs.
- Modify `backend/events/types.py`: add `VectorsDeletedEvent`.
- Modify `backend/events/codec.py`: register `vectors.deleted`.
- Modify `backend/tests/events/test_codec.py`: cover event codec.
- Modify `backend/tests/vectorstore/test_models.py`: cover new DTOs.
- Modify `backend/tests/vectorstore/test_in_memory_adapter.py`: cover full adapter protocol.
- Modify `backend/tests/vectorstore/test_service.py`: cover full service behavior through protocols/fakes.
- Modify `backend/tests/vectorstore/test_qdrant_adapter.py`: cover fake-client and live Qdrant behavior.
- Create `backend/tests/vectorstore/test_architecture.py`: enforce Qdrant import boundary.
- Modify `backend/pyproject.toml`: include `vectorstore` and `tests/vectorstore` in pyright strict checking.
- Create `backend/vectorstore/README.md`: document the 1.0 contract, config, lifecycle, tests, and non-goals.

## Verification Commands

Run these from `/home/rdhagan92/chiliAI` unless a command says otherwise.

- Unit/vectorstore tests: `uv run --project backend pytest backend/tests/vectorstore backend/tests/events/test_codec.py -v`
- Coverage gate: `uv run --project backend pytest --cov=vectorstore --cov-report=term-missing backend/tests/vectorstore`
- Live Qdrant release gate: `QDRANT_URL=http://localhost:6333 uv run --project backend pytest backend/tests/vectorstore/test_qdrant_adapter.py -m integration -v`
- Lint: `uv run --project backend ruff check backend/vectorstore backend/tests/vectorstore backend/events/types.py backend/events/codec.py backend/tests/events/test_codec.py`
- Type check: `uv run --project backend pyright`

---

### Task 1: Events, Models, And Protocol Contracts

**Files:**
- Modify: `backend/events/types.py`
- Modify: `backend/events/codec.py`
- Modify: `backend/tests/events/test_codec.py`
- Modify: `backend/vectorstore/service_models.py`
- Modify: `backend/vectorstore/adapters/protocols.py`
- Modify: `backend/vectorstore/protocols.py`
- Modify: `backend/vectorstore/__init__.py`
- Test: `backend/tests/vectorstore/test_models.py`

- [ ] **Step 1: Write failing service-model tests**

Add these tests to `backend/tests/vectorstore/test_models.py`:

```python
from vectorstore.service_models import (
    VectorAuditArtifact,
    VectorDeleteResponse,
    VectorIndexReceipt,
)


def test_vector_delete_response_records_deleted_count() -> None:
    response = VectorDeleteResponse(knowledge_base_id="kb-1", deleted_count=3)

    assert response.knowledge_base_id == "kb-1"
    assert response.deleted_count == 3


def test_vector_delete_response_rejects_negative_count() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        VectorDeleteResponse(knowledge_base_id="kb-1", deleted_count=-1)


def test_vector_audit_artifact_summarizes_receipts() -> None:
    receipt = VectorIndexReceipt(
        knowledge_base_id="kb-1",
        record_id="record-1",
        content_id="content-1",
        dimension=2,
    )

    artifact = VectorAuditArtifact(
        request_id="request-1",
        knowledge_base_id="kb-1",
        receipts=[receipt],
    )

    assert artifact.receipt_count == 1
    assert artifact.receipts == [receipt]
    assert '"receipt_count":1' in artifact.model_dump_json()
```

- [ ] **Step 2: Write failing event codec test**

In `backend/tests/events/test_codec.py`, add `VectorsDeletedEvent` to the import list from `events.types`, then add:

```python
def test_event_codec_round_trips_vectors_deleted_event() -> None:
    event = VectorsDeletedEvent(knowledge_base_id="kb-1", deleted_count=2)

    encoded = encode_event(event)
    decoded = decode_event(encoded)

    assert decoded == event
    assert decoded.event_type == "vectors.deleted"
```

- [ ] **Step 3: Run tests to verify contract failures**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_models.py backend/tests/events/test_codec.py -q
```

Expected: FAIL because `VectorDeleteResponse`, `VectorAuditArtifact`, and `VectorsDeletedEvent` do not exist.

- [ ] **Step 4: Add service DTOs**

In `backend/vectorstore/service_models.py`, add this helper and classes after `VectorIndexReceipt`:

```python
def _empty_receipts() -> list[VectorIndexReceipt]:
    return []


class VectorAuditArtifact(BaseModel):
    """Audit artifact persisted after successful vector indexing."""

    request_id: str
    knowledge_base_id: str
    receipts: list[VectorIndexReceipt] = Field(default_factory=_empty_receipts)
    created_at: datetime = Field(default_factory=utc_now)

    @computed_field
    @property
    def receipt_count(self) -> int:
        return len(self.receipts)


class VectorDeleteResponse(BaseModel):
    """Response returned after deleting a vector namespace."""

    knowledge_base_id: str
    deleted_count: int = Field(ge=0)
    deleted_at: datetime = Field(default_factory=utc_now)
```

Also add `computed_field` to the existing Pydantic import at the top of the file:

```python
from pydantic import BaseModel, Field, computed_field, model_validator
```

Update `__all__` in the same file:

```python
__all__ = [
    "VectorAuditArtifact",
    "VectorDeleteResponse",
    "VectorIndexReceipt",
    "VectorIndexRequest",
    "VectorIndexSubmission",
    "VectorSearchMatch",
    "VectorSearchRequest",
    "VectorSearchResponse",
]
```

- [ ] **Step 5: Add deleted event**

In `backend/events/types.py`, add after `VectorsIndexedEvent`:

```python
class VectorsDeletedEvent(EventBase):
    event_type: Literal["vectors.deleted"] = "vectors.deleted"
    knowledge_base_id: str
    deleted_count: int = Field(ge=0)
```

Add `VectorsDeletedEvent` to the `AnyEvent` union immediately after `VectorsIndexedEvent`.

Add `"VectorsDeletedEvent"` to `__all__` near `VectorsIndexedEvent`.

- [ ] **Step 6: Register deleted event codec**

In `backend/events/codec.py`, add `VectorsDeletedEvent` to the import block and add this registry entry immediately after `"vectors.indexed"`:

```python
"vectors.deleted": VectorsDeletedEvent,
```

- [ ] **Step 7: Expand vectorstore adapter protocol**

Replace `backend/vectorstore/adapters/protocols.py` with:

```python
"""Adapter-level protocols for vectorstore backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vectorstore.models import MetadataValue, VectorMatch, VectorRecord


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Persist embedding records and execute similarity search."""

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]: ...

    def search(
        self,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, MetadataValue] | None = None,
    ) -> list[VectorMatch]: ...

    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None: ...

    def count_records(self, knowledge_base_id: str) -> int: ...

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool: ...

    def delete_namespace(self, knowledge_base_id: str) -> int: ...


__all__ = [
    "VectorStoreProtocol",
]
```

- [ ] **Step 8: Expand vectorstore service protocol**

Replace `backend/vectorstore/protocols.py` with:

```python
"""Service-level protocols for the vectorstore module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vectorstore.models import VectorRecord
from vectorstore.service_models import (
    VectorDeleteResponse,
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorSearchRequest,
    VectorSearchResponse,
)


@runtime_checkable
class VectorServiceProtocol(Protocol):
    """Service boundary for vector indexing, search, and lifecycle operations."""

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]: ...

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse: ...

    def batch_search(
        self, requests: list[VectorSearchRequest]
    ) -> list[VectorSearchResponse]: ...

    def get_record(
        self, knowledge_base_id: str, record_id: str
    ) -> VectorRecord | None: ...

    def count(self, knowledge_base_id: str) -> int: ...

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool: ...

    def delete_knowledge_base(self, knowledge_base_id: str) -> VectorDeleteResponse: ...


__all__ = [
    "VectorServiceProtocol",
]
```

- [ ] **Step 9: Export new DTOs**

In `backend/vectorstore/__init__.py`, add `VectorAuditArtifact` and `VectorDeleteResponse` to the `from vectorstore.service_models import (...)` block and to `__all__`.

- [ ] **Step 10: Run focused tests**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_models.py backend/tests/events/test_codec.py -q
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add backend/events/types.py backend/events/codec.py backend/tests/events/test_codec.py backend/vectorstore/service_models.py backend/vectorstore/adapters/protocols.py backend/vectorstore/protocols.py backend/vectorstore/__init__.py backend/tests/vectorstore/test_models.py
git commit -m "feat(vectorstore): define 1.0 contracts"
```

---

### Task 2: In-Memory Adapter Protocol Parity

**Files:**
- Modify: `backend/vectorstore/adapters/in_memory.py`
- Test: `backend/tests/vectorstore/test_in_memory_adapter.py`

- [ ] **Step 1: Write failing in-memory adapter tests**

Add to `backend/tests/vectorstore/test_in_memory_adapter.py`:

```python
def test_in_memory_vector_store_gets_and_counts_records() -> None:
    store = InMemoryVectorStore()
    record = VectorRecord(
        id="record-1",
        knowledge_base_id="kb-1",
        content_id="content-1",
        embedding=[1.0, 0.0],
        content="Alpha",
        metadata={"source": "policy"},
    )
    store.upsert_records("kb-1", [record])

    assert store.get_record("kb-1", "record-1") == record
    assert store.get_record("kb-1", "missing") is None
    assert store.count_records("kb-1") == 1
    assert store.count_records("missing-kb") == 0


def test_in_memory_vector_store_deletes_record_idempotently() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
            )
        ],
    )

    assert store.delete_record("kb-1", "record-1") is True
    assert store.delete_record("kb-1", "record-1") is False
    assert store.get_record("kb-1", "record-1") is None
    assert store.count_records("kb-1") == 0


def test_in_memory_vector_store_delete_namespace_returns_count() -> None:
    store = InMemoryVectorStore()
    store.upsert_records(
        "kb-1",
        [
            VectorRecord(
                id="record-1",
                knowledge_base_id="kb-1",
                content_id="content-1",
                embedding=[1.0, 0.0],
            ),
            VectorRecord(
                id="record-2",
                knowledge_base_id="kb-1",
                content_id="content-2",
                embedding=[0.0, 1.0],
            ),
        ],
    )
    store.upsert_records(
        "kb-2",
        [
            VectorRecord(
                id="record-3",
                knowledge_base_id="kb-2",
                content_id="content-3",
                embedding=[1.0, 1.0],
            )
        ],
    )

    assert store.delete_namespace("kb-1") == 2
    assert store.delete_namespace("kb-1") == 0
    assert store.count_records("kb-1") == 0
    assert store.count_records("kb-2") == 1
```

- [ ] **Step 2: Run tests to verify failures**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_in_memory_adapter.py -q
```

Expected: FAIL because `get_record`, `count_records`, `delete_record`, and `delete_namespace` are missing.

- [ ] **Step 3: Implement in-memory lifecycle methods**

Add these methods to `InMemoryVectorStore` after `search()`:

```python
    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None:
        return self._records.get(knowledge_base_id, {}).get(record_id)

    def count_records(self, knowledge_base_id: str) -> int:
        return len(self._records.get(knowledge_base_id, {}))

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        bucket = self._records.get(knowledge_base_id)
        if bucket is None or record_id not in bucket:
            return False
        del bucket[record_id]
        if not bucket:
            self._records.pop(knowledge_base_id, None)
            self._dimensions.pop(knowledge_base_id, None)
        return True

    def delete_namespace(self, knowledge_base_id: str) -> int:
        deleted_count = len(self._records.get(knowledge_base_id, {}))
        self._records.pop(knowledge_base_id, None)
        self._dimensions.pop(knowledge_base_id, None)
        return deleted_count
```

- [ ] **Step 4: Run adapter tests**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_in_memory_adapter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/vectorstore/adapters/in_memory.py backend/tests/vectorstore/test_in_memory_adapter.py
git commit -m "feat(vectorstore): complete in-memory adapter contract"
```

---

### Task 3: VectorService Workflows

**Files:**
- Modify: `backend/vectorstore/service.py`
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/vectorstore/test_service.py`

- [ ] **Step 1: Add service fake helpers**

In `backend/tests/vectorstore/test_service.py`, add imports:

```python
from storage.adapters.in_memory import InMemoryObjectStore
from storage.models import StoredObjectWriteResult
from vectorstore.service_models import VectorAuditArtifact, VectorDeleteResponse
```

Extend the existing `_DroppingVectorStore` fake with the lifecycle methods required by the expanded protocol:

```python
    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None:
        del knowledge_base_id, record_id
        return None

    def count_records(self, knowledge_base_id: str) -> int:
        del knowledge_base_id
        return 0

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        del knowledge_base_id, record_id
        return False

    def delete_namespace(self, knowledge_base_id: str) -> int:
        del knowledge_base_id
        return 0
```

Add these helper classes after `_DroppingVectorStore`:

```python
class _RecordingVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.upsert_batch_sizes: list[int] = []

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]:
        self.upsert_batch_sizes.append(len(records))
        return super().upsert_records(knowledge_base_id, records)


class _FailingObjectStore(InMemoryObjectStore):
    def put_bytes(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredObjectWriteResult:
        del key, content, media_type, metadata
        raise RuntimeError("object store unavailable")
```

- [ ] **Step 2: Write failing service workflow tests**

Add these tests to `backend/tests/vectorstore/test_service.py`:

```python
def test_vector_service_splits_large_index_batches_and_preserves_order() -> None:
    event_bus = InMemoryEventBus()
    store = _RecordingVectorStore()
    service = create_vector_service(store, event_bus=event_bus, max_batch_size=2)

    receipts = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0]),
                VectorIndexSubmission(content_id="content-2", embedding=[0.0, 1.0]),
                VectorIndexSubmission(content_id="content-3", embedding=[1.0, 1.0]),
            ],
        )
    )

    assert store.upsert_batch_sizes == [2, 1]
    assert [receipt.content_id for receipt in receipts] == [
        "content-1",
        "content-2",
        "content-3",
    ]


def test_vector_service_persists_audit_artifact() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = create_vector_service(
        InMemoryVectorStore(),
        event_bus=event_bus,
        object_store=object_store,
    )

    receipts = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0])
            ],
        )
    )

    keys = object_store.list_keys("knowledgebases/kb-1/vector_index/")
    assert len(keys) == 1
    stored = object_store.get_bytes(keys[0])
    artifact = VectorAuditArtifact.model_validate_json(stored.content)
    assert artifact.knowledge_base_id == "kb-1"
    assert artifact.receipts == receipts
    assert stored.media_type == "application/json"


def test_vector_service_logs_audit_failure_without_rollback(caplog: pytest.LogCaptureFixture) -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(
        InMemoryVectorStore(),
        event_bus=event_bus,
        object_store=_FailingObjectStore(),
    )

    receipts = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0])
            ],
        )
    )

    assert len(receipts) == 1
    assert "Failed to persist vector index audit artifact" in caplog.text


def test_vector_service_batch_search_preserves_request_order() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)
    service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="alpha", embedding=[1.0, 0.0]),
                VectorIndexSubmission(content_id="beta", embedding=[0.0, 1.0]),
            ],
        )
    )

    responses = service.batch_search(
        [
            VectorSearchRequest(knowledge_base_id="kb-1", query_vector=[0.0, 1.0], limit=1),
            VectorSearchRequest(knowledge_base_id="kb-1", query_vector=[1.0, 0.0], limit=1),
        ]
    )

    assert [response.matches[0].content_id for response in responses] == ["beta", "alpha"]


def test_vector_service_get_count_and_delete_record() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)
    receipt = service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0])
            ],
        )
    )[0]

    record = service.get_record("kb-1", receipt.record_id)
    assert record is not None
    assert record.content_id == "content-1"
    assert service.count("kb-1") == 1
    assert service.delete_record("kb-1", receipt.record_id) is True
    assert service.delete_record("kb-1", receipt.record_id) is False
    assert service.count("kb-1") == 0


def test_vector_service_delete_knowledge_base_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_vector_service(InMemoryVectorStore(), event_bus=event_bus)
    service.index(
        VectorIndexRequest(
            knowledge_base_id="kb-1",
            submissions=[
                VectorIndexSubmission(content_id="content-1", embedding=[1.0, 0.0]),
                VectorIndexSubmission(content_id="content-2", embedding=[0.0, 1.0]),
            ],
        )
    )

    response = service.delete_knowledge_base("kb-1")

    assert isinstance(response, VectorDeleteResponse)
    assert response.deleted_count == 2
    assert service.count("kb-1") == 0
    assert event_bus.published_events[-1].event_type == "vectors.deleted"
```

- [ ] **Step 3: Run service tests to verify failures**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_service.py -q
```

Expected: FAIL because `create_vector_service()` does not accept `max_batch_size` or `object_store`, and the new service methods do not exist.

- [ ] **Step 4: Implement service workflows**

Replace `backend/vectorstore/service.py` with:

```python
"""Service entry point for vectorstore indexing and search flows."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterator
from typing import TypeVar

from events.protocols import EventBus
from events.types import VectorIndexedReference, VectorsDeletedEvent, VectorsIndexedEvent
from shared.protocols import ObjectStoreProtocol
from shared.utils import generate_id
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.exceptions import VectorDimensionMismatchError, VectorStoreError
from vectorstore.models import VectorRecord
from vectorstore.service_models import (
    VectorAuditArtifact,
    VectorDeleteResponse,
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorIndexSubmission,
    VectorSearchMatch,
    VectorSearchRequest,
    VectorSearchResponse,
)

logger = logging.getLogger(__name__)
ItemT = TypeVar("ItemT")


class VectorService:
    """Coordinate vector indexing, search, and lifecycle through injected ports."""

    def __init__(
        self,
        store: VectorStoreProtocol,
        *,
        event_bus: EventBus,
        object_store: ObjectStoreProtocol | None = None,
        max_batch_size: int = 500,
    ) -> None:
        if max_batch_size <= 0:
            raise ValueError("VectorService max_batch_size must be greater than 0.")
        self._store = store
        self._event_bus = event_bus
        self._object_store = object_store
        self._max_batch_size = max_batch_size

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]:
        request_id = generate_id()
        records = [
            self._record_for_submission(request.knowledge_base_id, submission)
            for submission in request.submissions
        ]

        stored_records: list[VectorRecord] = []
        try:
            for batch in _chunk_items(records, self._max_batch_size):
                stored_records.extend(
                    self._store.upsert_records(request.knowledge_base_id, batch)
                )
        except ValueError as exc:
            raise VectorDimensionMismatchError(str(exc)) from exc
        except Exception as exc:
            raise VectorStoreError("Failed to index vector records.") from exc

        self._verify_stored_records(records, stored_records)
        receipts = [self._receipt_for(record) for record in stored_records]
        self._publish_indexed_event(receipts)
        self._persist_audit_artifact(request_id, request.knowledge_base_id, receipts)
        return receipts

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse:
        try:
            matches = self._store.search(
                request.knowledge_base_id,
                request.query_vector,
                request.limit,
                request.filters,
            )
        except ValueError as exc:
            raise VectorDimensionMismatchError(str(exc)) from exc
        except Exception as exc:
            raise VectorStoreError("Failed to search vector records.") from exc

        return VectorSearchResponse(
            knowledge_base_id=request.knowledge_base_id,
            query_dimension=len(request.query_vector),
            matches=[
                VectorSearchMatch(
                    record_id=match.record_id,
                    content_id=match.content_id,
                    score=match.score,
                    content=match.content,
                    metadata=dict(match.metadata),
                )
                for match in matches
            ],
        )

    def batch_search(
        self, requests: list[VectorSearchRequest]
    ) -> list[VectorSearchResponse]:
        return [self.search(request) for request in requests]

    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None:
        try:
            return self._store.get_record(knowledge_base_id, record_id)
        except Exception as exc:
            raise VectorStoreError("Failed to get vector record.") from exc

    def count(self, knowledge_base_id: str) -> int:
        try:
            return self._store.count_records(knowledge_base_id)
        except Exception as exc:
            raise VectorStoreError("Failed to count vector records.") from exc

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        try:
            return self._store.delete_record(knowledge_base_id, record_id)
        except Exception as exc:
            raise VectorStoreError("Failed to delete vector record.") from exc

    def delete_knowledge_base(self, knowledge_base_id: str) -> VectorDeleteResponse:
        try:
            deleted_count = self._store.delete_namespace(knowledge_base_id)
        except Exception as exc:
            raise VectorStoreError("Failed to delete vector namespace.") from exc

        response = VectorDeleteResponse(
            knowledge_base_id=knowledge_base_id,
            deleted_count=deleted_count,
        )
        self._event_bus.publish(
            VectorsDeletedEvent(
                knowledge_base_id=knowledge_base_id,
                deleted_count=deleted_count,
            )
        )
        return response

    @staticmethod
    def _record_for_submission(
        knowledge_base_id: str,
        submission: VectorIndexSubmission,
    ) -> VectorRecord:
        return VectorRecord(
            id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            content_id=submission.content_id,
            embedding=list(submission.embedding),
            content=submission.content,
            metadata=dict(submission.metadata),
        )

    @staticmethod
    def _receipt_for(record: VectorRecord) -> VectorIndexReceipt:
        return VectorIndexReceipt(
            knowledge_base_id=record.knowledge_base_id,
            record_id=record.id,
            content_id=record.content_id,
            dimension=len(record.embedding),
        )

    @staticmethod
    def _verify_stored_records(
        expected: list[VectorRecord],
        actual: list[VectorRecord],
    ) -> None:
        expected_records = Counter(
            (record.id, record.content_id, record.knowledge_base_id)
            for record in expected
        )
        actual_records = Counter(
            (record.id, record.content_id, record.knowledge_base_id)
            for record in actual
        )
        if actual_records == expected_records:
            return

        missing = sorted(
            content_id
            for (_record_id, content_id, _knowledge_base_id), count in (
                expected_records - actual_records
            ).items()
            for _ in range(count)
        )
        unexpected = sorted(
            content_id
            for (_record_id, content_id, _knowledge_base_id), count in (
                actual_records - expected_records
            ).items()
            for _ in range(count)
        )
        details: list[str] = []
        if missing:
            details.append(f"missing records for: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected records for: {', '.join(unexpected)}")
        raise VectorStoreError(
            "Vector store returned incomplete batch results: " + "; ".join(details)
        )

    def _publish_indexed_event(self, receipts: list[VectorIndexReceipt]) -> None:
        self._event_bus.publish(
            VectorsIndexedEvent(
                records=[
                    VectorIndexedReference(
                        knowledge_base_id=receipt.knowledge_base_id,
                        record_id=receipt.record_id,
                        content_id=receipt.content_id,
                        dimension=receipt.dimension,
                    )
                    for receipt in receipts
                ]
            )
        )

    def _persist_audit_artifact(
        self,
        request_id: str,
        knowledge_base_id: str,
        receipts: list[VectorIndexReceipt],
    ) -> None:
        if self._object_store is None:
            return

        artifact = VectorAuditArtifact(
            request_id=request_id,
            knowledge_base_id=knowledge_base_id,
            receipts=receipts,
        )
        key = f"knowledgebases/{knowledge_base_id}/vector_index/{request_id}.json"
        try:
            self._object_store.put_bytes(
                key,
                artifact.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": knowledge_base_id,
                    "request_id": request_id,
                    "receipt_count": artifact.receipt_count,
                },
            )
        except Exception:
            logger.warning(
                "Failed to persist vector index audit artifact: key=%s",
                key,
                exc_info=True,
            )


def _chunk_items(items: list[ItemT], size: int) -> Iterator[list[ItemT]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def create_vector_service(
    store: VectorStoreProtocol,
    *,
    event_bus: EventBus,
    object_store: ObjectStoreProtocol | None = None,
    max_batch_size: int = 500,
) -> VectorService:
    """Create the default vector service."""

    return VectorService(
        store,
        event_bus=event_bus,
        object_store=object_store,
        max_batch_size=max_batch_size,
    )


__all__ = ["VectorService", "create_vector_service"]
```

- [ ] **Step 5: Wire object-store audit persistence into API factory**

In `backend/api/dependencies.py`, replace `get_vectorstore_service()` with:

```python
@lru_cache(maxsize=1)
def get_vectorstore_service() -> VectorServiceProtocol:
    """Return the vectorstore service assembled from configured dependencies."""
    return create_vector_service(
        get_vector_store(),
        event_bus=get_event_bus(),
        object_store=get_object_store(),
    )
```

- [ ] **Step 6: Run service tests**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Run dependency factory tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_dependencies.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/vectorstore/service.py backend/api/dependencies.py backend/tests/vectorstore/test_service.py
git commit -m "feat(vectorstore): add service lifecycle workflows"
```

---

### Task 4: Qdrant Adapter Full Contract

**Files:**
- Modify: `backend/vectorstore/adapters/qdrant_adapter.py`
- Test: `backend/tests/vectorstore/test_qdrant_adapter.py`

- [ ] **Step 1: Extend fake Qdrant client**

In `backend/tests/vectorstore/test_qdrant_adapter.py`, add this helper above `_FakeQdrantClient`:

```python
class _FakeCountResponse:
    def __init__(self, count: int) -> None:
        self.count = count
```

Extend `_FakeQdrantClient` with these fields in `__init__`:

```python
self.retrieved_ids: list[tuple[str, list[str]]] = []
self.counted_collections: list[str] = []
self.deleted_collections: list[str] = []
self.retrieve_response: list[qdrant_models.Record] = []
self.count_response = _FakeCountResponse(count=0)
```

Add these methods to `_FakeQdrantClient`:

```python
def retrieve(
    self,
    collection_name: str,
    ids: Sequence[str],
    with_payload: bool,
    with_vectors: bool,
    **_: object,
) -> list[qdrant_models.Record]:
    del with_payload, with_vectors
    self.retrieved_ids.append((collection_name, list(ids)))
    return self.retrieve_response


def count(
    self,
    collection_name: str,
    exact: bool,
    **_: object,
) -> _FakeCountResponse:
    del exact
    self.counted_collections.append(collection_name)
    return self.count_response


def delete_collection(self, collection_name: str, **_: object) -> bool:
    self.deleted_collections.append(collection_name)
    self.existing_collections.discard(collection_name)
    return True
```

- [ ] **Step 2: Write failing Qdrant fake-client tests**

Add tests to `backend/tests/vectorstore/test_qdrant_adapter.py`:

```python
def test_qdrant_vector_store_get_record_reconstructs_payload_and_vector() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.retrieve_response = [
        qdrant_models.Record(
            id="11111111-1111-1111-1111-111111111111",
            payload={
                "record_id": "kb-1:content-1",
                "knowledge_base_id": "kb-1",
                "content_id": "content-1",
                "content": "Alpha",
                "metadata": {"source": "policy"},
            },
            vector=[1.0, 0.0],
            shard_key=None,
        )
    ]
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    record = store.get_record("kb-1", "kb-1:content-1")

    assert record is not None
    assert record.id == "kb-1:content-1"
    assert record.embedding == [1.0, 0.0]
    assert record.metadata == {"source": "policy"}
    assert client.retrieved_ids[0][0] == "chili_kb-1"


def test_qdrant_vector_store_get_record_returns_none_for_missing_collection() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.get_record("kb-1", "record-1") is None
    assert client.retrieved_ids == []


def test_qdrant_vector_store_counts_records() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.count_response = _FakeCountResponse(count=4)
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.count_records("kb-1") == 4
    assert store.count_records("missing-kb") == 0


def test_qdrant_vector_store_delete_record_is_idempotent() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.retrieve_response = [
        qdrant_models.Record(
            id="11111111-1111-1111-1111-111111111111",
            payload={"record_id": "record-1", "content_id": "content-1"},
            vector=[1.0, 0.0],
            shard_key=None,
        )
    ]
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.delete_record("kb-1", "record-1") is True
    client.retrieve_response = []
    assert store.delete_record("kb-1", "record-1") is False


def test_qdrant_vector_store_delete_namespace_counts_then_deletes_collection() -> None:
    client = _FakeQdrantClient()
    client.existing_collections.add("chili_kb-1")
    client.count_response = _FakeCountResponse(count=3)
    store = QdrantVectorStore(
        VectorStoreConfig(backend="qdrant", uri="http://qdrant:6333", dimensions=2),
        client=cast(QdrantClientProtocol, client),
    )

    assert store.delete_namespace("kb-1") == 3
    assert client.deleted_collections == ["chili_kb-1"]
    assert store.delete_namespace("kb-1") == 0
```

- [ ] **Step 3: Run Qdrant tests to verify failures**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_qdrant_adapter.py -q
```

Expected: FAIL because Qdrant protocol methods and adapter methods are missing.

- [ ] **Step 4: Extend Qdrant client protocol**

In `backend/vectorstore/adapters/qdrant_adapter.py`, add these imports under `TYPE_CHECKING`:

```python
        CountResult,
        Record,
```

Add these methods to `QdrantClientProtocol`:

```python
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
        **kwargs: object,
    ) -> CountResult: ...

    def delete_collection(self, collection_name: str, **kwargs: object) -> bool: ...
```

- [ ] **Step 5: Implement Qdrant lifecycle methods**

Add these methods to `QdrantVectorStore` after `search()`:

```python
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
        except Exception as exc:
            raise VectorStoreError("Failed to retrieve Qdrant vector record.") from exc

        if not records:
            return None
        return self._record_from_qdrant_record(records[0], knowledge_base_id)

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
            self._client.delete_collection(collection_name=collection_name)
        except Exception as exc:
            raise VectorStoreError("Failed to delete Qdrant vector namespace.") from exc
        return deleted_count
```

Add this helper method near `_match_from_scored_point()`:

```python
    def _record_from_qdrant_record(
        self,
        record: Record,
        knowledge_base_id: str,
    ) -> VectorRecord:
        payload = cast(dict[str, object], record.payload or {})
        raw_vector = record.vector
        if not isinstance(raw_vector, list):
            raise VectorStoreError("Qdrant record did not include a dense vector.")
        return VectorRecord(
            id=cast(str, payload.get("record_id", str(record.id))),
            knowledge_base_id=cast(
                str,
                payload.get("knowledge_base_id", knowledge_base_id),
            ),
            content_id=cast(str, payload["content_id"]),
            embedding=[float(value) for value in raw_vector],
            content=cast(str | None, payload.get("content")),
            metadata=cast(dict[str, MetadataValue], payload.get("metadata", {})),
        )
```

- [ ] **Step 6: Update delete_records to use delete_record naming parity**

Keep existing `delete_records()` as an adapter-private compatibility helper for the current integration test cleanup, but route public single-record deletion through `delete_record()`. Do not add `delete_records()` to `VectorStoreProtocol`.

- [ ] **Step 7: Run Qdrant fake-client tests**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_qdrant_adapter.py -q -m "not integration"
```

Expected: PASS.

- [ ] **Step 8: Extend live Qdrant integration test**

In `test_qdrant_vector_store_round_trip_search`, after the existing search assertions add:

```python
        fetched = store.get_record(knowledge_base_id, record.id)
        assert fetched is not None
        assert fetched.id == record.id
        assert fetched.embedding == [1.0, 0.0]
        assert store.count_records(knowledge_base_id) == 1
        assert store.delete_record(knowledge_base_id, record.id) is True
        assert store.delete_record(knowledge_base_id, record.id) is False
        assert store.count_records(knowledge_base_id) == 0
```

Add a second live test:

```python
@pytest.mark.integration
def test_qdrant_vector_store_live_delete_namespace() -> None:
    uri = os.getenv("QDRANT_URL")
    if uri is None:
        pytest.skip("QDRANT_URL is required for Qdrant integration tests.")

    knowledge_base_id = f"kb-qdrant-delete-{uuid4()}"
    store = QdrantVectorStore(
        VectorStoreConfig(
            backend="qdrant",
            uri=uri,
            dimensions=2,
            distance_metric="cosine",
        )
    )
    records = [
        VectorRecord(
            id=str(uuid4()),
            knowledge_base_id=knowledge_base_id,
            content_id="content-1",
            embedding=[1.0, 0.0],
        ),
        VectorRecord(
            id=str(uuid4()),
            knowledge_base_id=knowledge_base_id,
            content_id="content-2",
            embedding=[0.0, 1.0],
        ),
    ]

    store.upsert_records(knowledge_base_id, records)

    assert store.delete_namespace(knowledge_base_id) == 2
    assert store.delete_namespace(knowledge_base_id) == 0
```

- [ ] **Step 9: Run live Qdrant release gate**

Start Qdrant with the repo's existing service profile, then run:

```bash
QDRANT_URL=http://localhost:6333 uv run --project backend pytest backend/tests/vectorstore/test_qdrant_adapter.py -m integration -v
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/vectorstore/adapters/qdrant_adapter.py backend/tests/vectorstore/test_qdrant_adapter.py
git commit -m "feat(vectorstore): complete qdrant adapter contract"
```

---

### Task 5: Architecture Guards, Strict Typing, And Documentation

**Files:**
- Create: `backend/tests/vectorstore/test_architecture.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/vectorstore/README.md`

- [ ] **Step 1: Write architecture guard test**

Create `backend/tests/vectorstore/test_architecture.py`:

```python
"""Architecture guardrails for vectorstore 1.0."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT
APPROVED_QDRANT_IMPORT_FILES = {
    BACKEND_ROOT / "vectorstore" / "adapters" / "qdrant_adapter.py",
    BACKEND_ROOT / "api" / "dependencies.py",
    BACKEND_ROOT / "agent" / "coordinator.py",
    BACKEND_ROOT / "tests" / "vectorstore" / "test_qdrant_adapter.py",
}


def test_qdrant_sdk_imports_stay_behind_adapter_boundary() -> None:
    offenders: list[str] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts or path in APPROVED_QDRANT_IMPORT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "qdrant_client" or name.startswith("qdrant_client.") for name in names):
                offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == []
```

- [ ] **Step 2: Run architecture test**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore/test_architecture.py -q
```

Expected: PASS. If it fails, remove Qdrant SDK imports from the reported files unless the design spec explicitly allows that file.

- [ ] **Step 3: Add vectorstore to strict pyright include**

In `backend/pyproject.toml`, add these entries to `[tool.pyright].include` near the existing module/test entries:

```toml
    "vectorstore",
    "tests/vectorstore",
```

- [ ] **Step 4: Write vectorstore README**

Create `backend/vectorstore/README.md`:

```markdown
# Vectorstore

`vectorstore` owns embedding storage and similarity search for chiliAI.

## Boundaries

Application code depends on `VectorServiceProtocol` from `vectorstore.protocols`.
`VectorService` depends on `VectorStoreProtocol` from `vectorstore.adapters.protocols`.
Qdrant is available only through `vectorstore.adapters.qdrant_adapter.QdrantVectorStore`.
Do not import `qdrant_client` outside the Qdrant adapter, dependency factories, or Qdrant-specific tests.

## Service Contract

The 1.0 service contract is synchronous:

- `index(request)`
- `search(request)`
- `batch_search(requests)`
- `get_record(knowledge_base_id, record_id)`
- `count(knowledge_base_id)`
- `delete_record(knowledge_base_id, record_id)`
- `delete_knowledge_base(knowledge_base_id)`

`delete_record` is idempotent and returns `False` for missing records.
`delete_knowledge_base` is idempotent and returns a `VectorDeleteResponse` with the deleted count.

## Qdrant Configuration

Use `VectorStoreConfig`:

```yaml
vectorstore:
  backend: qdrant
  uri: http://localhost:6333
  dimensions: 384
  distance_metric: cosine
```

`dimensions` must match the configured embeddings provider dimensions.

## Metadata Filters

Metadata values are scalar: `str | int | float | bool`.
Filters are exact-match filters. Qdrant float equality is implemented with an equal `gte/lte` range inside the adapter.

## Audit Artifacts

When `VectorService` receives an object store, successful index calls persist:

`knowledgebases/{knowledge_base_id}/vector_index/{request_id}.json`

The artifact contains request ID, knowledge base ID, receipts, receipt count, and creation time.
Audit write failures are logged and do not roll back vector writes.

## Live Qdrant Tests

Vectorstore 1.0 requires live Qdrant integration tests:

```bash
QDRANT_URL=http://localhost:6333 uv run --project backend pytest backend/tests/vectorstore/test_qdrant_adapter.py -m integration -v
```

## Non-Goals

1.0 does not include async contracts, pgvector, Weaviate, hybrid search, advanced metadata filters, public API endpoint expansion, RAG behavior changes, or cross-module document provenance cleanup.
```

- [ ] **Step 5: Run strict type check**

Run:

```bash
uv run --project backend pyright
```

Expected: PASS. If pyright reports Qdrant type mismatches around optional SDK models, fix them in `qdrant_adapter.py` using narrow `Protocol` types and `cast()` without leaking SDK types outside the adapter.

- [ ] **Step 6: Run lint**

Run:

```bash
uv run --project backend ruff check backend/vectorstore backend/tests/vectorstore backend/events/types.py backend/events/codec.py backend/tests/events/test_codec.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/vectorstore/test_architecture.py backend/pyproject.toml backend/vectorstore/README.md
git commit -m "docs(vectorstore): document 1.0 release boundary"
```

---

### Task 6: Full Release Verification

**Files:**
- No code changes expected.

- [ ] **Step 1: Run vectorstore unit tests**

Run:

```bash
uv run --project backend pytest backend/tests/vectorstore backend/tests/events/test_codec.py -v
```

Expected: PASS.

- [ ] **Step 2: Run coverage gate**

Run:

```bash
uv run --project backend pytest --cov=vectorstore --cov-report=term-missing backend/tests/vectorstore
```

Expected: PASS with total coverage at or above 90%.

- [ ] **Step 3: Run live Qdrant release gate**

Run with a live Qdrant instance:

```bash
QDRANT_URL=http://localhost:6333 uv run --project backend pytest backend/tests/vectorstore/test_qdrant_adapter.py -m integration -v
```

Expected: PASS.

- [ ] **Step 4: Run strict type check**

Run:

```bash
uv run --project backend pyright
```

Expected: PASS.

- [ ] **Step 5: Run lint**

Run:

```bash
uv run --project backend ruff check backend/vectorstore backend/tests/vectorstore backend/events/types.py backend/events/codec.py backend/tests/events/test_codec.py
```

Expected: PASS.

- [ ] **Step 6: Inspect final diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only intentional vectorstore 1.0 changes are present. Existing unrelated untracked files such as `.claude/`, `sample_data/`, or unrelated plan files must remain untouched unless the user explicitly asks to include them.

- [ ] **Step 7: Commit verification-only cleanup if needed**

If verification required small fixes, commit them:

```bash
git add backend/vectorstore backend/tests/vectorstore backend/events backend/tests/events backend/pyproject.toml
git commit -m "fix(vectorstore): satisfy 1.0 release gates"
```

If no fixes were needed, do not create an empty commit.
