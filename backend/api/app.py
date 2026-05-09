"""FastAPI application factory for the chiliAI backend API gateway."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.alerts import router as alerts_router
from api.routers.analytics import router as analytics_router
from api.routers.cases import router as cases_router
from api.routers.config import router as config_router
from api.routers.evidence import router as evidence_router
from api.routers.events import router as events_router
from api.routers.graph import router as graph_router
from api.routers.knowledgebases import router as knowledgebases_router
from api.routers.policy import router as policy_router
from api.routers.rag import router as rag_router
from api.routers.workflows import router as workflows_router

__all__ = ["create_app"]


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


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="chiliAI API",
        version="0.1.0",
        description="Backend API gateway for the chiliAI Graph RAG analytics platform.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_load_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        # TODO(production): Check actual subsystem health (event bus connectivity,
        # object store accessibility, graph DB connection). Return degraded status
        # with details when subsystems are unhealthy. Add /readiness endpoint for
        # Kubernetes probes. See docs/architecture.md §12.
        return {"status": "ok"}

    app.include_router(config_router)
    app.include_router(knowledgebases_router)
    app.include_router(events_router)
    app.include_router(alerts_router)
    app.include_router(graph_router)
    app.include_router(evidence_router)
    app.include_router(cases_router)
    app.include_router(rag_router)
    app.include_router(workflows_router)
    app.include_router(analytics_router)
    app.include_router(policy_router)

    # TODO(production): Add middleware: request logging/tracing, rate limiting, auth (JWT/OIDC),
    # global error handler, request correlation ID, API versioning (/v1/).
    # See docs/architecture.md §7 for API gateway requirements.

    return app
