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

    @property
    def settings(self) -> HealthSettings:
        return self._settings

    @property
    def last_event_processed_at(self) -> datetime | None:
        return self._last_event_processed_at

    def mark_event_processed(self, when: datetime | None = None) -> None:
        """Record the timestamp of the last successfully processed event."""

        self._last_event_processed_at = when if when is not None else utc_now()

    def status(self, *, now: datetime | None = None) -> str:
        """Return ``"ok"`` while events flow, otherwise ``"degraded"``."""

        if self._last_event_processed_at is None:
            return "ok"
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
