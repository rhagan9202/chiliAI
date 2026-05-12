"""Realtime events router exposing workspace snapshots over Server-Sent Events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from api._alert_store import AlertProjectionRepository, count_active_alerts
from api._kb_projection import project_knowledge_base
from api._kb_store import KnowledgeBaseRepository
from api.contracts import RealtimeSnapshotResponse
from api.dependencies import (
    get_api_state,
    get_alert_repository,
    get_graph_service,
    get_knowledge_base_repository,
    get_object_store,
)
from api.middleware.rbac import require_role
from api.state import ApiState
from graph.protocols import GraphServiceProtocol
from storage.protocols import ObjectStore

__all__ = ["router"]

router = APIRouter(prefix="/events", tags=["events"])


async def _stream_workspace_updates(
    request: Request,
    state: ApiState,
    alert_repository: AlertProjectionRepository,
    repository: KnowledgeBaseRepository,
    graph_service: GraphServiceProtocol,
    object_store: ObjectStore,
    max_events: int | None,
) -> AsyncIterator[str]:
    sequence = 0
    while True:
        if await request.is_disconnected():
            break
        if max_events is not None and sequence >= max_events:
            break

        snapshot = _build_realtime_snapshot(
            sequence,
            state,
            alert_repository,
            repository,
            graph_service,
            object_store,
        )
        yield f"event: workspace-update\ndata: {snapshot.model_dump_json()}\n\n"
        sequence += 1
        await asyncio.sleep(5)


@router.get("/stream", dependencies=[Depends(require_role("viewer"))])
async def stream_workspace_updates(
    request: Request,
    max_events: int | None = Query(default=None, ge=1),
    state: ApiState = Depends(get_api_state),
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
) -> StreamingResponse:
    """Stream workspace update events for alerts, workflows, and KB status changes."""
    return StreamingResponse(
        _stream_workspace_updates(
            request,
            state,
            alert_repository,
            repository,
            graph_service,
            object_store,
            max_events,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _build_realtime_snapshot(
    sequence: int,
    state: ApiState,
    alert_repository: AlertProjectionRepository,
    repository: KnowledgeBaseRepository,
    graph_service: GraphServiceProtocol,
    object_store: ObjectStore,
) -> RealtimeSnapshotResponse:
    seeded_snapshot = state.get_realtime_snapshot(sequence)
    knowledge_bases, _ = repository.list(limit=500, offset=0)
    live_statuses = {
        knowledge_base.id: project_knowledge_base(
            knowledge_base,
            repository,
            graph_service,
            object_store,
        ).status
        for knowledge_base in knowledge_bases
    }
    return seeded_snapshot.model_copy(
        update={
            "active_alerts": count_active_alerts(alert_repository),
            "knowledge_base_statuses": live_statuses,
        }
    )
