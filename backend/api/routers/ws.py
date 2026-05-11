"""WebSocket router for real-time alerts and pipeline progress events.

The router exposes two endpoints, ``/ws/alerts`` and ``/ws/pipeline``, that
forward in-process broadcast events to connected clients. The actual bridge
between the event bus (Redis Streams) and this hub is wired in Epic 8 — for
now the hub accepts direct ``broadcast`` calls so coordinator code (or tests)
can drive it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Final, cast

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from api.middleware.rbac import require_ws_role
from shared.utils import generate_id

__all__ = [
    "AlertSubscribeFilter",
    "PipelineSubscribeFilter",
    "WebSocketHub",
    "WebSocketConnection",
    "get_ws_hub",
    "router",
]


ROUTE_ALERTS: Final[str] = "alerts"
ROUTE_PIPELINE: Final[str] = "pipeline"
PING_INTERVAL_SECONDS: Final[float] = 30.0


class AlertSubscribeFilter(BaseModel):
    """Optional severity filter for alert subscribers."""

    severity: list[str] | None = Field(default=None)


class PipelineSubscribeFilter(BaseModel):
    """Per-knowledge-base scope filter for pipeline subscribers."""

    kb_id: str | None = Field(default=None)


class _AlertSubscribeMessage(BaseModel):
    subscribe: AlertSubscribeFilter


class _PipelineSubscribeMessage(BaseModel):
    subscribe: PipelineSubscribeFilter


@dataclass(slots=True)
class WebSocketConnection:
    """In-memory record of one connected WebSocket client."""

    id: str
    route: str
    websocket: WebSocket
    severity_filter: frozenset[str] | None = None
    kb_id_filter: str | None = None
    background_tasks: list[asyncio.Task[None]] = field(
        default_factory=lambda: cast(list[asyncio.Task[None]], [])
    )

    def matches_alert(self, severity: str) -> bool:
        if self.severity_filter is None:
            return True
        return severity in self.severity_filter

    def matches_kb(self, knowledge_base_id: str) -> bool:
        if self.kb_id_filter is None:
            return True
        return self.kb_id_filter == knowledge_base_id


class WebSocketHub:
    """Process-local registry of WebSocket connections for broadcasting.

    The hub is intentionally simple: a per-route list of connections plus a
    ``broadcast`` method that fans out a JSON payload to clients matching an
    optional filter predicate. It does not subscribe to Redis Streams — the
    event bus bridge is added in Epic 8.
    """

    def __init__(self) -> None:
        self._clients: dict[str, list[WebSocketConnection]] = {
            ROUTE_ALERTS: [],
            ROUTE_PIPELINE: [],
        }
        self._lock = asyncio.Lock()

    async def connect(self, route: str, websocket: WebSocket) -> WebSocketConnection:
        await websocket.accept()
        connection = WebSocketConnection(
            id=generate_id(),
            route=route,
            websocket=websocket,
        )
        async with self._lock:
            self._clients.setdefault(route, []).append(connection)
        return connection

    async def disconnect(self, connection: WebSocketConnection) -> None:
        async with self._lock:
            clients = self._clients.get(connection.route)
            if clients is not None and connection in clients:
                clients.remove(connection)
        for task in connection.background_tasks:
            task.cancel()

    async def broadcast(
        self,
        route: str,
        payload: dict[str, object],
        filter_fn: Callable[[WebSocketConnection], bool] | None = None,
    ) -> None:
        """Send ``payload`` as JSON to every matching connection on ``route``."""
        async with self._lock:
            targets = list(self._clients.get(route, []))

        for connection in targets:
            if filter_fn is not None and not filter_fn(connection):
                continue
            try:
                await connection.websocket.send_json(payload)
            except (WebSocketDisconnect, RuntimeError):
                await self.disconnect(connection)

    def connection_count(self, route: str) -> int:
        return len(self._clients.get(route, []))

    def connections(self, route: str) -> list[WebSocketConnection]:
        """Return a snapshot of connections on ``route`` (intended for tests)."""
        return list(self._clients.get(route, []))


@lru_cache(maxsize=1)
def get_ws_hub() -> WebSocketHub:
    """Return the process-wide WebSocket hub singleton."""
    return WebSocketHub()


router = APIRouter(prefix="/ws", tags=["websockets"])


async def _ping_loop(connection: WebSocketConnection) -> None:
    """Periodically send ping frames to keep the connection alive."""
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            await connection.websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        return


async def _alert_message_handler(
    connection: WebSocketConnection,
    raw_message: object,
) -> None:
    try:
        parsed = _AlertSubscribeMessage.model_validate(raw_message)
    except ValidationError:
        return
    severities = parsed.subscribe.severity
    connection.severity_filter = (
        frozenset(severities) if severities is not None else None
    )


async def _pipeline_message_handler(
    connection: WebSocketConnection,
    raw_message: object,
) -> None:
    try:
        parsed = _PipelineSubscribeMessage.model_validate(raw_message)
    except ValidationError:
        return
    connection.kb_id_filter = parsed.subscribe.kb_id


async def _serve_websocket(
    websocket: WebSocket,
    hub: WebSocketHub,
    route: str,
    on_message: Callable[[WebSocketConnection, object], Awaitable[None]],
) -> None:
    connection = await hub.connect(route, websocket)
    ping_task = asyncio.create_task(_ping_loop(connection))
    connection.background_tasks.append(ping_task)
    try:
        while True:
            raw_message = await websocket.receive_json()
            await on_message(connection, raw_message)
    except WebSocketDisconnect:
        return
    finally:
        await hub.disconnect(connection)


@router.websocket("/alerts", dependencies=[Depends(require_ws_role("viewer"))])
async def alerts_websocket(
    websocket: WebSocket,
    hub: WebSocketHub = Depends(get_ws_hub),
) -> None:
    """Accept alert WebSocket subscribers and broadcast ``AlertCreatedEvent`` payloads."""
    await _serve_websocket(websocket, hub, ROUTE_ALERTS, _alert_message_handler)


@router.websocket("/pipeline", dependencies=[Depends(require_ws_role("viewer"))])
async def pipeline_websocket(
    websocket: WebSocket,
    hub: WebSocketHub = Depends(get_ws_hub),
) -> None:
    """Accept pipeline WebSocket subscribers scoped by ``knowledge_base_id``."""
    await _serve_websocket(websocket, hub, ROUTE_PIPELINE, _pipeline_message_handler)
