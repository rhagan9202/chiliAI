"""Realtime events router exposing workspace snapshots over Server-Sent Events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from agent.protocols import AgentServiceProtocol
from agent.service_models import WorkflowRunStatus
from api._alert_store import AlertProjectionRepository, count_active_alerts
from api._kb_projection import project_knowledge_base
from api._kb_store import KnowledgeBaseRepository
from api._workflow_projection import count_running_workflows
from api.contracts import RealtimeSnapshotResponse
from api.dependencies import (
    get_agent_service,
    get_alert_repository,
    get_graph_service,
    get_knowledge_base_repository,
    get_object_store,
)
from api.middleware.rbac import require_role
from graph.protocols import GraphServiceProtocol
from shared.utils import utc_now
from storage.protocols import ObjectStore

__all__ = ["router"]

router = APIRouter(prefix="/events", tags=["events"])


async def _stream_workspace_updates(
    request: Request,
    alert_repository: AlertProjectionRepository,
    agent_service: AgentServiceProtocol,
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
            alert_repository,
            agent_service,
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
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    object_store: ObjectStore = Depends(get_object_store),
) -> StreamingResponse:
    """Stream workspace update events for alerts, workflows, and KB status changes."""
    return StreamingResponse(
        _stream_workspace_updates(
            request,
            alert_repository,
            agent_service,
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
    alert_repository: AlertProjectionRepository,
    agent_service: AgentServiceProtocol,
    repository: KnowledgeBaseRepository,
    graph_service: GraphServiceProtocol,
    object_store: ObjectStore,
) -> RealtimeSnapshotResponse:
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
    running_workflows = count_running_workflows(
        agent_service.list_workflows(
            status=WorkflowRunStatus.RUNNING,
            limit=500,
            offset=0,
        )
    )
    return RealtimeSnapshotResponse(
        sequence=sequence,
        emitted_at=utc_now(),
        active_alerts=count_active_alerts(alert_repository),
        running_workflows=running_workflows,
        knowledge_base_statuses=live_statuses,
    )
