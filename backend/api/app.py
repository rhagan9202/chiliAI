"""FastAPI application factory for the chiliAI backend API gateway."""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from functools import partial
from types import FrameType

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import (
    build_api_state,
    enforce_production_guardrail,
    load_chili_environment,
    reset_domain_config_caches,
)
from api.middleware.auth import configure_jwks_cache
from api.middleware.metrics import register_metrics
from api.middleware.policy_registry import assert_complete
from api.routers.alerts import router as alerts_router
from api.routers.analytics import router as analytics_router
from api.routers.audit import router as audit_router
from api.routers.auth import router as auth_router
from api.routers.capabilities import router as capabilities_router
from api.routers.cases import router as cases_router
from api.routers.config import router as config_router
from api.routers.connectors import router as connectors_router
from api.routers.dev_seed import router as dev_seed_router
from api.routers.evidence import kb_router as evidence_kb_router
from api.routers.evidence import router as evidence_router
from api.routers.events import router as events_router
from api.routers.graph import router as graph_router
from api.routers.governance import router as governance_router
from api.routers.housing import router as housing_router
from api.routers.identity import router as identity_router
from api.routers.investigation import router as investigation_router
from api.routers.knowledgebases import router as knowledgebases_router
from api.routers.policy import router as policy_router
from api.routers.playbooks import router as playbooks_router
from api.routers.rag import router as rag_router
from api.routers.readiness import router as readiness_router
from api.routers.records import router as records_router
from api.routers.scorecards import router as scorecards_router
from api.routers.score_runs import router as score_runs_router
from api.routers.workflow_definitions import router as workflow_definitions_router
from api.routers.workflows import router as workflows_router
from config.loader import load_config
from config.store import read_active_pack
from shared.logging import configure_logging, get_logger
from shared.tracing import instrument_fastapi_app, setup_tracing

__all__ = ["create_app"]

logger = get_logger("chili.api")


def _load_allowed_origins() -> list[str]:
    """Return allowed CORS origins from env or local development defaults."""
    raw_origins = os.environ.get("ALLOWED_ORIGINS")
    if raw_origins is None:
        return [
            "http://localhost:5173",
            "http://localhost:80",
            "http://localhost",
        ]

    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:5173"]


# What `signal.getsignal` returns: our own callable, one of the SIG_* ints, or
# None. Spelled out rather than `Any`, which this codebase does not allow.
_SignalHandler = (
    Callable[[int, FrameType | None], object] | int | signal.Handlers | None
)


@asynccontextmanager
async def _signal_shutdown_to_long_lived_responses(
    app: FastAPI,
) -> AsyncGenerator[None]:
    """Tell streaming responses to finish *before* the server drains them.

    uvicorn's graceful shutdown waits for open connections and only then runs
    this lifespan's shutdown half. `/events/stream` holds a connection open
    indefinitely by design, so a signal-free implementation deadlocks: the
    drain waits on the stream, and the stream waits on a signal that the drain
    is blocking. Setting the event here on the way out is therefore too late —
    it has to happen when the signal arrives.

    So this hooks SIGTERM/SIGINT ahead of uvicorn's own handler and chains to
    it. `signal.signal` is main-thread-only and raises `ValueError` elsewhere
    (Starlette's TestClient runs the app in a worker thread), which is not an
    error: in-process there is no drain to unblock, and the shutdown half below
    still ends the stream.
    """

    event = _shutdown_event_for(app)
    loop = asyncio.get_running_loop()
    restore: list[tuple[int, _SignalHandler]] = []

    def _handle(
        signum: int, frame: FrameType | None, previous: _SignalHandler = None
    ) -> None:
        loop.call_soon_threadsafe(event.set)
        if callable(previous):
            previous(signum, frame)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            previous = signal.getsignal(sig)
            signal.signal(sig, partial(_handle, previous=previous))
        except ValueError:  # not the main thread
            break
        restore.append((sig, previous))

    try:
        yield
    finally:
        for sig, previous in restore:
            with suppress(ValueError):
                signal.signal(sig, previous)
        event.set()


def _shutdown_event_for(app: FastAPI) -> asyncio.Event:
    """The app's shutdown signal, created on demand."""

    event = getattr(app.state, "shutdown_event", None)
    if not isinstance(event, asyncio.Event):
        event = asyncio.Event()
        app.state.shutdown_event = event
    return event

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    configure_logging()
    setup_tracing()

    # Reset every config-derived singleton so each create_app() call (e.g. one
    # per test, or a fresh process after a domain swap) reloads from the
    # active-pack pointer / CHILI_CONFIG_PATH / monkeypatched load_config.
    reset_domain_config_caches()

    # Boot-validate the SAME config DI will serve: pointer > CHILI_CONFIG_PATH
    # (mirroring api.dependencies.get_domain_config), so a poisoned pointer
    # fails startup loudly and a pointer-only deployment (no CHILI_CONFIG_PATH)
    # boots. When no pointer exists, the zero-arg load_config() call preserves
    # the historical ``api.app.load_config`` monkeypatch seam used by tests.
    pointer = read_active_pack()
    config = load_config(pointer.config_path) if pointer is not None else load_config()
    enforce_production_guardrail(config.auth)
    configure_jwks_cache(config.auth)

    app = FastAPI(
        title="chiliAI API",
        version="0.1.0",
        description="Backend API gateway for the chiliAI Graph RAG analytics platform.",
        lifespan=_signal_shutdown_to_long_lived_responses,
    )

    # Created here rather than in the lifespan so it exists even when the
    # lifespan never runs — `TestClient(app)` outside a `with` block skips it,
    # and a route reading a missing attribute would fail at request time.
    app.state.shutdown_event = asyncio.Event()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_load_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Per-app seeded state — see api.dependencies.get_api_state. Each
    # create_app() call yields a fresh ApiState so tests are isolated.
    # build_api_state composes the live RAG service (BL-001) via DI so the
    # chat surfaces query real embeddings / vector store / graph / LLM
    # adapters, falling back to the seeded in-memory demo pipeline on
    # composition failure. Domain hot-swaps rebuild this via
    # api.dependencies.reset_domain_config_caches(app).
    app.state.api_state = build_api_state()

    register_metrics(app)
    instrument_fastapi_app(app)

    @app.get("/health")
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    # REST routers
    app.include_router(config_router)
    app.include_router(knowledgebases_router)
    app.include_router(events_router)
    app.include_router(alerts_router)
    app.include_router(graph_router)
    app.include_router(evidence_router)
    app.include_router(evidence_kb_router)
    app.include_router(cases_router)
    app.include_router(rag_router)
    app.include_router(records_router)
    app.include_router(workflows_router)
    app.include_router(analytics_router)
    app.include_router(audit_router)
    app.include_router(scorecards_router)
    app.include_router(score_runs_router)
    app.include_router(capabilities_router)
    app.include_router(workflow_definitions_router)
    app.include_router(playbooks_router)
    app.include_router(governance_router)
    app.include_router(connectors_router)
    app.include_router(readiness_router)
    app.include_router(housing_router)
    app.include_router(identity_router)
    app.include_router(policy_router)
    app.include_router(investigation_router)
    app.include_router(auth_router)

    # Dev/e2e-only seed endpoint — never registered in production.
    if load_chili_environment() != "production":
        app.include_router(dev_seed_router)

    # Default-deny audit validates route annotations independent of runtime auth
    # mode. Individual require_role dependencies still short-circuit when auth is
    # disabled for local/dev operation.
    assert_complete(app)

    logger.info("api_app_initialized", version=app.version)
    return app
