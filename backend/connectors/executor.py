"""Executor for connector sync runs.

Consumes one ``connector.page.queued`` event per page: read the page from the
source, register its rows, advance the cursor, then chain the next page or
complete the run.

Rows are registered through ``RecordsService`` — the same service the manual
upload route calls — rather than persisted here. That is what makes a pulled
batch indistinguishable downstream from an uploaded one: the ``records.ingested``
event is published by the same line of code, the same validation runs, and the
same submission-hash dedup applies. A hand-rolled persist-and-publish here
would be free to drift from the manual path, and nothing would notice until a
pulled feed behaved subtly differently from an uploaded one.

Exceptions propagate on purpose: ``run_handler_with_retry`` in the worker owns
retry and dead-lettering. Conditions that can never succeed on retry — a
deleted connector, a source type with no adapter — fail the run instead, so a
dead run reports why rather than sitting in ``running`` forever.
"""

from __future__ import annotations

import logging
import os

from config.schema import RecordFeedConfig, RecordsConfig
from connectors.models import (
    ConnectorDefinition,
    ConnectorQuarantineRecordCreate,
    ConnectorSyncCounters,
    ConnectorSyncRun,
    ConnectorSyncRunUpdate,
)
from connectors.repository import ConnectorRepositoryProtocol
from events.types import AnyEvent, ConnectorPageQueuedEvent
from execution.deps import ExecutionDeps
from execution.registry import register_handler
from records.exceptions import RecordValidationError
from records.protocols import RecordsServiceProtocol
from records.service_models import RecordIngestReceipt, RecordSubmission
from records.validation import derive_record_id
from shared.utils import generate_id, utc_now

__all__ = ["handle_connector_page_queued"]

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "canceled"})


def _positive_int_from_env(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back on anything odd."""

    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%s must be positive; using %s", name, value, default)
        return default
    return value


# Rows per page. Small enough that one page is a cheap unit of retry, large
# enough that a big drop does not generate an event per handful of rows.
_PAGE_LIMIT = _positive_int_from_env("CHILI_CONNECTOR_PAGE_LIMIT", 500)


def handle_connector_page_queued(event: AnyEvent, deps: ExecutionDeps) -> int:
    """Pull one page, ingest it, then chain the next page or finish the run."""

    if not isinstance(event, ConnectorPageQueuedEvent):
        return 0
    repository = deps.connector_repository
    records_service = deps.records_service
    event_bus = deps.event_bus
    if repository is None or records_service is None or event_bus is None:
        return 0

    run = repository.get_run(event.run_id)
    if run is None:
        logger.warning("Connector page event for unknown run id=%s", event.run_id)
        return 0
    if run.status in _TERMINAL_RUN_STATUSES:
        return 0

    # The run's cursor is the authority on where this pull actually is. A page
    # event whose cursor does not match it was already processed (Redis is
    # at-least-once) or arrived out of order; re-reading it would re-count rows
    # and make the counters describe a pull that never happened.
    if event.cursor != run.source_cursor:
        logger.info(
            "Skipping stale connector page run=%s event_cursor=%r run_cursor=%r",
            run.run_id,
            event.cursor,
            run.source_cursor,
        )
        return 0

    now = utc_now()
    # Already-running runs are mid-pull and must not be re-claimed; only the
    # first page transitions the run out of `queued`.
    claimed = (
        run if run.status == "running" else repository.claim_sync_run(run.run_id, now=now)
    )
    if claimed is None:
        return 0

    connector = repository.get_definition(
        knowledge_base_id=event.knowledge_base_id,
        connector_id=event.connector_id,
    )
    if connector is None:
        return _fail_run(
            repository,
            claimed,
            f"connector '{event.connector_id}' no longer exists",
        )

    source_adapters = deps.source_adapters or {}
    adapter = source_adapters.get(connector.source_type)
    if adapter is None:
        return _fail_run(
            repository,
            claimed,
            f"no source adapter is configured for source type '{connector.source_type}'",
        )

    # One correlation id per run, assigned on the first page, so every page's
    # rows and every published ingest event trace back to the same sync run.
    correlation_id = claimed.ingest_correlation_id or generate_id()

    # Raises on a source failure: a transient outage is the worker's
    # retry-versus-dead-letter decision. Swallowing it would complete the run
    # having pulled nothing.
    feed = _resolve_feed(deps.records_config, connector.mapping.feed_name)
    if feed is None:
        return _fail_run(
            repository,
            claimed,
            f"feed '{connector.mapping.feed_name}' is not configured for this domain",
        )

    page = adapter.read_page(
        config=connector.config, cursor=event.cursor, limit=_PAGE_LIMIT
    )

    # A row with no derivable id raises out of `register_records` and fails the
    # whole submission — correct for an upload, where a client sees one clear
    # error, but fatal here: the exception would retry, dead-letter, and leave
    # the run stuck in `running` forever over a single malformed row. Partition
    # first, using the very function the service will use, so what is filtered
    # out is exactly what would have been rejected.
    ingestible, unidentifiable = _partition_by_derivable_id(feed, page.rows)

    receipt = _register_rows(
        records_service=records_service,
        connector=connector,
        run=claimed,
        rows=ingestible,
        correlation_id=correlation_id,
    )

    # Counters and quarantine rows move only for a batch that actually landed.
    # A redelivered page after a crash between persist and cursor-write reports
    # `duplicate`: the records service neither persists nor publishes, so
    # counting it again would double the run's totals for rows stored exactly
    # once, and re-quarantining would duplicate the operator's error list.
    counters = claimed.counters
    if receipt is None or not receipt.duplicate:
        rejected_count = 0 if receipt is None else receipt.rejected_count
        accepted_count = 0 if receipt is None else receipt.accepted_count
        _quarantine_rows(
            repository,
            connector,
            claimed,
            unidentifiable=unidentifiable,
            receipt=receipt,
        )
        counters = ConnectorSyncCounters(
            pulled=claimed.counters.pulled + len(page.rows),
            accepted=claimed.counters.accepted + accepted_count,
            quarantined=(
                claimed.counters.quarantined + rejected_count + len(unidentifiable)
            ),
            failed=claimed.counters.failed,
        )

    # Cursor advances only after the rows are durable and the ingest event is
    # published — both happen inside register_records. Advancing first would
    # skip these rows forever if the process died in between.
    repository.update_run(
        claimed.run_id,
        ConnectorSyncRunUpdate(
            counters=counters,
            source_cursor=page.next_cursor,
            ingest_correlation_id=correlation_id,
        ),
    )

    if page.next_cursor is None:
        repository.update_run(claimed.run_id, ConnectorSyncRunUpdate(status="completed"))
        logger.info(
            "Connector sync run completed run=%s connector=%s pulled=%s accepted=%s quarantined=%s",
            claimed.run_id,
            connector.connector_id,
            counters.pulled,
            counters.accepted,
            counters.quarantined,
        )
    else:
        event_bus.publish(
            ConnectorPageQueuedEvent(
                correlation_id=event.correlation_id,
                knowledge_base_id=connector.knowledge_base_id,
                connector_id=connector.connector_id,
                run_id=claimed.run_id,
                cursor=page.next_cursor,
            )
        )
    return 1


def _register_rows(
    *,
    records_service: RecordsServiceProtocol,
    connector: ConnectorDefinition,
    run: ConnectorSyncRun,
    rows: list[dict[str, object]],
    correlation_id: str,
) -> RecordIngestReceipt | None:
    """Hand the page's rows to the records service, or ``None`` for an empty page."""

    if not rows:
        return None
    return records_service.register_records(
        connector.knowledge_base_id,
        RecordSubmission(
            feed_name=connector.mapping.feed_name,
            rows=rows,
            # A pull is a system putting rows into a feed, not a user upload.
            # RecordSubmission has no `connector_pull` member and adding one
            # would ripple into the domain-pack config schema, so provenance
            # rides on source_ref instead.
            source_type="api_push",
            source_ref=f"connector:{connector.connector_id}:run:{run.run_id}",
        ),
        correlation_id=correlation_id,
    )


def _resolve_feed(
    records_config: RecordsConfig | None, feed_name: str
) -> RecordFeedConfig | None:
    if records_config is None:
        return None
    for feed in records_config.feeds:
        if feed.name == feed_name:
            return feed
    return None


def _partition_by_derivable_id(
    feed: RecordFeedConfig, rows: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[tuple[int, str]]]:
    """Split rows into those with a derivable record id and those without.

    Returns ``(ingestible, unidentifiable)`` where each unidentifiable entry is
    its ``(index, reason)`` so the quarantine row can name both.
    """

    ingestible: list[dict[str, object]] = []
    unidentifiable: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        try:
            derive_record_id(feed, row)
        except RecordValidationError as exc:
            unidentifiable.append((index, str(exc)))
        else:
            ingestible.append(row)
    return ingestible, unidentifiable


def _quarantine_rows(
    repository: ConnectorRepositoryProtocol,
    connector: ConnectorDefinition,
    run: ConnectorSyncRun,
    *,
    unidentifiable: list[tuple[int, str]],
    receipt: RecordIngestReceipt | None,
) -> None:
    """Record why each unusable row was not ingested.

    The counters say how many rows were quarantined; these rows say which ones
    and why, which is the difference between an operator being able to fix the
    feed and being told a number.

    A row is quarantined precisely because it may be malformed, so its own id
    field cannot be trusted as an identifier — the row's position in the page
    is what lets an operator find it in the source file.
    """

    rejected: list[tuple[int, str]] = list(unidentifiable)
    if receipt is not None:
        rejected.extend((row.index, row.reason) for row in receipt.rejected)
    for index, reason in rejected:
        repository.add_quarantine_record(
            ConnectorQuarantineRecordCreate(
                run_id=run.run_id,
                connector_id=connector.connector_id,
                knowledge_base_id=connector.knowledge_base_id,
                source_record_id=f"row-{index}",
                reason=reason,
            )
        )


def _fail_run(
    repository: ConnectorRepositoryProtocol,
    run: ConnectorSyncRun,
    reason: str,
) -> int:
    """Terminate a run that cannot succeed on any retry.

    Raising instead would burn the retry budget and dead-letter the event while
    leaving the run stuck in `running` with no recorded cause.
    """

    logger.error("Failing connector sync run run=%s reason=%s", run.run_id, reason)
    repository.update_run(
        run.run_id,
        ConnectorSyncRunUpdate(status="failed", error_message=reason),
    )
    return 0


register_handler("connector.page.queued", handle_connector_page_queued)


# `_PAGE_LIMIT` is read once at import. Tests that need a different page size
# should drive it through the source adapter's own limit handling rather than
# reassigning this, so behaviour under test matches behaviour in the worker.
