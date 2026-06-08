"""Tests for the worker health-check HTTP server."""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import closing

from agent.health import HealthState, build_health_payload, start_health_server
from agent.models import HealthSettings


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _http_get(host: str, port: int, path: str) -> tuple[int, bytes]:
    reader, writer = await asyncio.open_connection(host, port)
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    writer.write(request)
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    status_line, _, rest = response.partition(b"\r\n")
    _, _, body = rest.partition(b"\r\n\r\n")
    parts = status_line.decode("ascii").split(" ", 2)
    status_code = int(parts[1]) if len(parts) >= 2 else 0
    return status_code, body


async def _exercise_health_server() -> None:
    port = _free_port()
    settings = HealthSettings(host="127.0.0.1", port=port)
    state = HealthState(settings=settings)

    server = await start_health_server(state)
    try:
        status_code, body = await _http_get("127.0.0.1", port, "/health")
        assert status_code == 200
        payload = json.loads(body)
        assert payload["status"] == "ok"
        assert payload["last_event_processed_at"] is None

        # Hit an unknown path to cover the 404 branch.
        status_404, _ = await _http_get("127.0.0.1", port, "/missing")
        assert status_404 == 404

        # POST is rejected with 405.
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            b"POST /health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n"
        )
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
        assert b"405 Method Not Allowed" in response
    finally:
        server.close()
        await server.wait_closed()


def test_health_server_responds_to_get_health() -> None:
    asyncio.run(_exercise_health_server())


def test_build_health_payload_returns_iso_timestamp_when_event_processed() -> None:
    state = HealthState(settings=HealthSettings())
    state.mark_event_processed()
    payload = build_health_payload(state)
    assert payload["status"] == "ok"
    assert isinstance(payload["last_event_processed_at"], str)
    assert payload["events_processed"] == 1
    assert payload["events_dead_lettered"] == 0


def test_status_degraded_when_only_dead_lettering() -> None:
    # A worker that has received events but dead-lettered all of them has made
    # no real progress and must NOT report healthy.
    state = HealthState(settings=HealthSettings())
    assert state.status() == "ok"  # fresh + idle is genuinely ok
    state.mark_event_dead_lettered()
    state.mark_event_dead_lettered()
    assert state.status() == "degraded"
    payload = build_health_payload(state)
    assert payload["status"] == "degraded"
    assert payload["events_dead_lettered"] == 2
    assert payload["events_processed"] == 0


def test_status_ok_when_some_events_succeed_despite_dead_letters() -> None:
    state = HealthState(settings=HealthSettings())
    state.mark_event_processed()
    state.mark_event_dead_lettered()
    # Some genuine progress → not degraded on the dead-letter signal alone.
    assert state.status() == "ok"


def test_status_degraded_after_consecutive_drain_errors() -> None:
    state = HealthState(settings=HealthSettings(degraded_after_drain_errors=3))
    state.record_drain_error(RuntimeError("redis down"))
    state.record_drain_error(RuntimeError("redis down"))
    assert state.status() == "ok"  # below threshold
    state.record_drain_error(RuntimeError("redis down"))
    assert state.status() == "degraded"
    payload = build_health_payload(state)
    assert payload["consecutive_drain_errors"] == 3
    assert payload["last_drain_error"] == "redis down"
    # A successful drain (or processed event) clears the streak.
    state.record_drain_success()
    assert state.status() == "ok"
    assert state.consecutive_drain_errors == 0


def test_mark_event_processed_clears_drain_error_streak() -> None:
    state = HealthState(settings=HealthSettings(degraded_after_drain_errors=2))
    state.record_drain_error(RuntimeError("blip"))
    state.record_drain_error(RuntimeError("blip"))
    assert state.status() == "degraded"
    state.mark_event_processed()
    assert state.status() == "ok"
