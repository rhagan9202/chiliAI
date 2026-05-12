"""Production startup guardrails."""

from __future__ import annotations

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


def test_create_app_refuses_when_environment_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHILI_ENV", raising=False)
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    with pytest.raises(RuntimeError, match="CHILI_ENV must be set"):
        create_app()


def test_create_app_refuses_when_environment_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_ENV", "prodution")
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    with pytest.raises(RuntimeError, match="Unknown CHILI_ENV"):
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


def test_create_app_succeeds_under_local_with_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_ENV", "local")
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    app = create_app()
    assert app is not None


def test_create_app_succeeds_under_dev_with_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_ENV", "dev")
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    app = create_app()
    assert app is not None


def test_create_app_refuses_when_staging_and_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_ENV", "staging")
    _set_dev_redis(monkeypatch)
    from api.app import create_app

    with pytest.raises(RuntimeError, match="AuthConfig.enabled must be True"):
        create_app()


def test_create_app_passes_policy_registry_assert_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With auth enabled and every router protected, create_app succeeds."""
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setenv("CHILI_ENV", "local")

    from api.app import create_app
    from config.loader import load_config
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

    app = create_app()
    assert app is not None
