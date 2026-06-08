"""Lightweight async health-check HTTP server for the worker process."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from agent.models import HealthSettings
from shared.utils import utc_now

__all__ = [
    "HealthState",
    "build_health_payload",
    "start_health_server",
]

logger = logging.getLogger("chili.worker.health")


class HealthState:
    """Mutable health state shared between the worker loop and HTTP server."""

    def __init__(
        self,
        *,
        settings: HealthSettings,
        clock: type[datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._clock_factory: type[datetime] = clock if clock is not None else datetime
        self._last_event_processed_at: datetime | None = None
        self._events_processed: int = 0
        self._events_dead_lettered: int = 0
        self._consecutive_drain_errors: int = 0
        self._last_drain_error: str | None = None

    @property
    def settings(self) -> HealthSettings:
        return self._settings

    @property
    def last_event_processed_at(self) -> datetime | None:
        return self._last_event_processed_at

    @property
    def events_processed(self) -> int:
        return self._events_processed

    @property
    def events_dead_lettered(self) -> int:
        return self._events_dead_lettered

    @property
    def consecutive_drain_errors(self) -> int:
        return self._consecutive_drain_errors

    @property
    def last_drain_error(self) -> str | None:
        return self._last_drain_error

    def mark_event_processed(self, when: datetime | None = None) -> None:
        """Record a successfully processed event (NOT a dead-lettered one).

        Successful progress also clears the consecutive-drain-error counter: a
        worker making progress is, by definition, reading the stream.
        """

        self._events_processed += 1
        self._last_event_processed_at = when if when is not None else utc_now()
        self._consecutive_drain_errors = 0

    def mark_event_dead_lettered(self) -> None:
        """Record an event whose retries were exhausted and routed to the DLQ.

        Deliberately does NOT touch ``last_event_processed_at`` — a worker that
        only dead-letters has made no real progress and must not look healthy.
        """

        self._events_dead_lettered += 1

    def record_drain_error(self, error: BaseException) -> None:
        """Record a drain iteration that failed to read/process the stream."""

        self._consecutive_drain_errors += 1
        self._last_drain_error = str(error)

    def record_drain_success(self) -> None:
        """Record a drain iteration that completed (the read path is healthy)."""

        self._consecutive_drain_errors = 0
        self._last_drain_error = None

    def status(self, *, now: datetime | None = None) -> str:
        """Return ``"ok"`` only when the worker is genuinely healthy.

        Reports ``"degraded"`` when the worker cannot drain the stream
        (``>= degraded_after_drain_errors`` consecutive failures), when it has
        received events but dead-lettered all of them (no successful progress),
        or when it was processing and has since stalled past
        ``degraded_after_seconds``. A freshly-started, idle worker with no errors
        is genuinely ``"ok"``.
        """

        if self._consecutive_drain_errors >= self._settings.degraded_after_drain_errors:
            return "degraded"
        if self._events_dead_lettered > 0 and self._events_processed == 0:
            return "degraded"
        if self._last_event_processed_at is not None:
            current = now if now is not None else self._clock_factory.now(timezone.utc)
            elapsed = (current - self._last_event_processed_at).total_seconds()
            if elapsed > self._settings.degraded_after_seconds:
                return "degraded"
        return "ok"


def build_health_payload(state: HealthState, *, now: datetime | None = None) -> dict[str, object]:
    """Render the JSON body returned by ``GET /health``."""

    last_processed = state.last_event_processed_at
    payload: dict[str, object] = {
        "status": state.status(now=now),
        "last_event_processed_at": (
            last_processed.isoformat() if last_processed is not None else None
        ),
        "events_processed": state.events_processed,
        "events_dead_lettered": state.events_dead_lettered,
        "consecutive_drain_errors": state.consecutive_drain_errors,
        "last_drain_error": state.last_drain_error,
    }
    return payload


async def start_health_server(state: HealthState) -> asyncio.AbstractServer:
    """Start the asyncio TCP server that responds to ``GET /health``.

    The worker survives a health-server failure: callers wrap this coroutine in
    a ``try/except`` and log a warning instead of aborting startup.
    """

    server = await asyncio.start_server(
        lambda reader, writer: _handle_client(reader, writer, state),
        host=state.settings.host,
        port=state.settings.port,
    )
    return server


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: HealthState,
) -> None:
    """Serve a single HTTP request and close the connection."""

    try:
        request_line = await reader.readline()
        # Drain the rest of the request headers up to the blank line.
        while True:
            header_line = await reader.readline()
            if not header_line or header_line in (b"\r\n", b"\n"):
                break

        response_body, status_line = _route_request(request_line, state)
        body_bytes = response_body.encode("utf-8")
        response = (
            f"HTTP/1.1 {status_line}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii") + body_bytes
        writer.write(response)
        await writer.drain()
    except Exception:  # noqa: BLE001 - guard against transport-layer surprises
        logger.exception("Failed to serve health request")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 - close errors are non-fatal
            pass


def _route_request(request_line: bytes, state: HealthState) -> tuple[str, str]:
    """Return the response body and HTTP status line for a single request."""

    try:
        decoded_line = request_line.decode("ascii", errors="replace").strip()
    except UnicodeDecodeError:
        return _error_payload("Invalid request"), "400 Bad Request"

    parts = decoded_line.split(" ")
    if len(parts) < 2:
        return _error_payload("Invalid request"), "400 Bad Request"

    method, path = parts[0], parts[1]
    if method != "GET":
        return _error_payload("Method not allowed"), "405 Method Not Allowed"
    if path != "/health":
        return _error_payload("Not found"), "404 Not Found"

    payload = build_health_payload(state)
    return json.dumps(payload), "200 OK"


def _error_payload(message: str) -> str:
    return json.dumps({"error": message})
