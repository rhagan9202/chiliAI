"""Realtime events router exposing workspace snapshots over Server-Sent Events.

Also hosts the ``/events/dlq`` operator surface (BL-023): list/inspect
dead-lettered events and replay/discard them once an operator has
investigated the failure.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from agent.protocols import AgentServiceProtocol
from api._workflow_projection import count_running_workflows
from api.contracts import RealtimeSnapshotResponse
from api.dependencies import (
    get_agent_service,
    get_alert_feed_store,
    get_dlq_record_store,
    get_event_bus,
    get_knowledge_base_repository,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from events.codec import decode_event
from events.dlq_models import DlqRecord, DlqRecordListResponse, DlqRecordStatus
from events.protocols import DlqRecordStore, EventBus
from knowledgebases.protocols import KnowledgeBaseRepository
from monitoring.adapters.protocols import AlertFeedStoreProtocol
from shared.alerts import ACTIVE_ALERT_STATUSES
from shared.utils import utc_now

__all__ = ["router"]

router = APIRouter(prefix="/events", tags=["events"])
_SNAPSHOT_PAGE_SIZE = 500


async def _stream_workspace_updates(
    request: Request,
    alert_store: AlertFeedStoreProtocol,
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
            alert_store,
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
    alert_store: AlertFeedStoreProtocol = Depends(get_alert_feed_store),
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
            alert_store,
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


def _count_active_alerts(alert_store: AlertFeedStoreProtocol) -> int:
    """Return the number of active alerts for realtime workspace snapshots."""
    return alert_store.count_by_statuses(ACTIVE_ALERT_STATUSES)


def _build_realtime_snapshot(
    sequence: int,
    alert_store: AlertFeedStoreProtocol,
    agent_service: AgentServiceProtocol,
    repository: KnowledgeBaseRepository,
    user: User,
) -> RealtimeSnapshotResponse:
    cached_statuses = _list_accessible_knowledge_base_statuses(repository, user)
    running_workflows = _count_accessible_running_workflows(agent_service, user)
    return RealtimeSnapshotResponse(
        sequence=sequence,
        emitted_at=utc_now(),
        active_alerts=_count_active_alerts(alert_store),
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


@router.get(
    "/dlq",
    response_model=DlqRecordListResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def list_dlq_records(
    status_filter: DlqRecordStatus | None = Query(default=None, alias="status"),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: DlqRecordStore = Depends(get_dlq_record_store),
) -> DlqRecordListResponse:
    """List dead-lettered events, newest first, with optional filters."""
    items, total = store.list(
        status=status_filter,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return DlqRecordListResponse(items=items, total=total)


@router.get(
    "/dlq/{dlq_id}",
    response_model=DlqRecord,
    dependencies=[Depends(require_role("analyst"))],
)
async def get_dlq_record(
    dlq_id: str,
    store: DlqRecordStore = Depends(get_dlq_record_store),
) -> DlqRecord:
    """Return a single DLQ record, or 404 when unknown."""
    record = store.get(dlq_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DLQ record '{dlq_id}' not found.",
        )
    return record


@router.post(
    "/dlq/{dlq_id}/replay",
    response_model=DlqRecord,
    dependencies=[Depends(require_role("admin"))],
)
async def replay_dlq_record(
    dlq_id: str,
    store: DlqRecordStore = Depends(get_dlq_record_store),
    event_bus: EventBus = Depends(get_event_bus),
) -> DlqRecord:
    """Re-publish a pending DLQ record's original event and mark it replayed.

    404 for an unknown id, 409 when the record is not pending, 422 when the
    stored payload no longer decodes against the current event registry (the
    record is left ``pending`` so an operator can discard or retry later).
    """
    record = store.get(dlq_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DLQ record '{dlq_id}' not found.",
        )
    if record.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"DLQ record '{dlq_id}' is '{record.status}', not pending.",
        )
    try:
        event = decode_event(record.payload)
    except Exception as exc:  # noqa: BLE001 - codec drift surfaces as 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Stored payload no longer decodes: {exc}",
        ) from exc
    event_bus.publish(event)
    updated = store.mark_replayed(dlq_id)
    if updated is None:  # raced with another operator between get and CAS
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"DLQ record '{dlq_id}' was transitioned concurrently.",
        )
    return updated


@router.post(
    "/dlq/{dlq_id}/discard",
    response_model=DlqRecord,
    dependencies=[Depends(require_role("admin"))],
)
async def discard_dlq_record(
    dlq_id: str,
    store: DlqRecordStore = Depends(get_dlq_record_store),
) -> DlqRecord:
    """Mark a pending DLQ record discarded. 404 unknown, 409 non-pending."""
    updated = store.mark_discarded(dlq_id)
    if updated is not None:
        return updated
    if store.get(dlq_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DLQ record '{dlq_id}' not found.",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"DLQ record '{dlq_id}' is not pending.",
    )
