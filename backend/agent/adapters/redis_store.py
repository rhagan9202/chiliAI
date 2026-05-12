"""Redis workflow run store adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from redis import Redis

from agent.exceptions import WorkflowRunNotFoundError
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowRunUpdate
from shared.utils import utc_now

__all__ = ["RedisWorkflowRunStore"]

RedisValue = str | bytes | bytearray | memoryview


class RedisWorkflowRunStore:
    """Redis-backed workflow run store shared by API and worker processes."""

    WORKFLOW_PREFIX = "workflow:"
    IDEMPOTENCY_PREFIX = "workflow:idempotency:"
    CREATED_INDEX = "workflow:index:created_at"

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = "chiliai:",
        client: Redis | None = None,
    ) -> None:
        self._client = client or Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            redis_url,
            decode_responses=True,
        )
        self._prefix = key_prefix

    def save_run(self, run: WorkflowRun) -> WorkflowRun:
        previous = self._get_optional(run.workflow_id)
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
            if indexed_workflow_id is not None and indexed_workflow_id != run.workflow_id:
                raise ValueError(
                    "Workflow idempotency key already exists for this knowledge base."
                )
        stored = run.model_copy(deep=True)
        self._client.set(self._workflow_key(stored.workflow_id), stored.model_dump_json())
        self._client.zadd(
            self._key(self.CREATED_INDEX),
            {stored.workflow_id: _datetime_score(stored.created_at)},
        )
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
    ) -> list[WorkflowRun]:
        if limit < 0:
            raise ValueError("limit must be non-negative.")
        if offset < 0:
            raise ValueError("offset must be non-negative.")
        workflow_ids = cast(
            list[RedisValue],
            self._client.zrevrange(  # pyright: ignore[reportUnknownMemberType]
                self._key(self.CREATED_INDEX), 0, -1
            ),
        )
        runs: list[WorkflowRun] = []
        for workflow_id_value in workflow_ids:
            workflow_id = _decode_redis_string(workflow_id_value)
            run = self._get_optional(workflow_id)
            if run is None:
                continue
            if knowledge_base_id is not None and run.knowledge_base_id != knowledge_base_id:
                continue
            if status is not None and run.status != status:
                continue
            runs.append(run)
        return [run.model_copy(deep=True) for run in runs[offset : offset + limit]]

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

    def delete_run(self, workflow_id: str) -> None:
        existing = self._get_optional(workflow_id)
        if existing is not None and existing.idempotency_key is not None:
            self._client.delete(
                self._idempotency_key(existing.knowledge_base_id, existing.idempotency_key)
            )
        self._client.delete(self._workflow_key(workflow_id))
        self._client.zrem(self._key(self.CREATED_INDEX), workflow_id)

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

    def _key(self, suffix: str) -> str:
        return f"{self._prefix}{suffix}"


def _datetime_score(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _decode_redis_string(value: RedisValue) -> str:
    if isinstance(value, str):
        return value
    return bytes(value).decode("utf-8")
