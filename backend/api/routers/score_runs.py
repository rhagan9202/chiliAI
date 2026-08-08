"""Score-all run API endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from analytics.score_runs.models import ScoreBatch, ScoreRun
from analytics.score_runs.service import ScoreRunConflictError, ScoreRunService
from api.contracts import (
    ScoreBatchResponse,
    ScoreBatchStatusValue,
    ScoreRunDetailResponse,
    ScoreRunListResponse,
    ScoreRunReplayRequest,
    ScoreRunResponse,
    ScoreRunStartRequest,
    ScoreRunStatusValue,
)
from api.dependencies import (
    get_graph_repository,
    get_knowledge_base_repository,
    get_score_run_service,
)
from api.middleware.auth import User
from api.middleware.rbac import require_role
from graph.adapters.protocols import GraphRepository
from knowledgebases.protocols import KnowledgeBaseRepository

__all__ = ["router"]

router = APIRouter(
    prefix="/knowledgebases/{knowledge_base_id}/score-runs",
    tags=["score-runs"],
)


def _can_access_knowledge_base(user: User, knowledge_base_id: str) -> bool:
    allowed = user.knowledge_base_ids
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles


def _require_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository,
    user: User,
) -> None:
    if not _can_access_knowledge_base(user, knowledge_base_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )
    if repository.get(knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )


def _require_run_for_kb(
    service: ScoreRunService,
    *,
    knowledge_base_id: str,
    run_id: str,
) -> ScoreRun:
    try:
        run = service.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Score run '{run_id}' was not found.",
        ) from exc
    if run.knowledge_base_id != knowledge_base_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Score run '{run_id}' was not found.",
        )
    return run


@router.post(
    "",
    response_model=ScoreRunDetailResponse,
)
def start_score_run(
    knowledge_base_id: str,
    payload: ScoreRunStartRequest,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_repository: GraphRepository = Depends(get_graph_repository),
    service: ScoreRunService = Depends(get_score_run_service),
    user: User = Depends(require_role("analyst")),
) -> ScoreRunDetailResponse:
    """Start or return an idempotent KB-scoped score-all run."""
    _require_knowledge_base(knowledge_base_id, repository, user)
    # entity_ids=None passes straight through: the executor enumerates. This
    # route used to list every entity in the KB synchronously, which is risk R2
    # and failed inside the HTTP request on a large KB.
    del graph_repository
    try:
        result = service.start_score_all(
            knowledge_base_id=knowledge_base_id,
            entity_ids=payload.entity_ids,
            requested_by=payload.requested_by or user.user_id,
            model_version=payload.model_version,
            catalog_version=payload.catalog_version,
            idempotency_key=payload.idempotency_key,
            batch_size=payload.batch_size,
        )
    except ScoreRunConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _detail_response(result.run, result.batches, created=result.created)


@router.get(
    "",
    response_model=ScoreRunListResponse,
)
def list_score_runs(
    knowledge_base_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: ScoreRunService = Depends(get_score_run_service),
    user: User = Depends(require_role("viewer")),
) -> ScoreRunListResponse:
    """Return recent score-all runs for a knowledge base."""
    _require_knowledge_base(knowledge_base_id, repository, user)
    page = service.list_runs(
        knowledge_base_id=knowledge_base_id,
        limit=limit,
        offset=offset,
    )
    return ScoreRunListResponse(
        items=[_run_response(run) for run in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{run_id}",
    response_model=ScoreRunDetailResponse,
)
def get_score_run(
    knowledge_base_id: str,
    run_id: str = Path(...),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: ScoreRunService = Depends(get_score_run_service),
    user: User = Depends(require_role("viewer")),
) -> ScoreRunDetailResponse:
    """Return one score-all run plus current batch state."""
    _require_knowledge_base(knowledge_base_id, repository, user)
    run = _require_run_for_kb(service, knowledge_base_id=knowledge_base_id, run_id=run_id)
    return _detail_response(run, service.list_batches(run_id=run.id), created=False)


@router.post(
    "/{run_id}/cancel",
    response_model=ScoreRunDetailResponse,
)
def cancel_score_run(
    knowledge_base_id: str,
    run_id: str = Path(...),
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: ScoreRunService = Depends(get_score_run_service),
    user: User = Depends(require_role("analyst")),
) -> ScoreRunDetailResponse:
    """Request cooperative cancellation of a queued or running score-all run."""
    _require_knowledge_base(knowledge_base_id, repository, user)
    _require_run_for_kb(service, knowledge_base_id=knowledge_base_id, run_id=run_id)
    try:
        run = service.cancel_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _detail_response(run, service.list_batches(run_id=run.id), created=False)


@router.post(
    "/{run_id}/replay",
    response_model=ScoreRunDetailResponse,
)
def replay_score_run(
    knowledge_base_id: str,
    run_id: str,
    payload: ScoreRunReplayRequest,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    service: ScoreRunService = Depends(get_score_run_service),
    user: User = Depends(require_role("analyst")),
) -> ScoreRunDetailResponse:
    """Create or return a replay run for failed score batches."""
    _require_knowledge_base(knowledge_base_id, repository, user)
    _require_run_for_kb(service, knowledge_base_id=knowledge_base_id, run_id=run_id)
    try:
        result = service.replay_failed_batches(
            run_id,
            requested_by=payload.requested_by or user.user_id,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _detail_response(result.run, result.batches, created=result.created)


def _detail_response(
    run: ScoreRun,
    batches: list[ScoreBatch],
    *,
    created: bool,
) -> ScoreRunDetailResponse:
    return ScoreRunDetailResponse(
        run=_run_response(run),
        batches=[_batch_response(batch) for batch in batches],
        created=created,
    )


def _run_response(run: ScoreRun) -> ScoreRunResponse:
    return ScoreRunResponse(
        id=run.id,
        knowledge_base_id=run.knowledge_base_id,
        status=cast(ScoreRunStatusValue, run.status),
        requested_by=run.requested_by,
        idempotency_key=run.idempotency_key,
        model_version=run.model_version,
        catalog_version=run.catalog_version,
        replay_of_run_id=run.replay_of_run_id,
        total_entities=run.total_entities,
        scored_entities=run.scored_entities,
        failed_entities=run.failed_entities,
        skipped_entities=run.skipped_entities,
        error_summary=run.error_summary,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _batch_response(batch: ScoreBatch) -> ScoreBatchResponse:
    return ScoreBatchResponse(
        id=batch.id,
        run_id=batch.run_id,
        knowledge_base_id=batch.knowledge_base_id,
        batch_number=batch.batch_number,
        status=cast(ScoreBatchStatusValue, batch.status),
        entity_ids=list(batch.entity_ids),
        attempts=batch.attempts,
        error_summary=batch.error_summary,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
    )
