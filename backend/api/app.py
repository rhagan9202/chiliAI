"""FastAPI application factory for the chiliAI backend API gateway."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.metrics import register_metrics
from api.routers.alerts import router as alerts_router
from api.routers.analytics import router as analytics_router
from api.routers.chat import router as chat_router
from api.routers.config import router as config_router
from api.routers.investigation import router as investigation_router
from api.routers.knowledgebases import router as knowledgebases_router
from api.routers.ws import router as ws_router
from shared.logging import configure_logging, get_logger
from shared.tracing import instrument_fastapi_app, setup_tracing

__all__ = ["create_app"]

logger = get_logger("chili.api")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    configure_logging()
    setup_tracing()

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

    register_metrics(app)
    instrument_fastapi_app(app)

    @app.get("/health")
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    # REST routers
    app.include_router(config_router)
    app.include_router(knowledgebases_router)
    app.include_router(alerts_router)
    app.include_router(investigation_router)
    app.include_router(chat_router)
    app.include_router(analytics_router)

    # WebSocket router (registered after REST routers per E5-S14 conventions)
    app.include_router(ws_router)

    logger.info("api_app_initialized", version=app.version)
    return app
