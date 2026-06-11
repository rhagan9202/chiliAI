"""Shared fixtures for API router tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.protocols import WorkflowRunStoreProtocol
from agent.models import WorkflowRunStatus, WorkflowRunUpdate


@pytest.fixture
def complete_inflight_workflows() -> Callable[[TestClient], None]:
    """Return a callable that drives in-flight workflow runs to COMPLETED.

    Ingestion endpoints now start a tracked workflow run synchronously, so the
    KB is busy (``ensure_kb_idle``) until the worker finishes the run. Tests
    that exercise a *second* KB mutation without a running worker use this to
    simulate the worker completing the pipeline so the KB becomes idle again.
    """

    def _complete(client: TestClient) -> None:
        app = cast(FastAPI, client.app)
        store = getattr(app.state, "workflow_run_store", None)
        if not isinstance(store, WorkflowRunStoreProtocol):
            return
        for run in store.list_runs():
            if run.status in (WorkflowRunStatus.QUEUED, WorkflowRunStatus.RUNNING):
                store.update_run(
                    run.workflow_id,
                    WorkflowRunUpdate(status=WorkflowRunStatus.COMPLETED),
                )

    return _complete
