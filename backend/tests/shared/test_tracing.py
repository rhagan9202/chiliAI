"""Tests for OpenTelemetry tracing helpers (E10-S14)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest

pytest.importorskip("opentelemetry.sdk.trace")
pytest.importorskip("opentelemetry.sdk.trace.export.in_memory_span_exporter")

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

import shared.tracing as tracing_module  # noqa: E402
from shared.tracing import get_tracer, start_pipeline_span  # noqa: E402


@pytest.fixture
def in_memory_provider() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "chili-test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # Force-replace any previously installed provider so tests are deterministic.
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
    trace._TRACER_PROVIDER = None  # pyright: ignore[reportPrivateUsage]
    trace.set_tracer_provider(provider)
    tracing_module._PROVIDER = provider  # pyright: ignore[reportPrivateUsage]
    try:
        yield exporter
    finally:
        exporter.clear()
        trace._TRACER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
        trace._TRACER_PROVIDER = None  # pyright: ignore[reportPrivateUsage]
        tracing_module._PROVIDER = None  # pyright: ignore[reportPrivateUsage]


class TestSpanCreation:
    def test_start_pipeline_span_emits_span(
        self, in_memory_provider: InMemorySpanExporter
    ) -> None:
        with start_pipeline_span("ingest.parse"):
            pass
        spans = in_memory_provider.get_finished_spans()
        assert spans, "Expected at least one span"
        names = [cast(ReadableSpan, span).name for span in spans]
        assert "ingest.parse" in names

    def test_span_records_correlation_id_attribute(
        self, in_memory_provider: InMemorySpanExporter
    ) -> None:
        with start_pipeline_span("graph.upsert", correlation_id="corr-1"):
            pass
        spans = in_memory_provider.get_finished_spans()
        target = next(
            cast(ReadableSpan, s)
            for s in spans
            if cast(ReadableSpan, s).name == "graph.upsert"
        )
        attributes = target.attributes or {}
        assert attributes.get("correlation_id") == "corr-1"

    def test_span_records_extra_attributes(
        self, in_memory_provider: InMemorySpanExporter
    ) -> None:
        with start_pipeline_span(
            "vector.upsert", attributes={"document_count": 3}
        ):
            pass
        spans = in_memory_provider.get_finished_spans()
        target = next(
            cast(ReadableSpan, s)
            for s in spans
            if cast(ReadableSpan, s).name == "vector.upsert"
        )
        attributes = target.attributes or {}
        assert attributes.get("document_count") == 3


class TestParentChildLinkage:
    def test_nested_spans_share_trace_and_link_parent(
        self, in_memory_provider: InMemorySpanExporter
    ) -> None:
        tracer = trace.get_tracer("chili.test.parent")
        with tracer.start_as_current_span("parent"):
            with start_pipeline_span("child"):
                pass

        spans = in_memory_provider.get_finished_spans()
        readable = [cast(ReadableSpan, s) for s in spans]
        by_name = {span.name: span for span in readable}
        assert "parent" in by_name
        assert "child" in by_name

        parent_span = by_name["parent"]
        child_span = by_name["child"]
        assert parent_span.context is not None
        assert child_span.context is not None
        assert parent_span.context.trace_id == child_span.context.trace_id
        assert child_span.parent is not None
        assert child_span.parent.span_id == parent_span.context.span_id


class TestGetTracer:
    def test_returns_tracer_object(self) -> None:
        tracer = get_tracer("chili.test.tracer")
        assert tracer is not None
