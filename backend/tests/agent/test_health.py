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
