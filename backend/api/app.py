"""FastAPI application factory for the chiliAI backend API gateway."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.metrics import register_metrics
from api.middleware.policy_registry import assert_complete
from api.state import create_api_state
from api.routers.alerts import router as alerts_router
from api.routers.analytics import router as analytics_router
from api.routers.auth import router as auth_router
from api.routers.cases import router as cases_router
from api.routers.config import router as config_router
from api.routers.evidence import router as evidence_router
from api.routers.events import router as events_router
from api.routers.graph import router as graph_router
from api.routers.investigation import router as investigation_router
from api.routers.knowledgebases import router as knowledgebases_router
from api.routers.policy import router as policy_router
from api.routers.rag import router as rag_router
from api.routers.records import router as records_router
from api.routers.workflows import router as workflows_router
from api.routers.ws import router as ws_router
from config.loader import load_config
from config.schema import AuthConfig
from shared.logging import configure_logging, get_logger
from shared.tracing import instrument_fastapi_app, setup_tracing

__all__ = ["create_app"]

logger = get_logger("chili.api")

_ALLOWED_ENVIRONMENTS = frozenset({"local", "dev", "staging", "production"})
_AUTH_REQUIRED_ENVIRONMENTS = frozenset({"staging", "production"})


def _load_chili_environment() -> str:
    """Return the validated runtime environment name."""

    raw_environment = os.environ.get("CHILI_ENV")
    if raw_environment is None or raw_environment.strip() == "":
        allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
        raise RuntimeError(
            "CHILI_ENV must be set to one of "
            f"{allowed}; use CHILI_ENV=local for local development."
        )

    environment = raw_environment.strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
        raise RuntimeError(
            f"Unknown CHILI_ENV '{raw_environment}'. Expected one of {allowed}."
        )
    return environment


def _enforce_production_guardrail(auth: AuthConfig | None) -> None:
    environment = _load_chili_environment()
    if environment not in _AUTH_REQUIRED_ENVIRONMENTS:
        return
    if auth is None or not auth.enabled:
        raise RuntimeError(
            "AuthConfig.enabled must be True under "
            f"CHILI_ENV={environment}."
        )
    required = (
        ("issuer_url", auth.issuer_url),
        ("audience", auth.audience),
        ("jwks_uri", auth.jwks_uri),
        ("client_id", auth.client_id),
        ("client_secret_env_var", auth.client_secret_env_var),
        ("authorize_endpoint", auth.authorize_endpoint),
        ("token_endpoint", auth.token_endpoint),
        ("redirect_uri", auth.redirect_uri),
    )
    missing = [name for name, value in required if value is None]
    if missing:
        raise RuntimeError(
            "AuthConfig is missing required fields under "
            f"CHILI_ENV={environment}: {missing}"
        )


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

    configure_logging()
    setup_tracing()

    # Reset process-level config cache so each create_app() call (e.g. one
    # per test) reloads from CHILI_CONFIG_PATH / monkeypatched load_config.
    from api.dependencies import get_domain_config
    get_domain_config.cache_clear()

    config = load_config()
    _enforce_production_guardrail(config.auth)

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

    # Per-app seeded state — see api.dependencies.get_api_state. Each
    # create_app() call yields a fresh ApiState so tests are isolated.
    app.state.api_state = create_api_state()

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
    app.include_router(cases_router)
    app.include_router(rag_router)
    app.include_router(records_router)
    app.include_router(workflows_router)
    app.include_router(analytics_router)
    app.include_router(policy_router)
    app.include_router(investigation_router)
    app.include_router(auth_router)
    app.include_router(ws_router)

    # Default-deny audit validates route annotations independent of runtime auth
    # mode. Individual require_role dependencies still short-circuit when auth is
    # disabled for local/dev operation.
    assert_complete(app)

    logger.info("api_app_initialized", version=app.version)
    return app
