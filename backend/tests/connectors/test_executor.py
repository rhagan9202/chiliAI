"""Tests for the connector page executor.

Built on the real in-memory repository, the real records service and the real
event bus rather than mocks. The behaviour under test — duplicate delivery,
event parity with the manual upload path — lives in the interaction between
those pieces, and a mock would assert only that this executor calls the
methods this executor was written to call.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from config.schema import RecordFeedConfig, RecordsConfig
from connectors.adapters.in_memory import InMemoryConnectorRepository
from connectors.exceptions import ConnectorSourceError
from connectors.executor import handle_connector_page_queued
from connectors.models import (
    ConnectorDefinitionCreate,
    ConnectorMappingRef,
    ConnectorSchedule,
    ConnectorSyncRunCreate,
    ConnectorSyncRunUpdate,
)
from connectors.sources.protocols import SourcePage
from events.adapters.in_memory import InMemoryEventBus
from events.types import AnyEvent, ConnectorPageQueuedEvent, RecordsIngestedEvent
from execution.deps import ExecutionDeps
from records.adapters.in_memory import InMemoryRawRecordStore
from records.service import create_records_service
from records.service_models import RecordSubmission

_KB_ID = "kb-1"
_CONNECTOR_ID = "cms-claims-drop"
_FEED = "claims_feed"


class _StubSource:
    """A source adapter returning scripted pages, keyed by incoming cursor."""

    def __init__(self, pages: dict[str | None, SourcePage]) -> None:
        self._pages = pages
        self.calls: list[str | None] = []

    def read_page(
        self,
        *,
        config: Mapping[str, object],
        cursor: str | None,
        limit: int,
    ) -> SourcePage:
        self.calls.append(cursor)
        if cursor not in self._pages:
            raise ConnectorSourceError(f"no scripted page for cursor {cursor!r}")
        return self._pages[cursor]


class _ExplodingSource:
    def read_page(
        self,
        *,
        config: Mapping[str, object],
        cursor: str | None,
        limit: int,
    ) -> SourcePage:
        raise ConnectorSourceError("source is unavailable")


@dataclass
class _Harness:
    deps: ExecutionDeps
    repository: InMemoryConnectorRepository
    event_bus: InMemoryEventBus
    run_id: str
    source: _StubSource | _ExplodingSource


def _feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name=_FEED,
        record_type="claim",
        source="api_push",
        id_field="id",
        record_schema={},
        allow_extra_fields=True,
    )


def _harness(
    *,
    pages: dict[str | None, SourcePage] | None = None,
    source: _ExplodingSource | None = None,
    path: Path | None = None,
) -> _Harness:
    repository = InMemoryConnectorRepository()
    repository.save_definition(
        ConnectorDefinitionCreate(
            connector_id=_CONNECTOR_ID,
            name="CMS Claims Drop",
            source_type="filesystem",
            knowledge_base_id=_KB_ID,
            schedule=ConnectorSchedule(mode="manual"),
            mapping=ConnectorMappingRef(
                mapping_id="claims",
                mapping_version="v1",
                feed_name=_FEED,
            ),
            config={"path": str(path) if path is not None else "/imports"},
        )
    )
    run = repository.create_run(
        ConnectorSyncRunCreate(
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=_KB_ID,
            requested_by="operator-1",
        )
    )
    event_bus = InMemoryEventBus()
    records_service = create_records_service(
        InMemoryRawRecordStore(),
        event_bus=event_bus,
        records_config=RecordsConfig(feeds=[_feed()]),
    )
    adapter = source if source is not None else _StubSource(pages or {})
    deps = ExecutionDeps(
        event_bus=event_bus,
        risk_service=None,
        score_run_repository=None,
        graph_repository=None,
        domain_config=None,
        records_config=RecordsConfig(feeds=[_feed()]),
        connector_repository=repository,
        records_service=records_service,
        source_adapters={"filesystem": adapter},
    )
    return _Harness(
        deps=deps,
        repository=repository,
        event_bus=event_bus,
        run_id=run.run_id,
        source=adapter,
    )


def _event(harness: _Harness, *, cursor: str | None = None) -> ConnectorPageQueuedEvent:
    return ConnectorPageQueuedEvent(
        correlation_id="corr-1",
        knowledge_base_id=_KB_ID,
        connector_id=_CONNECTOR_ID,
        run_id=harness.run_id,
        cursor=cursor,
    )


def _ingested(harness: _Harness) -> list[RecordsIngestedEvent]:
    return [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, RecordsIngestedEvent)
    ]


def _chained(harness: _Harness) -> list[ConnectorPageQueuedEvent]:
    return [
        event
        for event in harness.event_bus.published_events
        if isinstance(event, ConnectorPageQueuedEvent)
    ]


# --- happy path -------------------------------------------------------------


def test_publishes_the_same_event_the_manual_upload_path_publishes() -> None:
    """Parity is by construction, not by reimplementation.

    The executor calls the same RecordsService the upload route calls, so the
    ingest event is published by the same line of code. A hand-rolled publish
    here would be free to drift from the manual path.
    """
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}, {"id": "2"}], next_cursor=None)}
    )

    processed = handle_connector_page_queued(_event(harness), harness.deps)

    ingested = _ingested(harness)
    assert processed == 1
    assert len(ingested) == 1
    assert ingested[0].record_count == 2
    assert ingested[0].knowledge_base_id == _KB_ID
    assert ingested[0].feed_name == _FEED
    # record_type comes from the feed config, not from the connector mapping.
    assert ingested[0].record_type == "claim"


def test_does_not_publish_when_the_page_is_empty() -> None:
    harness = _harness(pages={None: SourcePage(rows=[], next_cursor=None)})

    handle_connector_page_queued(_event(harness), harness.deps)

    assert _ingested(harness) == []


def test_completes_the_run_at_the_final_page() -> None:
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}], next_cursor=None)}
    )

    handle_connector_page_queued(_event(harness), harness.deps)

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.completed_at is not None
    assert run.counters.accepted == 1
    assert run.counters.pulled == 1


def test_chains_the_next_page_instead_of_completing() -> None:
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}], next_cursor="a.csv:1")}
    )

    handle_connector_page_queued(_event(harness), harness.deps)

    chained = _chained(harness)
    run = harness.repository.get_run(harness.run_id)
    assert len(chained) == 1
    assert chained[0].cursor == "a.csv:1"
    assert chained[0].run_id == harness.run_id
    assert run is not None
    assert run.status == "running"
    assert run.source_cursor == "a.csv:1"


def test_walks_every_page_to_completion() -> None:
    harness = _harness(
        pages={
            None: SourcePage(rows=[{"id": "1"}], next_cursor="a.csv:1"),
            "a.csv:1": SourcePage(rows=[{"id": "2"}], next_cursor="a.csv:2"),
            "a.csv:2": SourcePage(rows=[{"id": "3"}], next_cursor=None),
        }
    )

    cursor: str | None = None
    for _ in range(3):
        handle_connector_page_queued(_event(harness, cursor=cursor), harness.deps)
        run = harness.repository.get_run(harness.run_id)
        assert run is not None
        cursor = run.source_cursor

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.counters.accepted == 3
    assert len(_ingested(harness)) == 3


def test_claims_the_run_out_of_queued_on_the_first_page() -> None:
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}], next_cursor="a.csv:1")}
    )

    handle_connector_page_queued(_event(harness), harness.deps)

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.status == "running"


# --- idempotency ------------------------------------------------------------


def test_is_idempotent_under_duplicate_delivery() -> None:
    """Spec 6.4 — Redis Streams is at-least-once, including after a reclaim.

    The same page redelivered must not double-count counters or publish a
    second ingest event for rows already persisted.
    """
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}, {"id": "2"}], next_cursor=None)}
    )
    event = _event(harness)

    handle_connector_page_queued(event, harness.deps)
    handle_connector_page_queued(event, harness.deps)  # redelivered

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.counters.accepted == 2  # NOT 4
    assert len(_ingested(harness)) == 1


def test_a_stale_page_event_is_skipped_rather_than_reprocessed() -> None:
    """The run's cursor is the authority on where the pull actually is.

    A page event delivered late — after the run has already moved past it —
    must not re-read that page and re-count its rows.
    """
    harness = _harness(
        pages={
            None: SourcePage(rows=[{"id": "1"}], next_cursor="a.csv:1"),
            "a.csv:1": SourcePage(rows=[{"id": "2"}], next_cursor=None),
        }
    )
    handle_connector_page_queued(_event(harness), harness.deps)
    handle_connector_page_queued(_event(harness, cursor="a.csv:1"), harness.deps)

    processed = handle_connector_page_queued(_event(harness), harness.deps)

    run = harness.repository.get_run(harness.run_id)
    assert processed == 0
    assert run is not None
    assert run.counters.accepted == 2  # not 3


def test_replaying_the_final_page_does_not_reopen_a_completed_run() -> None:
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}], next_cursor=None)}
    )
    event = _event(harness)
    handle_connector_page_queued(event, harness.deps)

    processed = handle_connector_page_queued(event, harness.deps)

    run = harness.repository.get_run(harness.run_id)
    assert processed == 0
    assert run is not None
    assert run.status == "completed"


def test_counters_do_not_move_for_rows_that_were_already_persisted() -> None:
    """The crash-between-persist-and-cursor case.

    If the worker dies after the rows land but before the cursor advances, the
    run's cursor still points at this page, so redelivery passes the cursor
    guard and re-reads it. The records service recognises the identical batch,
    neither persists nor publishes — and the counters must not move either, or
    the run would claim to have pulled rows twice that exist once.

    Simulated with a second run over the same page, which is the same situation
    from the records service's point of view: rows already in the store.
    """
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}, {"id": "2"}], next_cursor=None)}
    )
    handle_connector_page_queued(_event(harness), harness.deps)

    second = harness.repository.create_run(
        ConnectorSyncRunCreate(
            connector_id=_CONNECTOR_ID,
            knowledge_base_id=_KB_ID,
            requested_by="operator-1",
        )
    )
    replayed = _event(harness).model_copy(update={"run_id": second.run_id})
    handle_connector_page_queued(replayed, harness.deps)

    run = harness.repository.get_run(second.run_id)
    assert run is not None
    assert run.counters.accepted == 0  # the rows already exist
    assert len(_ingested(harness)) == 1  # NOT 2


def test_the_cursor_cannot_be_rewound_through_the_repository() -> None:
    """`update_run` ignores a None cursor, so progress only ever moves forward.

    This is what makes the cursor safe to use as the replay guard: nothing in
    the normal API can move a run backwards into re-reading a page it already
    consumed.
    """
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}], next_cursor="a.csv:1")}
    )
    handle_connector_page_queued(_event(harness), harness.deps)

    harness.repository.update_run(
        harness.run_id, ConnectorSyncRunUpdate(source_cursor=None)
    )

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.source_cursor == "a.csv:1"


# --- quarantine -------------------------------------------------------------


def test_invalid_rows_are_quarantined_not_dropped() -> None:
    harness = _harness(
        pages={
            None: SourcePage(
                rows=[{"id": "1"}, {"no_id_here": "row"}], next_cursor=None
            )
        }
    )

    handle_connector_page_queued(_event(harness), harness.deps)

    run = harness.repository.get_run(harness.run_id)
    quarantine = harness.repository.list_quarantine(run_id=harness.run_id)
    assert run is not None
    assert run.counters.accepted == 1
    assert run.counters.quarantined == 1
    assert quarantine.total_items == 1
    assert quarantine.items[0].reason


def test_a_page_of_only_invalid_rows_still_advances_the_run() -> None:
    """Otherwise one bad page stalls the pull forever."""
    harness = _harness(
        pages={None: SourcePage(rows=[{"nope": "1"}], next_cursor=None)}
    )

    handle_connector_page_queued(_event(harness), harness.deps)

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.counters.quarantined == 1
    assert run.counters.accepted == 0


# --- guards -----------------------------------------------------------------


def test_ignores_an_unrelated_event_type() -> None:
    harness = _harness(pages={None: SourcePage(rows=[], next_cursor=None)})
    unrelated: AnyEvent = RecordsIngestedEvent(
        knowledge_base_id=_KB_ID, feed_name=_FEED, record_type="claim", record_count=1
    )

    assert handle_connector_page_queued(unrelated, harness.deps) == 0


def test_returns_zero_when_the_repository_is_absent() -> None:
    harness = _harness(pages={None: SourcePage(rows=[], next_cursor=None)})
    deps = replace(harness.deps, connector_repository=None)

    assert handle_connector_page_queued(_event(harness), deps) == 0


def test_returns_zero_when_the_records_service_is_absent() -> None:
    harness = _harness(pages={None: SourcePage(rows=[], next_cursor=None)})
    deps = replace(harness.deps, records_service=None)

    assert handle_connector_page_queued(_event(harness), deps) == 0


def test_returns_zero_for_an_unknown_run() -> None:
    harness = _harness(pages={None: SourcePage(rows=[], next_cursor=None)})
    event = _event(harness).model_copy(update={"run_id": "no-such-run"})

    assert handle_connector_page_queued(event, harness.deps) == 0


def test_returns_zero_for_a_canceled_run() -> None:
    """Cancellation must actually stop the pull, not merely relabel it."""
    harness = _harness(
        pages={None: SourcePage(rows=[{"id": "1"}], next_cursor=None)}
    )
    harness.repository.update_run(
        harness.run_id, ConnectorSyncRunUpdate(status="canceled")
    )

    processed = handle_connector_page_queued(_event(harness), harness.deps)

    assert processed == 0
    assert _ingested(harness) == []


def test_a_missing_connector_definition_fails_the_run() -> None:
    """A run whose connector was deleted can never succeed.

    Retrying forever would keep a dead run in `running` and hide the cause, so
    the run is failed with the reason recorded on it.
    """
    harness = _harness(pages={None: SourcePage(rows=[], next_cursor=None)})
    event = _event(harness).model_copy(update={"connector_id": "deleted-connector"})

    processed = handle_connector_page_queued(event, harness.deps)

    run = harness.repository.get_run(harness.run_id)
    assert processed == 0
    assert run is not None
    assert run.status == "failed"
    assert run.error_message is not None
    assert "connector" in run.error_message


def test_a_source_type_with_no_adapter_fails_the_run() -> None:
    harness = _harness(pages={None: SourcePage(rows=[], next_cursor=None)})
    deps = replace(harness.deps, source_adapters={})

    processed = handle_connector_page_queued(_event(harness), deps)

    run = harness.repository.get_run(harness.run_id)
    assert processed == 0
    assert run is not None
    assert run.status == "failed"


def test_a_source_read_failure_propagates_for_the_worker_to_retry() -> None:
    """A transient source outage is the worker's retry/DLQ decision, not ours.

    Swallowing it here would mark the run complete having pulled nothing.
    """
    harness = _harness(source=_ExplodingSource())

    with pytest.raises(ConnectorSourceError):
        handle_connector_page_queued(_event(harness), harness.deps)

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.status != "completed"


def test_the_executor_is_registered_for_its_event_type() -> None:
    from execution.registry import registered_event_types

    assert "connector.page.queued" in registered_event_types()


# --- real source integration ------------------------------------------------


def test_end_to_end_over_a_real_filesystem_source(tmp_path: Path) -> None:
    """No stub adapter: the real CSV reader, paged to completion."""
    from connectors.sources.filesystem import FilesystemSourceAdapter

    (tmp_path / "claims.csv").write_text("id\n1\n2\n3\n", encoding="utf-8")
    harness = _harness(path=tmp_path)
    deps = replace(
        harness.deps,
        source_adapters={"filesystem": FilesystemSourceAdapter(allowed_root=tmp_path)},
    )

    cursor: str | None = None
    for _ in range(5):
        handle_connector_page_queued(_event(harness, cursor=cursor), deps)
        run = harness.repository.get_run(harness.run_id)
        assert run is not None
        if run.status == "completed":
            break
        cursor = run.source_cursor

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.counters.accepted == 3
    assert run.counters.pulled == 3


def test_rows_reach_the_store_the_manual_path_writes_to(tmp_path: Path) -> None:
    """The pulled rows must be readable by the same Flow 1 handler.

    `records.ingested` carries no rows — the worker reads them back by
    correlation id — so a pull that published the event without landing rows in
    `raw_records` would produce a silent no-op downstream.
    """
    store = InMemoryRawRecordStore()
    (tmp_path / "claims.csv").write_text("id\n1\n2\n", encoding="utf-8")
    harness = _harness(path=tmp_path)
    event_bus = InMemoryEventBus()
    from connectors.sources.filesystem import FilesystemSourceAdapter

    deps = replace(
        harness.deps,
        event_bus=event_bus,
        records_service=create_records_service(
            store,
            event_bus=event_bus,
            records_config=RecordsConfig(feeds=[_feed()]),
        ),
        source_adapters={"filesystem": FilesystemSourceAdapter(allowed_root=tmp_path)},
    )

    handle_connector_page_queued(_event(harness), deps)

    ingested = [
        event
        for event in event_bus.published_events
        if isinstance(event, RecordsIngestedEvent)
    ]
    assert len(ingested) == 1
    rows = store.load_batch(
        knowledge_base_id=_KB_ID, correlation_id=ingested[0].correlation_id
    )
    assert [row.record_id for row in rows] == ["1", "2"]


def test_submission_records_the_connector_as_its_provenance(tmp_path: Path) -> None:
    """`source_ref` is how a pulled row is traced back to its run."""
    store = InMemoryRawRecordStore()
    (tmp_path / "claims.csv").write_text("id\n1\n", encoding="utf-8")
    harness = _harness(path=tmp_path)
    event_bus = InMemoryEventBus()
    from connectors.sources.filesystem import FilesystemSourceAdapter

    deps = replace(
        harness.deps,
        event_bus=event_bus,
        records_service=create_records_service(
            store,
            event_bus=event_bus,
            records_config=RecordsConfig(feeds=[_feed()]),
        ),
        source_adapters={"filesystem": FilesystemSourceAdapter(allowed_root=tmp_path)},
    )

    handle_connector_page_queued(_event(harness), deps)

    ingested = [
        event
        for event in event_bus.published_events
        if isinstance(event, RecordsIngestedEvent)
    ]
    rows = store.load_batch(
        knowledge_base_id=_KB_ID, correlation_id=ingested[0].correlation_id
    )
    assert rows[0].source_ref is not None
    assert _CONNECTOR_ID in rows[0].source_ref
    assert harness.run_id in rows[0].source_ref


def test_submission_uses_a_stable_correlation_id_across_pages(tmp_path: Path) -> None:
    """All pages of one run share a correlation id, so the run is traceable."""
    (tmp_path / "claims.csv").write_text("id\n1\n2\n3\n", encoding="utf-8")
    harness = _harness(path=tmp_path)
    from connectors.sources.filesystem import FilesystemSourceAdapter

    deps = replace(
        harness.deps,
        source_adapters={"filesystem": FilesystemSourceAdapter(allowed_root=tmp_path)},
    )

    cursor: str | None = None
    for _ in range(5):
        handle_connector_page_queued(_event(harness, cursor=cursor), deps)
        run = harness.repository.get_run(harness.run_id)
        assert run is not None
        if run.status == "completed":
            break
        cursor = run.source_cursor

    run = harness.repository.get_run(harness.run_id)
    assert run is not None
    assert run.ingest_correlation_id is not None
    correlation_ids = {event.correlation_id for event in _ingested(harness)}
    assert correlation_ids == {run.ingest_correlation_id}


def test_unused_submission_type_is_not_file_upload() -> None:
    """Provenance guard: a pull is not a user upload.

    RecordSubmission's literal has no `connector_pull` member, so a pull is
    recorded as `api_push` plus a `source_ref`. If that literal ever gains a
    connector member this test should be updated to demand it.
    """
    assert "connector_pull" not in str(RecordSubmission.model_fields["source_type"])
