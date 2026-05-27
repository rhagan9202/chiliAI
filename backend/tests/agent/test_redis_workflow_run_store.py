"""Tests for the Redis workflow run store adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.adapters.redis_store import RedisWorkflowRunStore
from agent.exceptions import WorkflowRunNotFoundError
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}

    def set(self, key: str, value: str, nx: bool = False) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return 1 if existed else 0

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        sorted_set = self.sorted_sets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in sorted_set:
                added += 1
            sorted_set[member] = score
        return added

    def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        members = sorted(
            self.sorted_sets.get(key, {}),
            key=lambda member: self.sorted_sets[key][member],
            reverse=True,
        )
        if end == -1:
            return members[start:]
        return members[start : end + 1]

    def zrem(self, key: str, member: str) -> int:
        sorted_set = self.sorted_sets.get(key, {})
        existed = member in sorted_set
        sorted_set.pop(member, None)
        return 1 if existed else 0

    def pipeline(self) -> "_FakeRedisPipeline":
        return _FakeRedisPipeline(self)


class _FakeRedisPipeline:
    def __init__(self, client: _FakeRedis) -> None:
        self._client = client
        self._commands: list[tuple[str, str, str]] = []
        self._in_multi = False

    def watch(self, key: str) -> None:
        assert key

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def multi(self) -> None:
        self._in_multi = True

    def set(self, key: str, value: str) -> bool | None:
        if self._in_multi:
            self._commands.append(("set", key, value))
            return None
        return self._client.set(key, value)

    def execute(self) -> list[object]:
        results: list[object] = []
        for command, key, value in self._commands:
            if command == "set":
                results.append(self._client.set(key, value))
        self.reset()
        return results

    def reset(self) -> None:
        self._commands.clear()
        self._in_multi = False


def _run(
    *,
    workflow_id: str = "workflow-1",
    knowledge_base_id: str = "kb-1",
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    idempotency_key: str | None = None,
) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=workflow_id,
        knowledge_base_id=knowledge_base_id,
        trigger_event_type="documents.uploaded",
        status=status,
        steps=[WorkflowStepState(step_name="parse")],
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=updated_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        idempotency_key=idempotency_key,
    )


def _store() -> RedisWorkflowRunStore:
    return RedisWorkflowRunStore(
        redis_url="redis://unused",
        client=_FakeRedis(),  # pyright: ignore[reportArgumentType]
    )


def test_redis_workflow_run_store_saves_and_loads_detached_run() -> None:
    store = _store()
    run = _run(idempotency_key="abc-123")

    saved = store.save_run(run)
    saved.metadata["mutated"] = True

    loaded = store.get_run("workflow-1")
    assert loaded == run
    assert "mutated" not in loaded.metadata


def test_redis_workflow_run_store_lists_newest_first_and_filters() -> None:
    store = _store()
    older = _run(
        workflow_id="older",
        knowledge_base_id="kb-1",
        status=WorkflowRunStatus.RUNNING,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = _run(
        workflow_id="newer",
        knowledge_base_id="kb-2",
        status=WorkflowRunStatus.COMPLETED,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    store.save_run(older)
    store.save_run(newer)

    assert [run.workflow_id for run in store.list_runs()] == ["newer", "older"]
    assert [run.workflow_id for run in store.list_runs(knowledge_base_id="kb-1")] == ["older"]
    assert [run.workflow_id for run in store.list_runs(status=WorkflowRunStatus.COMPLETED)] == ["newer"]


def test_redis_workflow_run_store_updates_run_and_timestamp() -> None:
    store = _store()
    run = store.save_run(_run())

    updated = store.update_run(
        "workflow-1",
        WorkflowRunUpdate(status=WorkflowRunStatus.COMPLETED),
    )

    assert updated.status is WorkflowRunStatus.COMPLETED
    assert updated.updated_at >= run.updated_at


def test_redis_workflow_run_store_update_if_current_updates_matching_run() -> None:
    store = _store()
    run = store.save_run(_run(status=WorkflowRunStatus.RUNNING))

    updated = store.update_run_if_current(
        "workflow-1",
        WorkflowRunUpdate(
            status=WorkflowRunStatus.FAILED,
            metadata={"reason": "stale_workflow_reconciled"},
        ),
        expected_statuses={WorkflowRunStatus.RUNNING},
        updated_before=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert updated is not None
    assert updated.status is WorkflowRunStatus.FAILED
    assert updated.updated_at >= run.updated_at
    assert updated.metadata["reason"] == "stale_workflow_reconciled"


def test_redis_workflow_run_store_update_if_current_returns_none_on_stale_condition() -> None:
    store = _store()
    store.save_run(_run(status=WorkflowRunStatus.COMPLETED))

    updated = store.update_run_if_current(
        "workflow-1",
        WorkflowRunUpdate(status=WorkflowRunStatus.FAILED),
        expected_statuses={WorkflowRunStatus.RUNNING},
        updated_before=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert updated is None
    assert store.get_run("workflow-1").status is WorkflowRunStatus.COMPLETED


def test_redis_workflow_run_store_enforces_idempotency_per_kb() -> None:
    store = _store()
    store.save_run(_run(workflow_id="workflow-1", idempotency_key="shared"))

    with pytest.raises(ValueError, match="idempotency key"):
        store.save_run(_run(workflow_id="workflow-2", idempotency_key="shared"))

    found = store.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="shared",
    )
    assert found is not None
    assert found.workflow_id == "workflow-1"


def test_redis_workflow_run_store_deletes_run_and_indexes() -> None:
    store = _store()
    store.save_run(_run(idempotency_key="abc-123"))

    store.delete_run("workflow-1")

    with pytest.raises(WorkflowRunNotFoundError):
        store.get_run("workflow-1")
    assert store.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="abc-123",
    ) is None
    assert store.list_runs() == []
