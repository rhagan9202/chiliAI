"""Shared ingestion telemetry: Prometheus counters and the stage-log helper (BL-043).

Counters are registered on the default ``prometheus_client`` registry. There is
no cross-process aggregation: each process serves its own ``/metrics`` endpoint
(the API gateway via ``api/middleware/metrics.py``, the pipeline worker via the
health server in ``agent/health.py``) and reports only the increments that
happened in that process.

``ingestion_documents_failed_total`` must be incremented adjacent to every
``DocumentsFailedEvent`` publish (the event payload carries neither ``stage``
nor ``error_class``, so counting at consumption cannot label correctly).
Emission points today: ``ingestion/service.py`` (parse failures) and four
sites in ``agent/coordinator.py`` (the missing-storage-key and
get_bytes/parse-failure branches of ``handle_documents_parsed`` and
``handle_documents_chunked``); new emission points add one
``.labels(...).inc()`` line each.

Counters are per-attempt increments, not per-document: under at-least-once
event delivery a retried/redelivered document can increment the same counter
more than once for what is ultimately a single logical failure, so these
counters over-count relative to distinct-document failure totals.
"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, Literal

from prometheus_client import Counter

from shared.logging import get_logger

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

__all__ = [
    "StageOutcome",
    "ingestion_dedup_suppressed_total",
    "ingestion_documents_empty_extraction_total",
    "ingestion_documents_failed_total",
    "log_stage",
]

StageOutcome = Literal["success", "failed", "empty"]

ingestion_documents_failed_total: Counter = Counter(
    "ingestion_documents_failed_total",
    "Documents that emitted a documents.failed event, by stage and error class.",
    ["stage", "error_class"],
)

ingestion_documents_empty_extraction_total: Counter = Counter(
    "ingestion_documents_empty_extraction_total",
    "Documents whose extraction validated to zero entities.",
)

ingestion_dedup_suppressed_total: Counter = Counter(
    "ingestion_dedup_suppressed_total",
    "Ingestion submissions suppressed by idempotent deduplication "
    "(kind=document: re-uploaded source document; kind=record_batch: "
    "identical structured-records batch).",
    ["kind"],
)

_stage_logger: BoundLogger = get_logger("chili.ingestion.stage")


def log_stage(
    *,
    stage: str,
    kb_id: str,
    source_document_id: str,
    started_at: float,
    outcome: StageOutcome,
) -> None:
    """Emit the BL-043 structured per-document stage log line.

    ``started_at`` is a ``time.perf_counter()`` value captured when the stage
    began; duration is computed here so call sites stay one line.
    """

    duration_ms = (perf_counter() - started_at) * 1000.0
    _stage_logger.info(
        "ingestion_stage",
        stage=stage,
        source_document_id=source_document_id,
        kb_id=kb_id,
        duration_ms=round(duration_ms, 3),
        outcome=outcome,
    )
