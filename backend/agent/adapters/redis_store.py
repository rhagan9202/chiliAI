"""Redis workflow run store adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import cast

from redis import Redis
from redis.exceptions import RedisError, WatchError

from agent.adapters.protocols import StoreHealth, WorkflowRunPage
from agent.exceptions import WorkflowRunNotFoundError
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowRunUpdate
from shared.utils import utc_now

__all__ = ["RedisWorkflowRunStore"]

RedisValue = str | bytes | bytearray | memoryview


class RedisWorkflowRunStore:
    """Redis-backed workflow run store shared by API and worker processes."""

    WORKFLOW_PREFIX = "workflow:"
    IDEMPOTENCY_PREFIX = "workflow:idempotency:"
    CORRELATION_PREFIX = "workflow:correlation:"
    CREATED_INDEX = "workflow:index:created_at"
    KB_INDEX_PREFIX = "workflow:index:knowledge_base:"
    STATUS_INDEX_PREFIX = "workflow:index:status:"
    KB_STATUS_INDEX_PREFIX = "workflow:index:knowledge_base_status:"

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = "chiliai:",
        client: Redis | None = None,
        socket_connect_timeout: float = 2.0,
        socket_timeout: float = 2.0,
        retry_on_timeout: bool = True,
        health_timeout_seconds: float = 2.0,
    ) -> None:
        self._client = client or Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            redis_url,
            decode_responses=True,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            retry_on_timeout=retry_on_timeout,
        )
        self._prefix = key_prefix
        self._health_timeout_seconds = health_timeout_seconds

    def save_run(self, run: WorkflowRun) -> WorkflowRun:
        previous = self._get_optional(run.workflow_id)
        claimed_idempotency_key: str | None = None
        if run.idempotency_key is not None:
            idempotency_key = self._idempotency_key(
                run.knowledge_base_id,
                run.idempotency_key,
            )
            indexed_workflow_id = self._get_string(idempotency_key)
            if indexed_workflow_id is None:
                created = bool(self._client.set(idempotency_key, run.workflow_id, nx=True))
                if not created:
                    indexed_workflow_id = self._get_string(idempotency_key)
                else:
                    claimed_idempotency_key = idempotency_key
            if indexed_workflow_id is not None and indexed_workflow_id != run.workflow_id:
                raise ValueError(
                    "Workflow idempotency key already exists for this knowledge base."
                )
        incoming_correlation_id = run.metadata.get("correlation_id")
        try:
            if isinstance(incoming_correlation_id, str):
                correlation_key = self._correlation_key(incoming_correlation_id)
                claimed = bool(
                    self._client.set(correlation_key, run.workflow_id, nx=True)
                )
                if not claimed:
                    indexed_workflow_id = self._get_string(correlation_key)
                    if indexed_workflow_id != run.workflow_id:
                        raise ValueError("Workflow correlation id already exists.")
        except ValueError:
            if (
                claimed_idempotency_key is not None
                and self._get_string(claimed_idempotency_key) == run.workflow_id
            ):
                self._client.delete(claimed_idempotency_key)
            raise
        stored = run.model_copy(deep=True)
        self._client.set(self._workflow_key(stored.workflow_id), stored.model_dump_json())
        self._update_listing_indexes(previous, stored)
        if previous is not None and previous.idempotency_key is not None:
            previous_key = self._idempotency_key(
                previous.knowledge_base_id,
                previous.idempotency_key,
            )
            if previous.idempotency_key != stored.idempotency_key:
                self._client.delete(previous_key)
        if stored.idempotency_key is not None:
            self._client.set(
                self._idempotency_key(stored.knowledge_base_id, stored.idempotency_key),
                stored.workflow_id,
            )
        previous_correlation_id = (
            previous.metadata.get("correlation_id") if previous is not None else None
        )
        stored_correlation_id = stored.metadata.get("correlation_id")
        if (
            isinstance(previous_correlation_id, str)
            and previous_correlation_id != stored_correlation_id
        ):
            self._client.delete(self._correlation_key(previous_correlation_id))
        if isinstance(stored_correlation_id, str):
            self._client.set(
                self._correlation_key(stored_correlation_id), stored.workflow_id
            )
        return stored.model_copy(deep=True)

    def get_run(self, workflow_id: str) -> WorkflowRun:
        run = self._get_optional(workflow_id)
        if run is None:
            raise WorkflowRunNotFoundError(workflow_id)
        return run

    def list_runs(
        self,
        *,
        knowledge_base_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowRunPage:
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        if offset < 0:
            raise ValueError("offset must be non-negative.")
        index_key = self._listing_index_key(
            knowledge_base_id=knowledge_base_id,
            status=status,
        )
        scan_start = offset
        window_size = limit + 1 if limit > 0 else 1
        runs: list[WorkflowRun] = []
        stale_entries: list[tuple[str, int]] = []
        has_more = False
        next_offset = offset if limit == 0 else None

        while len(runs) <= limit:
            scan_end = scan_start + window_size - 1
            workflow_ids = cast(
                list[RedisValue],
                self._client.zrevrange(  # pyright: ignore[reportUnknownMemberType]
                    index_key,
                    scan_start,
                    scan_end,
                ),
            )
            if not workflow_ids:
                break

            for index, workflow_id_value in enumerate(workflow_ids):
                index_position = scan_start + index
                workflow_id = _decode_redis_string(workflow_id_value)
                run = self._get_optional(workflow_id)
                if run is None:
                    stale_entries.append((workflow_id, index_position))
                    continue
                if (
                    knowledge_base_id is not None
                    and run.knowledge_base_id != knowledge_base_id
                ):
                    continue
                if status is not None and run.status != status:
                    continue
                if len(runs) < limit:
                    runs.append(run)
                    next_offset = index_position + 1
                    continue
                has_more = True
                break

            if has_more or len(workflow_ids) < window_size:
                break
            scan_start += len(workflow_ids)

        if has_more and next_offset is not None:
            next_offset -= sum(
                1 for _, index_position in stale_entries if index_position < next_offset
            )

        for workflow_id, _ in stale_entries:
            self._client.zrem(index_key, workflow_id)

        items = [run.model_copy(deep=True) for run in runs[:limit]]
        return WorkflowRunPage(
            items=items,
            has_more=has_more,
            next_offset=next_offset if has_more else None,
        )

    def update_run(self, workflow_id: str, update: WorkflowRunUpdate) -> WorkflowRun:
        existing = self.get_run(workflow_id)
        patch = update.model_dump(exclude_none=True)
        if not patch:
            return existing.model_copy(deep=True)
        patch.setdefault("updated_at", utc_now())
        merged = existing.model_dump()
        merged.update(patch)
        updated = WorkflowRun.model_validate(merged)
        return self.save_run(updated)

    def update_run_if_current(
        self,
        workflow_id: str,
        update: WorkflowRunUpdate,
        *,
        expected_statuses: set[WorkflowRunStatus] | frozenset[WorkflowRunStatus],
        updated_before: datetime | None = None,
    ) -> WorkflowRun | None:
        workflow_key = self._workflow_key(workflow_id)
        for _ in range(3):
            pipe = self._client.pipeline()  # pyright: ignore[reportUnknownMemberType]
            try:
                pipe.watch(workflow_key)
                raw = pipe.get(workflow_key)
                if raw is None:
                    return None
                existing = WorkflowRun.model_validate_json(
                    _decode_redis_string(cast(RedisValue, raw))
                )
                if existing.status not in expected_statuses:
                    return None
                if updated_before is not None and existing.updated_at >= updated_before:
                    return None
                patch = update.model_dump(exclude_none=True)
                if not patch:
                    return existing.model_copy(deep=True)
                patch.setdefault("updated_at", utc_now())
                merged = existing.model_dump()
                merged.update(patch)
                updated = WorkflowRun.model_validate(merged)
                pipe.multi()
                pipe.set(workflow_key, updated.model_dump_json())
                pipe.execute()
                self._update_listing_indexes(existing, updated)
                return updated.model_copy(deep=True)
            except WatchError:
                continue
            finally:
                pipe.reset()
        return None

    def delete_run(self, workflow_id: str) -> None:
        existing = self._get_optional(workflow_id)
        if existing is not None:
            if existing.idempotency_key is not None:
                self._client.delete(
                    self._idempotency_key(
                        existing.knowledge_base_id, existing.idempotency_key
                    )
                )
            correlation_id = existing.metadata.get("correlation_id")
            if isinstance(correlation_id, str):
                self._client.delete(self._correlation_key(correlation_id))
        self._client.delete(self._workflow_key(workflow_id))
        if existing is not None:
            self._delete_listing_indexes(existing)

    def find_by_idempotency_key(
        self,
        *,
        knowledge_base_id: str,
        idempotency_key: str,
    ) -> WorkflowRun | None:
        workflow_id = self._get_string(
            self._idempotency_key(knowledge_base_id, idempotency_key)
        )
        if workflow_id is None:
            return None
        return self._get_optional(workflow_id)

    def find_by_correlation_id(self, correlation_id: str) -> WorkflowRun | None:
        workflow_id = self._get_string(self._correlation_key(correlation_id))
        if workflow_id is None:
            return None
        return self._get_optional(workflow_id)

    def check_health(self) -> StoreHealth:
        started_at = monotonic()
        try:
            self._client.ping()
        except RedisError as exc:
            return StoreHealth(
                status="unhealthy",
                latency_ms=_elapsed_ms(started_at),
                error=str(exc),
            )
        latency_ms = _elapsed_ms(started_at)
        if latency_ms > self._health_timeout_seconds * 1000:
            return StoreHealth(
                status="unhealthy",
                latency_ms=latency_ms,
                error="Redis health check exceeded timeout.",
            )
        return StoreHealth(status="ok", latency_ms=latency_ms)

    def _get_optional(self, workflow_id: str) -> WorkflowRun | None:
        raw = self._get_string(self._workflow_key(workflow_id))
        if raw is None:
            return None
        return WorkflowRun.model_validate_json(raw).model_copy(deep=True)

    def _get_string(self, key: str) -> str | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        return _decode_redis_string(cast(RedisValue, raw))

    def _workflow_key(self, workflow_id: str) -> str:
        return self._key(f"{self.WORKFLOW_PREFIX}{workflow_id}")

    def _idempotency_key(self, knowledge_base_id: str, idempotency_key: str) -> str:
        return self._key(
            f"{self.IDEMPOTENCY_PREFIX}{knowledge_base_id}:{idempotency_key}"
        )

    def _correlation_key(self, correlation_id: str) -> str:
        return self._key(f"{self.CORRELATION_PREFIX}{correlation_id}")

    def _listing_index_key(
        self,
        *,
        knowledge_base_id: str | None,
        status: WorkflowRunStatus | None,
    ) -> str:
        if knowledge_base_id is not None and status is not None:
            return self._key(
                f"{self.KB_STATUS_INDEX_PREFIX}{knowledge_base_id}:{status.value}"
            )
        if knowledge_base_id is not None:
            return self._key(f"{self.KB_INDEX_PREFIX}{knowledge_base_id}")
        if status is not None:
            return self._key(f"{self.STATUS_INDEX_PREFIX}{status.value}")
        return self._key(self.CREATED_INDEX)

    def _listing_index_keys_for_run(self, run: WorkflowRun) -> set[str]:
        return {
            self._key(self.CREATED_INDEX),
            self._key(f"{self.KB_INDEX_PREFIX}{run.knowledge_base_id}"),
            self._key(f"{self.STATUS_INDEX_PREFIX}{run.status.value}"),
            self._key(
                f"{self.KB_STATUS_INDEX_PREFIX}{run.knowledge_base_id}:{run.status.value}"
            ),
        }

    def _update_listing_indexes(
        self,
        previous: WorkflowRun | None,
        stored: WorkflowRun,
    ) -> None:
        workflow_id = stored.workflow_id
        if previous is not None:
            stale_keys = self._listing_index_keys_for_run(previous) - (
                self._listing_index_keys_for_run(stored)
            )
            for key in stale_keys:
                self._client.zrem(key, workflow_id)
        score = _datetime_score(stored.created_at)
        for key in self._listing_index_keys_for_run(stored):
            self._client.zadd(key, {workflow_id: score})

    def _delete_listing_indexes(self, run: WorkflowRun) -> None:
        for key in self._listing_index_keys_for_run(run):
            self._client.zrem(key, run.workflow_id)

    def _key(self, suffix: str) -> str:
        return f"{self._prefix}{suffix}"


def _datetime_score(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _elapsed_ms(started_at: float) -> float:
    return (monotonic() - started_at) * 1000


def _decode_redis_string(value: RedisValue) -> str:
    if isinstance(value, str):
        return value
    return bytes(value).decode("utf-8")
