"""OpenTelemetry tracing setup for API and worker entry points (E10-S14).

The OpenTelemetry libraries live in the optional ``[observability]`` extra,
so all imports are deferred until :func:`setup_tracing` is called. When
the libraries are not installed the helper degrades to a no-op without
raising.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from opentelemetry.sdk.trace import TracerProvider

__all__ = [
    "get_tracer",
    "instrument_fastapi_app",
    "setup_tracing",
    "start_pipeline_span",
]


# Mutable container avoids reassigning a module-level uppercase name.
_STATE: dict[str, object] = {"provider": None}


def setup_tracing(
    otlp_endpoint: str | None = None,
    *,
    service_name: str = "chiliai",
) -> object | None:
    """Configure a global ``TracerProvider`` and return it (or ``None`` on miss)."""

    if _STATE["provider"] is not None:
        return _STATE["provider"]

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
            SpanExporter,
        )
    except ImportError:  # pragma: no cover - optional extra
        return None

    resource = Resource.create({"service.name": service_name})
    provider: TracerProvider = TracerProvider(resource=resource)

    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    exporter: SpanExporter
    use_batch = True
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError:  # pragma: no cover - optional extra
            exporter = ConsoleSpanExporter()
            use_batch = False
        else:
            exporter = OTLPSpanExporter(endpoint=endpoint)
    else:
        exporter = ConsoleSpanExporter()
        use_batch = False

    provider.add_span_processor(
        BatchSpanProcessor(exporter) if use_batch else SimpleSpanProcessor(exporter)
    )
    trace.set_tracer_provider(provider)
    _STATE["provider"] = provider
    return provider


def instrument_fastapi_app(app: object) -> bool:
    """Attach OpenTelemetry FastAPI instrumentation if available."""

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - optional extra
        return False
    FastAPIInstrumentor.instrument_app(app)  # pyright: ignore[reportUnknownMemberType,reportArgumentType]
    return True


def get_tracer(name: str) -> object | None:
    """Return a tracer for ``name`` or ``None`` if OpenTelemetry is unavailable."""

    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover
        return None
    return trace.get_tracer(name)


@contextmanager
def start_pipeline_span(
    name: str,
    *,
    correlation_id: str | None = None,
    attributes: dict[str, str | int | float | bool] | None = None,
) -> Generator[object | None, None, None]:
    """Start a span as a child of the current context and yield it.

    Yields ``None`` when OpenTelemetry is unavailable so callers do not need
    a try/except around the optional dependency.
    """

    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover
        yield None
        return

    tracer = trace.get_tracer("chili.pipeline")
    with tracer.start_as_current_span(name) as span:  # type: ignore[union-attr]
        if correlation_id is not None:
            span.set_attribute("correlation_id", correlation_id)  # type: ignore[union-attr]
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)  # type: ignore[union-attr]
        yield span
