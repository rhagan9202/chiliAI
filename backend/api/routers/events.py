"""Realtime events router exposing workspace snapshots over Server-Sent Events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from agent.protocols import AgentServiceProtocol
from api._alert_store import AlertProjectionRepository, count_active_alerts
from api._workflow_projection import count_running_workflows
from api.contracts import RealtimeSnapshotResponse
from api.dependencies import (
    get_agent_service,
    get_alert_repository,
    get_knowledge_base_repository,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.utils import utc_now

__all__ = ["router"]

router = APIRouter(prefix="/events", tags=["events"])
_SNAPSHOT_PAGE_SIZE = 500


async def _stream_workspace_updates(
    request: Request,
    alert_repository: AlertProjectionRepository,
    agent_service: AgentServiceProtocol,
    repository: KnowledgeBaseRepository,
    user: User,
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
            user,
        )
        yield f"event: workspace-update\ndata: {snapshot.model_dump_json()}\n\n"
        sequence += 1
        await asyncio.sleep(5)


@router.get("/stream")
async def stream_workspace_updates(
    request: Request,
    max_events: int | None = Query(default=None, ge=1),
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    agent_service: AgentServiceProtocol = Depends(get_agent_service),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    user: User = Depends(require_role("viewer")),
) -> StreamingResponse:
    """Stream lightweight workspace updates for alerts, workflows, and KB status.

    The heartbeat intentionally reads cached KB metadata only. Live graph/object
    store reconciliation remains on explicit KB list/detail reads so an idle
    browser tab cannot repeatedly query Neo4j every five seconds.
    """
    return StreamingResponse(
        _stream_workspace_updates(
            request,
            alert_repository,
            agent_service,
            repository,
            user,
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
    user: User,
) -> RealtimeSnapshotResponse:
    cached_statuses = _list_accessible_knowledge_base_statuses(repository, user)
    running_workflows = _count_accessible_running_workflows(agent_service, user)
    return RealtimeSnapshotResponse(
        sequence=sequence,
        emitted_at=utc_now(),
        active_alerts=count_active_alerts(alert_repository),
        running_workflows=running_workflows,
        knowledge_base_statuses=cached_statuses,
    )


def _can_access_knowledge_base(user: User, knowledge_base_id: str) -> bool:
    allowed = getattr(user, "knowledge_base_ids", None)
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


def _list_accessible_knowledge_base_statuses(
    repository: KnowledgeBaseRepository,
    user: User,
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    offset = 0

    while True:
        knowledge_bases, total = repository.list(
            limit=_SNAPSHOT_PAGE_SIZE,
            offset=offset,
        )
        for knowledge_base in knowledge_bases:
            if _can_access_knowledge_base(user, knowledge_base.id):
                statuses[knowledge_base.id] = knowledge_base.status
        if (
            not knowledge_bases
            or offset + len(knowledge_bases) >= total
            or len(knowledge_bases) < _SNAPSHOT_PAGE_SIZE
        ):
            break
        next_offset = offset + len(knowledge_bases)
        if next_offset <= offset:
            break
        offset = next_offset

    return statuses


def _count_accessible_running_workflows(
    agent_service: AgentServiceProtocol,
    user: User,
) -> int:
    running_workflows = 0
    offset = 0

    while True:
        page = agent_service.list_workflows(
            limit=_SNAPSHOT_PAGE_SIZE,
            offset=offset,
        )
        accessible_runs = [
            run
            for run in page.items
            if _can_access_knowledge_base(user, run.knowledge_base_id)
        ]
        running_workflows += count_running_workflows(accessible_runs)
        if not page.has_more:
            break
        if (
            not page.items
            or page.next_offset is None
            or page.next_offset <= offset
        ):
            break
        offset = page.next_offset

    return running_workflows
