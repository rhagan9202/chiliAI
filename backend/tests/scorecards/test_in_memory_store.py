from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from scorecards.adapters.in_memory import InMemoryScorecardRunRepository
from scorecards.models import ScorecardRun


BASE_TIME = datetime(2026, 7, 1, tzinfo=UTC)


def _run(
    run_id: str,
    *,
    kb: str = "kb-1",
    template_id: str = "uh_scorecard",
    status: str = "generated",
    created_at: datetime = BASE_TIME,
    snapshot_hash: str = "snapshot-a",
) -> ScorecardRun:
    return ScorecardRun(
        id=run_id,
        knowledge_base_id=kb,
        template_id=template_id,
        template_name="Unaccompanied Housing Scorecard",
        scope_type="installation",
        scope_id="jbsa",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        source_snapshot_hash=snapshot_hash,
        status=status,  # type: ignore[arg-type]
        overall_health="incomplete",
        created_at=created_at,
        updated_at=created_at,
    )


def test_upsert_is_idempotent_on_natural_key_and_does_not_replace() -> None:
    repo = InMemoryScorecardRunRepository()
    original = _run("run-original")
    replacement = _run("run-replacement").model_copy(
        update={"template_name": "Changed", "status": "failed"}
    )

    first = repo.upsert(original)
    second = repo.upsert(replacement)

    assert first == original
    assert second == original
    stored = repo.get(knowledge_base_id="kb-1", run_id="run-original")
    assert stored == original
    assert repo.get(knowledge_base_id="kb-1", run_id="run-replacement") is None


def test_list_filters_sorts_newest_first_and_paginates() -> None:
    repo = InMemoryScorecardRunRepository()
    repo.upsert(_run("old", created_at=BASE_TIME, snapshot_hash="snapshot-old"))
    repo.upsert(
        _run(
            "new-b",
            created_at=BASE_TIME + timedelta(hours=1),
            snapshot_hash="snapshot-new-b",
        )
    )
    repo.upsert(
        _run(
            "new-a",
            created_at=BASE_TIME + timedelta(hours=1),
            snapshot_hash="snapshot-new-a",
        )
    )
    repo.upsert(
        _run(
            "other-template",
            template_id="mfh_scorecard",
            snapshot_hash="snapshot-mfh",
        )
    )
    repo.upsert(_run("failed", status="failed", snapshot_hash="snapshot-f"))
    repo.upsert(_run("other-kb", kb="kb-2", snapshot_hash="snapshot-b"))

    items, total = repo.list(
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        status="generated",
        limit=2,
        offset=0,
    )

    assert total == 3
    assert [item.id for item in items] == ["new-b", "new-a"]

    next_items, next_total = repo.list(
        knowledge_base_id="kb-1",
        template_id="uh_scorecard",
        status="generated",
        limit=2,
        offset=2,
    )
    assert next_total == 3
    assert [item.id for item in next_items] == ["old"]


def test_delete_by_kb_removes_matching_runs_and_returns_count() -> None:
    repo = InMemoryScorecardRunRepository()
    repo.upsert(_run("a", kb="kb-delete", snapshot_hash="snapshot-a"))
    repo.upsert(_run("b", kb="kb-delete", snapshot_hash="snapshot-b"))
    repo.upsert(_run("c", kb="kb-keep", snapshot_hash="snapshot-c"))

    assert repo.delete_by_kb("kb-delete") == 2
    assert repo.delete_by_kb("kb-delete") == 0
    assert repo.get(knowledge_base_id="kb-keep", run_id="c") is not None
