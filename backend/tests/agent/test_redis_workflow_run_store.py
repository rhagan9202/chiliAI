"""Tests for the Redis workflow run store adapter."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from redis.exceptions import RedisError

from agent.adapters.redis_store import RedisWorkflowRunStore
from agent.exceptions import WorkflowRunNotFoundError
from agent.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunUpdate,
    WorkflowStepState,
)
from shared.utils import generate_id


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.zrevrange_calls: list[tuple[str, int, int]] = []
        self.ping_error: RedisError | None = None
        self.ping_count = 0

    def ping(self) -> bool:
        self.ping_count += 1
        if self.ping_error is not None:
            raise self.ping_error
        return True

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
        self.zrevrange_calls.append((key, start, end))
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


def test_redis_workflow_run_store_health_pings_client() -> None:
    client = _FakeRedis()
    store = RedisWorkflowRunStore(
        redis_url="redis://unused",
        client=client,  # pyright: ignore[reportArgumentType]
    )

    health = store.check_health()

    assert health.status == "ok"
    assert health.latency_ms is not None
    assert health.latency_ms >= 0
    assert health.error is None
    assert client.ping_count == 1


def test_redis_workflow_run_store_health_reports_redis_error() -> None:
    client = _FakeRedis()
    client.ping_error = RedisError("redis unavailable")
    store = RedisWorkflowRunStore(
        redis_url="redis://unused",
        client=client,  # pyright: ignore[reportArgumentType]
    )

    health = store.check_health()

    assert health.status == "unhealthy"
    assert health.latency_ms is not None
    assert health.latency_ms >= 0
    assert health.error == "redis unavailable"


def test_redis_workflow_run_store_configures_default_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    client = _FakeRedis()

    def from_url(redis_url: str, **kwargs: object) -> _FakeRedis:
        captured["redis_url"] = redis_url
        captured.update(kwargs)
        return client

    monkeypatch.setattr("agent.adapters.redis_store.Redis.from_url", from_url)

    store = RedisWorkflowRunStore(redis_url="redis://localhost:6379/0")

    assert store.check_health().status == "ok"
    assert captured == {
        "redis_url": "redis://localhost:6379/0",
        "decode_responses": True,
        "socket_connect_timeout": 2.0,
        "socket_timeout": 2.0,
        "retry_on_timeout": True,
    }


def test_redis_workflow_run_store_uses_injected_client_without_recreating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def from_url(redis_url: str, **kwargs: object) -> _FakeRedis:
        raise AssertionError("Redis.from_url should not be called")

    monkeypatch.setattr("agent.adapters.redis_store.Redis.from_url", from_url)

    store = RedisWorkflowRunStore(
        redis_url="redis://unused",
        client=_FakeRedis(),  # pyright: ignore[reportArgumentType]
        socket_connect_timeout=9.0,
        socket_timeout=8.0,
        retry_on_timeout=False,
    )

    assert store.check_health().status == "ok"


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

    assert [run.workflow_id for run in store.list_runs().items] == ["newer", "older"]
    assert [run.workflow_id for run in store.list_runs(knowledge_base_id="kb-1").items] == ["older"]
    assert [run.workflow_id for run in store.list_runs(status=WorkflowRunStatus.COMPLETED).items] == ["newer"]


def test_redis_workflow_run_store_returns_page_metadata() -> None:
    store = _store()
    for index in range(3):
        store.save_run(
            _run(
                workflow_id=f"w-{index}",
                created_at=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
            )
        )

    page = store.list_runs(limit=2, offset=0)

    assert [run.workflow_id for run in page.items] == ["w-2", "w-1"]
    assert page.has_more is True
    assert page.next_offset == 2


def test_redis_workflow_run_store_scans_past_stale_index_entries() -> None:
    client = _FakeRedis()
    store = RedisWorkflowRunStore(
        redis_url="redis://unused",
        client=client,  # pyright: ignore[reportArgumentType]
    )
    store.save_run(
        _run(
            workflow_id="valid-new",
            created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        )
    )
    store.save_run(
        _run(
            workflow_id="valid-old",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    )
    index_key = "chiliai:workflow:index:created_at"
    client.zadd(
        index_key,
        {"missing-newest": 9_999_999_999.0, "missing-next": 9_999_999_998.0},
    )

    page = store.list_runs(limit=1)

    assert [run.workflow_id for run in page.items] == ["valid-new"]
    assert page.has_more is True
    assert page.next_offset == 1
    assert "missing-newest" not in client.sorted_sets[index_key]
    assert "missing-next" not in client.sorted_sets[index_key]

    next_page = store.list_runs(limit=1, offset=page.next_offset)

    assert [run.workflow_id for run in next_page.items] == ["valid-old"]
    assert next_page.has_more is False
    assert next_page.next_offset is None


def test_redis_workflow_run_store_scans_filtered_index_past_stale_entries() -> None:
    client = _FakeRedis()
    store = RedisWorkflowRunStore(
        redis_url="redis://unused",
        client=client,  # pyright: ignore[reportArgumentType]
    )
    store.save_run(
        _run(
            workflow_id="target",
            knowledge_base_id="kb-1",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    )
    store.save_run(
        _run(
            workflow_id="wrong-kb",
            knowledge_base_id="kb-2",
            created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        )
    )
    index_key = "chiliai:workflow:index:knowledge_base:kb-1"
    client.zadd(
        index_key,
        {"missing": 9_999_999_999.0, "wrong-kb": 9_999_999_998.0},
    )

    page = store.list_runs(knowledge_base_id="kb-1", limit=1)

    assert [run.workflow_id for run in page.items] == ["target"]
    assert page.has_more is False
    assert page.next_offset is None
    assert "missing" not in client.sorted_sets[index_key]
    assert "wrong-kb" in client.sorted_sets[index_key]


def test_redis_workflow_run_store_uses_narrowest_filtered_index() -> None:
    client = _FakeRedis()
    store = RedisWorkflowRunStore(
        redis_url="redis://unused",
        client=client,  # pyright: ignore[reportArgumentType]
    )
    store.save_run(_run(workflow_id="target", knowledge_base_id="kb-1"))
    store.save_run(_run(workflow_id="other-kb", knowledge_base_id="kb-2"))

    page = store.list_runs(knowledge_base_id="kb-1", limit=1)

    assert [run.workflow_id for run in page.items] == ["target"]
    assert client.zrevrange_calls[-1] == (
        "chiliai:workflow:index:knowledge_base:kb-1",
        0,
        1,
    )


def test_redis_workflow_run_store_removes_stale_filtered_indexes_on_update() -> None:
    store = _store()
    store.save_run(
        _run(
            workflow_id="workflow-1",
            knowledge_base_id="kb-1",
            status=WorkflowRunStatus.RUNNING,
        )
    )

    store.save_run(
        _run(
            workflow_id="workflow-1",
            knowledge_base_id="kb-2",
            status=WorkflowRunStatus.COMPLETED,
        )
    )

    assert store.list_runs(knowledge_base_id="kb-1").items == []
    assert store.list_runs(status=WorkflowRunStatus.RUNNING).items == []
    assert store.list_runs(
        knowledge_base_id="kb-2",
        status=WorkflowRunStatus.COMPLETED,
    ).items[0].workflow_id == "workflow-1"


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
    assert store.list_runs().items == []


def _run_corr(
    *, workflow_id: str = "workflow-1", correlation_id: str = "corr-1"
) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=workflow_id,
        knowledge_base_id="kb-1",
        trigger_event_type="documents.uploaded",
        steps=[WorkflowStepState(step_name="parse")],
        metadata={"correlation_id": correlation_id},
    )


def test_redis_workflow_run_store_finds_by_correlation_id() -> None:
    store = _store()
    store.save_run(_run_corr(correlation_id="corr-xyz"))

    found = store.find_by_correlation_id("corr-xyz")
    assert found is not None
    assert found.workflow_id == "workflow-1"
    assert store.find_by_correlation_id("missing") is None


def test_redis_workflow_run_store_enforces_unique_correlation_id() -> None:
    store = _store()
    original = _run_corr(workflow_id="workflow-1", correlation_id="shared-corr")
    duplicate = _run_corr(workflow_id="workflow-2", correlation_id="shared-corr")
    store.save_run(original)

    with pytest.raises(ValueError, match="correlation id"):
        store.save_run(duplicate)

    found = store.find_by_correlation_id("shared-corr")
    assert found is not None
    assert found.workflow_id == "workflow-1"


def test_redis_workflow_run_store_rolls_back_new_idempotency_claim_on_correlation_conflict() -> None:
    store = _store()
    original = _run_corr(workflow_id="workflow-1", correlation_id="shared-corr")
    conflict = _run_corr(
        workflow_id="workflow-2",
        correlation_id="shared-corr",
    ).model_copy(update={"idempotency_key": "new-key"}, deep=True)
    valid = _run_corr(
        workflow_id="workflow-3",
        correlation_id="other-corr",
    ).model_copy(update={"idempotency_key": "new-key"}, deep=True)
    store.save_run(original)

    with pytest.raises(ValueError, match="correlation id"):
        store.save_run(conflict)

    assert store.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="new-key",
    ) is None

    store.save_run(valid)

    found = store.find_by_idempotency_key(
        knowledge_base_id="kb-1",
        idempotency_key="new-key",
    )
    assert found is not None
    assert found.workflow_id == "workflow-3"


def test_redis_workflow_run_store_allows_same_run_to_keep_correlation_id() -> None:
    store = _store()
    original = _run_corr(workflow_id="workflow-1", correlation_id="shared-corr")
    replacement = original.model_copy(
        update={"status": WorkflowRunStatus.COMPLETED}, deep=True
    )
    store.save_run(original)

    store.save_run(replacement)

    found = store.find_by_correlation_id("shared-corr")
    assert found is not None
    assert found.workflow_id == "workflow-1"
    assert found.status is WorkflowRunStatus.COMPLETED


def test_redis_workflow_run_store_delete_clears_correlation_index() -> None:
    store = _store()
    store.save_run(_run_corr(correlation_id="corr-del"))

    store.delete_run("workflow-1")

    assert store.find_by_correlation_id("corr-del") is None


def test_redis_workflow_run_store_status_only_cas_guards_cancelled() -> None:
    store = _store()
    store.save_run(_run(status=WorkflowRunStatus.CANCELLED))

    result = store.update_run_if_current(
        "workflow-1",
        WorkflowRunUpdate(status=WorkflowRunStatus.COMPLETED),
        expected_statuses={WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING},
    )

    assert result is None
    assert store.get_run("workflow-1").status is WorkflowRunStatus.CANCELLED


@pytest.mark.integration
def test_redis_workflow_run_store_real_redis_contract() -> None:
    redis_url = os.environ.get("REDIS_URL")
    if redis_url is None:
        pytest.skip(
            "REDIS_URL is not set; skipping Redis workflow run store integration test."
        )

    key_prefix = f"test:{generate_id()}:"
    store = RedisWorkflowRunStore(redis_url=redis_url, key_prefix=key_prefix)
    health = store.check_health()
    if health.status != "ok":
        pytest.skip(f"Redis is unavailable at REDIS_URL: {health.error}")
    workflow_id = f"workflow-{generate_id()}"
    other_workflow_id = f"workflow-{generate_id()}"
    target = _run(
        workflow_id=workflow_id,
        knowledge_base_id="kb-real-1",
        status=WorkflowRunStatus.RUNNING,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        idempotency_key="idem-real-1",
    )
    other = _run(
        workflow_id=other_workflow_id,
        knowledge_base_id="kb-real-2",
        status=WorkflowRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
        idempotency_key="idem-real-2",
    )

    try:
        saved = store.save_run(target)
        store.save_run(other)

        assert store.get_run(workflow_id) == saved
        assert [run.workflow_id for run in store.list_runs().items] == [
            other_workflow_id,
            workflow_id,
        ]
        assert [
            run.workflow_id
            for run in store.list_runs(knowledge_base_id="kb-real-1").items
        ] == [workflow_id]
        assert [
            run.workflow_id
            for run in store.list_runs(status=WorkflowRunStatus.RUNNING).items
        ] == [workflow_id]

        updated = store.update_run(
            workflow_id,
            WorkflowRunUpdate(status=WorkflowRunStatus.COMPLETED),
        )

        assert updated.status is WorkflowRunStatus.COMPLETED
        assert store.list_runs(status=WorkflowRunStatus.RUNNING).items == []
        assert [
            run.workflow_id
            for run in store.list_runs(
                knowledge_base_id="kb-real-1",
                status=WorkflowRunStatus.COMPLETED,
            ).items
        ] == [workflow_id]

        store.delete_run(workflow_id)

        with pytest.raises(WorkflowRunNotFoundError):
            store.get_run(workflow_id)
        assert store.find_by_idempotency_key(
            knowledge_base_id="kb-real-1",
            idempotency_key="idem-real-1",
        ) is None
        assert store.list_runs(knowledge_base_id="kb-real-1").items == []
        assert store.list_runs(status=WorkflowRunStatus.COMPLETED).items == [other]

        store.delete_run(other_workflow_id)
        assert store.list_runs().items == []
        assert store.list_runs(knowledge_base_id="kb-real-2").items == []
        assert store.list_runs(status=WorkflowRunStatus.COMPLETED).items == []
    finally:
        cleanup_client = store.client
        try:
            keys: list[str] = list(
                cleanup_client.scan_iter(match=f"{key_prefix}*")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]  # redis-py stub gap
            )
            if keys:
                cleanup_client.delete(*keys)  # pyright: ignore[reportUnknownMemberType]  # redis-py stub gap
        except RedisError:
            pass
