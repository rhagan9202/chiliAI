"""Tests for the shared ingestion telemetry counters and stage-log helper (BL-043)."""

from __future__ import annotations

import logging
from time import perf_counter

import pytest
from prometheus_client import REGISTRY

from shared.metrics import (
    ingestion_dedup_suppressed_total,
    ingestion_documents_empty_extraction_total,
    ingestion_documents_failed_total,
    log_stage,
)


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    value = REGISTRY.get_sample_value(name, labels or {})
    return value if value is not None else 0.0


def _has_field(text: str, key: str, value: str) -> bool:
    """Match a structured field under either renderer: console (key=value) or JSON."""
    return f"{key}={value}" in text or f'"{key}": "{value}"' in text


class TestCounters:
    def test_failed_counter_labels_stage_and_error_class(self) -> None:
        labels = {"stage": "parse", "error_class": "ValueError"}
        before = _sample("ingestion_documents_failed_total", labels)
        ingestion_documents_failed_total.labels(
            stage="parse", error_class="ValueError"
        ).inc()
        assert _sample("ingestion_documents_failed_total", labels) == before + 1.0

    def test_empty_extraction_counter_increments(self) -> None:
        before = _sample("ingestion_documents_empty_extraction_total")
        ingestion_documents_empty_extraction_total.inc()
        assert _sample("ingestion_documents_empty_extraction_total") == before + 1.0

    def test_dedup_counter_labels_kind(self) -> None:
        labels = {"kind": "document"}
        before = _sample("ingestion_dedup_suppressed_total", labels)
        ingestion_dedup_suppressed_total.labels(kind="document").inc()
        assert _sample("ingestion_dedup_suppressed_total", labels) == before + 1.0


class TestLogStage:
    def test_emits_all_bl043_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
            log_stage(
                stage="parse",
                kb_id="kb-1",
                source_document_id="doc-1",
                started_at=perf_counter(),
                outcome="success",
            )
        assert _has_field(caplog.text, "stage", "parse")
        assert _has_field(caplog.text, "kb_id", "kb-1")
        assert _has_field(caplog.text, "source_document_id", "doc-1")
        assert _has_field(caplog.text, "outcome", "success")
        assert "duration_ms" in caplog.text

    def test_failed_outcome_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="chili.ingestion.stage"):
            log_stage(
                stage="chunk",
                kb_id="kb-2",
                source_document_id="doc-2",
                started_at=perf_counter(),
                outcome="failed",
            )
        assert _has_field(caplog.text, "outcome", "failed")
        assert _has_field(caplog.text, "stage", "chunk")
