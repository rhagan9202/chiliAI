"""FastAPI application factory for the chiliAI backend API gateway."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.alerts import router as alerts_router
from api.routers.analytics import router as analytics_router
from api.routers.cases import router as cases_router
from api.routers.config import router as config_router
from api.routers.evidence import router as evidence_router
from api.routers.graph import router as graph_router
from api.routers.knowledgebases import router as knowledgebases_router
from api.routers.rag import router as rag_router
from api.routers.workflows import router as workflows_router

__all__ = ["create_app"]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="chiliAI API",
        version="0.1.0",
        description="Backend API gateway for the chiliAI Graph RAG analytics platform.",
    )

    app.add_middleware(
        CORSMiddleware,
        # TODO(production): Read allowed origins from config or ALLOWED_ORIGINS env var.
        # Current origins are hardcoded for local dev only.
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:80",
            "http://localhost",
        ],
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
    app.include_router(alerts_router)
    app.include_router(graph_router)
    app.include_router(evidence_router)
    app.include_router(cases_router)
    app.include_router(rag_router)
    app.include_router(workflows_router)
    app.include_router(analytics_router)

    # TODO(production): Add missing routers required by the frontend:
    # - Extend routers with write operations once backing services exist:
    #   POST /cases, PATCH /cases/{id}, POST /cases/{id}/feedback,
    #   POST /chat/conversations, POST /chat/conversations/{id}/messages,
    #   GET /graph/entities/{id}/relationships, DELETE /workflows/{id}
    # Add middleware: request logging/tracing, rate limiting, auth (JWT/OIDC),
    # global error handler, request correlation ID, API versioning (/v1/).
    # See docs/architecture.md §7 for API gateway requirements.

    return app
