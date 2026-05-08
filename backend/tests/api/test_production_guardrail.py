"""Production startup guardrails."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config.loader import load_config
from config.schema import AuthConfig


def _set_dev_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")


def test_create_app_refuses_when_production_and_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_ENV", "production")
    _set_dev_redis(monkeypatch)
    # Default config has auth.enabled=False
    from api.app import create_app

    with pytest.raises(RuntimeError, match="AuthConfig.enabled must be True"):
        create_app()


def test_create_app_refuses_when_production_and_oidc_fields_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_ENV", "production")
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    base = load_config()
    incomplete = base.model_copy(
        update={"auth": AuthConfig(enabled=True, issuer_url="https://idp.example.com")}
    )
    monkeypatch.setattr("api.app.load_config", lambda: incomplete)

    with pytest.raises(RuntimeError, match="AuthConfig is missing"):
        create_app()


def test_create_app_succeeds_under_dev_with_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHILI_ENV", raising=False)
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    app = create_app()
    assert app is not None


def test_create_app_invokes_policy_audit_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When auth is enabled, the default-deny audit must run after router registration."""

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.delenv("CHILI_ENV", raising=False)

    from api.app import create_app
    from config.schema import AuthConfig

    base = load_config()
    enabled = base.model_copy(
        update={
            "auth": AuthConfig(
                enabled=True,
                issuer_url="https://idp.example.com",
                audience="chili-api",
                jwks_uri="https://idp.example.com/jwks",
                client_id="chili-spa",
                client_secret_env_var="OIDC_CLIENT_SECRET",
                authorize_endpoint="https://idp.example.com/authorize",
                token_endpoint="https://idp.example.com/oauth/token",
                redirect_uri="https://app.example.com/auth/callback",
            )
        }
    )
    monkeypatch.setattr("api.app.load_config", lambda: enabled)

    # Patch assert_complete to a no-op so the audit doesn't actually fire on
    # currently-unprotected routes (Tasks 15-22 attach policies; until then,
    # assert_complete would raise).
    with patch("api.app.assert_complete") as mocked_assert:
        app = create_app()
        assert app is not None
        mocked_assert.assert_called_once()
        # The audit was called with the FastAPI app
        called_app = mocked_assert.call_args[0][0]
        assert called_app is app
