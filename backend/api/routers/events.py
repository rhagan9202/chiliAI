"""Realtime events router exposing workspace snapshots over Server-Sent Events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from api.state import ApiState
from api.dependencies import get_api_state
from api.middleware.rbac import require_role

__all__ = ["router"]

router = APIRouter(prefix="/events", tags=["events"])


async def _stream_workspace_updates(
    request: Request,
    state: ApiState,
    max_events: int | None,
) -> AsyncIterator[str]:
    sequence = 0
    while True:
        if await request.is_disconnected():
            break
        if max_events is not None and sequence >= max_events:
            break

        snapshot = state.get_realtime_snapshot(sequence)
        yield f"event: workspace-update\ndata: {snapshot.model_dump_json()}\n\n"
        sequence += 1
        await asyncio.sleep(5)


@router.get("/stream", dependencies=[Depends(require_role("viewer"))])
async def stream_workspace_updates(
    request: Request,
    max_events: int | None = Query(default=None, ge=1),
    state: ApiState = Depends(get_api_state),
) -> StreamingResponse:
    """Stream workspace update events for alerts, workflows, and KB status changes."""
    return StreamingResponse(
        _stream_workspace_updates(request, state, max_events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )