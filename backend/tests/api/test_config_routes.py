"""Tests for the config pack-management routes (E4).

Covers: GET /config/packs, POST /config/validate|apply|switch happy paths,
structured field-level validation errors, RBAC denial per route, the
validate-only non-mutation proof, never-persist-broken-pack rollback,
path-traversal rejection, and event/degradation surfacing.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from api import dependencies
from api.app import create_app
from api.dependencies import get_domain_config
from api.middleware.auth import User, get_current_user
from api.routers.config import PACK_DIRS_ENV_VAR
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from config.store import read_active_pack, resolve_state_path
from events.types import ConfigUpdatedEvent
from rag.protocols import RagServiceProtocol

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"
FOOD_YAML = DEFAULTS_DIR / "food_supply_chain.yaml"


@pytest.fixture(autouse=True)
def isolate_config_caches() -> Iterator[None]:
    """Reset all config-derived singletons around every test in this module."""
    dependencies.reset_domain_config_caches()
    yield
    dependencies.reset_domain_config_caches()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


class _RecordingBus:
    """Minimal publish-recording stand-in for the event bus."""

    def __init__(self, label: str = "") -> None:
        self.label = label
        self.events: list[object] = []

    def publish(self, event: object) -> str | None:
        self.events.append(event)
        return None

    def ensure_consumer_group(
        self, event_types: list[str], *, consumer_group: str
    ) -> None:
        del event_types, consumer_group


# ---------------------------------------------------------------------------
# GET /config/packs
# ---------------------------------------------------------------------------


class TestListPacks:
    def test_lists_default_packs_with_env_active(self, client: TestClient) -> None:
        resp = client.get("/config/packs")
        assert resp.status_code == 200
        data = resp.json()

        names = {pack["name"] for pack in data["packs"]}
        assert {"medicare_fraud", "food_supply_chain"} <= names

        assert data["active"]["source"] == "env"
        assert data["active"]["config_path"] == str(MEDICARE_YAML.resolve())
        assert isinstance(data["generation"], int)

        medicare = next(p for p in data["packs"] if p["name"] == "medicare_fraud")
        assert medicare["active"] is True
        assert medicare["valid"] is True
        assert medicare["domain_name"] == "medicare_fraud"
        assert medicare["display_name"] == "Medicare Fraud Detection"
        assert medicare["error"] is None

        food = next(p for p in data["packs"] if p["name"] == "food_supply_chain")
        assert food["active"] is False
        assert food["valid"] is True

    def test_pointer_becomes_active_source_after_switch(self, client: TestClient) -> None:
        switch = client.post("/config/switch", json={"pack": "food_supply_chain"})
        assert switch.status_code == 200

        data = client.get("/config/packs").json()
        assert data["active"]["source"] == "pointer"
        assert data["active"]["pack_name"] == "food_supply_chain"
        assert data["active"]["updated_at"] is not None
        food = next(p for p in data["packs"] if p["name"] == "food_supply_chain")
        assert food["active"] is True

    def test_broken_pack_in_extra_dir_listed_as_invalid(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "broken.yaml").write_text("domain: {name: broken}\n", encoding="utf-8")
        monkeypatch.setenv(PACK_DIRS_ENV_VAR, str(tmp_path))

        data = client.get("/config/packs").json()
        broken = next(p for p in data["packs"] if p["name"] == "broken")
        assert broken["valid"] is False
        assert broken["error"]
        assert broken["domain_name"] is None
        assert broken["active"] is False


# ---------------------------------------------------------------------------
# POST /config/validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_valid_pack_by_name(self, client: TestClient) -> None:
        resp = client.post("/config/validate", json={"pack": "food_supply_chain"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["pack_name"] == "food_supply_chain"
        assert data["display_name"]
        assert data["errors"] == []

    def test_valid_pack_by_path(self, client: TestClient) -> None:
        resp = client.post("/config/validate", json={"pack": str(FOOD_YAML)})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_invalid_inline_content_returns_field_level_errors(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/config/validate", json={"content": {"domain": {"name": "x"}}}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["pack_name"] is None
        assert data["errors"]
        for issue in data["errors"]:
            assert issue["message"]
            assert issue["error_type"]
            assert isinstance(issue["loc"], list)
        fields = {issue["field"] for issue in data["errors"]}
        assert "domain.display_name" in fields
        assert "entities" in fields

    def test_unparseable_pack_file_reports_parse_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        garbage = tmp_path / "garbage.yaml"
        garbage.write_text("{{ not: yaml: [", encoding="utf-8")
        monkeypatch.setenv(PACK_DIRS_ENV_VAR, str(tmp_path))

        resp = client.post("/config/validate", json={"pack": "garbage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["errors"][0]["error_type"] == "parse_error"

    def test_requires_exactly_one_of_pack_or_content(self, client: TestClient) -> None:
        neither = client.post("/config/validate", json={})
        both = client.post(
            "/config/validate",
            json={"pack": "medicare_fraud", "content": {"domain": {}}},
        )
        assert neither.status_code == 422
        assert both.status_code == 422

    def test_validate_never_mutates_anything(self, client: TestClient) -> None:
        """Zero-mutation proof: pointer, generation, and config identity survive."""
        assert client.get("/config/domain").json()["domain"]["name"] == "medicare_fraud"
        config_before = dependencies.get_domain_config()
        generation_before = dependencies.get_config_generation()
        assert read_active_pack() is None
        assert not resolve_state_path().exists()

        assert client.post(
            "/config/validate", json={"pack": "food_supply_chain"}
        ).json()["valid"]
        assert not client.post(
            "/config/validate", json={"content": {"domain": {"name": "x"}}}
        ).json()["valid"]

        assert read_active_pack() is None
        assert not resolve_state_path().exists()
        assert dependencies.get_config_generation() == generation_before
        assert dependencies.get_domain_config() is config_before
        assert client.get("/config/domain").json()["domain"]["name"] == "medicare_fraud"


# ---------------------------------------------------------------------------
# POST /config/validate?with_overlays
# ---------------------------------------------------------------------------


class TestValidateOverlays:
    def test_validate_with_overlays_applies_env_overlay(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Overlay flips a knob (display_name) that keeps the config valid but
        # is observable in the response — proving the overlay was applied.
        good_overlay = tmp_path / "good.yaml"
        good_overlay.write_text(
            "overlay_for: medicare_fraud\n"
            "domain:\n"
            "  display_name: Medicare Fraud Detection (Overlay)\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(good_overlay))

        resp = client.post(
            "/config/validate",
            json={"pack": "medicare_fraud"},
            params={"with_overlays": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["pack_name"] == "medicare_fraud"
        assert data["display_name"] == "Medicare Fraud Detection (Overlay)"
        assert data["errors"] == []

        # An overlay with an unknown top-level key raises OverlayError, which
        # must be wrapped into a valid=False response, not a raised exception.
        bad_overlay = tmp_path / "bad.yaml"
        bad_overlay.write_text(
            "overlay_for: medicare_fraud\nnot_a_real_section: true\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(bad_overlay))

        resp2 = client.post(
            "/config/validate",
            json={"pack": "medicare_fraud"},
            params={"with_overlays": "true"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["valid"] is False
        assert data2["pack_name"] is None
        assert len(data2["errors"]) == 1
        assert data2["errors"][0]["error_type"] == "overlay_error"
        assert "unknown top-level keys" in data2["errors"][0]["message"]

    def test_validate_without_overlays_ignores_env(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Same env var set as the "bad" overlay above — if it were applied,
        # this would come back valid=False with an overlay_error. Omitting
        # with_overlays must ignore it entirely (pack-only verdict).
        bad_overlay = tmp_path / "bad.yaml"
        bad_overlay.write_text(
            "overlay_for: medicare_fraud\nnot_a_real_section: true\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(bad_overlay))

        resp = client.post("/config/validate", json={"pack": "medicare_fraud"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["pack_name"] == "medicare_fraud"
        assert data["errors"] == []

    def test_validate_with_overlays_rejects_inline_content(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/config/validate",
            json={"content": {"domain": {"name": "x"}}},
            params={"with_overlays": "true"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /config/apply and /config/switch
# ---------------------------------------------------------------------------


class TestApplyAndSwitch:
    def test_switch_activates_pack_and_emits_event(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bus = _RecordingBus()
        monkeypatch.setattr(dependencies, "get_event_bus", lambda: bus)

        resp = client.post("/config/switch", json={"pack": "food_supply_chain"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "applied"
        assert data["reason"] == "switch"
        assert data["pack_name"] == "food_supply_chain"
        assert data["pack_path"] == str(FOOD_YAML.resolve())
        assert data["previous_pack_name"] == "medicare_fraud"
        assert data["generation"] >= 1
        assert data["event_published"] is True
        assert isinstance(data["rag_degraded_to_fallback"], bool)

        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.pack_name == "food_supply_chain"

        # The running app now serves the new domain.
        assert client.get("/config/domain").json()["domain"]["name"] == "food_supply_chain"

        events = [e for e in bus.events if isinstance(e, ConfigUpdatedEvent)]
        assert len(events) == 1
        event = events[0]
        assert event.pack_name == "food_supply_chain"
        assert event.pack_path == str(FOOD_YAML.resolve())
        assert event.previous_pack_name == "medicare_fraud"
        assert event.reason == "switch"
        assert event.source == "api.config"

    def test_apply_without_pack_reapplies_active(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bus = _RecordingBus()
        monkeypatch.setattr(dependencies, "get_event_bus", lambda: bus)
        generation_before = dependencies.get_config_generation()

        resp = client.post("/config/apply", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["reason"] == "apply"
        assert data["pack_name"] == "medicare_fraud"
        assert data["generation"] == generation_before + 1
        assert data["rag_degraded_to_fallback"] is False

        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.pack_name == "medicare_fraud"

        events = [e for e in bus.events if isinstance(e, ConfigUpdatedEvent)]
        assert len(events) == 1
        assert events[0].reason == "apply"

    def test_apply_with_explicit_pack_path(self, client: TestClient) -> None:
        resp = client.post("/config/apply", json={"pack": str(FOOD_YAML)})
        assert resp.status_code == 200
        assert resp.json()["pack_name"] == "food_supply_chain"
        assert resp.json()["reason"] == "apply"

    def test_apply_without_active_pack_is_rejected(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CHILI_CONFIG_PATH")
        resp = client.post("/config/apply", json={})
        assert resp.status_code == 400
        assert "No active pack" in resp.json()["detail"]

    def test_switch_to_unknown_pack_returns_404(self, client: TestClient) -> None:
        resp = client.post("/config/switch", json={"pack": "does_not_exist"})
        assert resp.status_code == 404

    def test_never_persists_a_broken_pack(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Swap-once-success rollback: an invalid pack mutates nothing."""
        broken = tmp_path / "broken.yaml"
        broken.write_text("domain: {name: broken}\n", encoding="utf-8")
        monkeypatch.setenv(PACK_DIRS_ENV_VAR, str(tmp_path))

        assert client.get("/config/domain").json()["domain"]["name"] == "medicare_fraud"
        config_before = dependencies.get_domain_config()
        generation_before = dependencies.get_config_generation()

        for route in ("/config/apply", "/config/switch"):
            resp = client.post(route, json={"pack": "broken"})
            assert resp.status_code == 400, route
            assert "active configuration unchanged" in resp.json()["detail"]

        assert read_active_pack() is None
        assert not resolve_state_path().exists()
        assert dependencies.get_config_generation() == generation_before
        assert dependencies.get_domain_config() is config_before
        assert client.get("/config/domain").json()["domain"]["name"] == "medicare_fraud"

    def test_swap_succeeds_even_when_event_publish_fails(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_bus() -> object:
            raise RuntimeError("no event transport")

        monkeypatch.setattr(dependencies, "get_event_bus", broken_bus)

        resp = client.post("/config/switch", json={"pack": "food_supply_chain"})
        assert resp.status_code == 200
        assert resp.json()["event_published"] is False
        assert client.get("/config/domain").json()["domain"]["name"] == "food_supply_chain"

    def test_rag_degradation_is_surfaced(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_rag_service() -> RagServiceProtocol:
            raise RuntimeError("composition failed")

        monkeypatch.setattr(dependencies, "get_rag_service", broken_rag_service)

        resp = client.post("/config/apply", json={})
        assert resp.status_code == 200
        assert resp.json()["rag_degraded_to_fallback"] is True

    def test_reload_signal_published_on_pre_swap_transport(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """M3: config.updated must ride the OLD pack's event transport.

        The worker is still consuming on pre-swap settings, so the bus must
        be resolved before the cache reset. Each bus resolution is labeled
        with the domain config visible at resolution time; the reload signal
        must land on a bus resolved while the old pack was still cached.
        """
        buses: list[_RecordingBus] = []

        def capturing_get_event_bus() -> _RecordingBus:
            bus = _RecordingBus(label=dependencies.get_domain_config().domain.name)
            buses.append(bus)
            return bus

        monkeypatch.setattr(dependencies, "get_event_bus", capturing_get_event_bus)

        resp = client.post("/config/switch", json={"pack": "food_supply_chain"})
        assert resp.status_code == 200
        assert resp.json()["event_published"] is True

        carrying = [
            bus
            for bus in buses
            if any(isinstance(event, ConfigUpdatedEvent) for event in bus.events)
        ]
        assert len(carrying) == 1
        assert carrying[0].label == "medicare_fraud"


# ---------------------------------------------------------------------------
# Production auth guardrail on hot-swap
# ---------------------------------------------------------------------------


class TestProductionGuardrail:
    def test_authless_pack_rejected_under_production_with_nothing_mutated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """C1: one POST must never disable auth platform-wide in production."""
        assert client.get("/config/domain").json()["domain"]["name"] == "medicare_fraud"
        config_before = dependencies.get_domain_config()
        generation_before = dependencies.get_config_generation()

        monkeypatch.setenv("CHILI_ENV", "production")
        for route in ("/config/switch", "/config/apply"):
            resp = client.post(route, json={"pack": "food_supply_chain"})
            assert resp.status_code == 400, route
            detail = resp.json()["detail"]
            assert "guardrail" in detail
            assert "active configuration unchanged" in detail

        assert read_active_pack() is None
        assert not resolve_state_path().exists()
        assert dependencies.get_config_generation() == generation_before
        assert dependencies.get_domain_config() is config_before
        assert client.get("/config/domain").json()["domain"]["name"] == "medicare_fraud"

    def test_non_production_env_still_swaps(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILI_ENV", "dev")
        resp = client.post("/config/switch", json={"pack": "food_supply_chain"})
        assert resp.status_code == 200
        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.pack_name == "food_supply_chain"

    def test_production_swap_allowed_for_fully_authed_pack(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        secured = load_config(MEDICARE_YAML).model_copy(
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
        pack = tmp_path / "secured.yaml"
        pack.write_text(
            yaml.safe_dump(secured.model_dump(mode="json")), encoding="utf-8"
        )
        monkeypatch.setenv(PACK_DIRS_ENV_VAR, str(tmp_path))
        monkeypatch.setenv("CHILI_ENV", "production")

        resp = client.post("/config/switch", json={"pack": "secured"})
        assert resp.status_code == 200
        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.pack_name == "medicare_fraud"


# ---------------------------------------------------------------------------
# Path-traversal rejection
# ---------------------------------------------------------------------------


class TestPathTraversal:
    @pytest.mark.parametrize(
        "reference",
        [
            "../../../etc/passwd",
            "/etc/passwd",
            "../../../../tmp/evil.yaml",
            "food_supply_chain/../../../etc/passwd",
            "..",
            "   ",
        ],
    )
    def test_traversal_references_rejected_on_switch(
        self, client: TestClient, reference: str
    ) -> None:
        resp = client.post("/config/switch", json={"pack": reference})
        assert resp.status_code == 400
        assert read_active_pack() is None

    def test_traversal_references_rejected_on_validate_and_apply(
        self, client: TestClient
    ) -> None:
        assert (
            client.post("/config/validate", json={"pack": "../../.env"}).status_code
            == 400
        )
        assert (
            client.post("/config/apply", json={"pack": "/etc/passwd"}).status_code
            == 400
        )
        assert read_active_pack() is None

    def test_symlink_escaping_allowed_dir_is_not_resolvable(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.yaml"
        secret.write_text("domain: {}\n", encoding="utf-8")
        packs = tmp_path / "packs"
        packs.mkdir()
        (packs / "evil.yaml").symlink_to(secret)
        monkeypatch.setenv(PACK_DIRS_ENV_VAR, str(packs))

        resp = client.post("/config/switch", json={"pack": "evil"})
        assert resp.status_code == 404
        assert read_active_pack() is None


# ---------------------------------------------------------------------------
# RBAC: all pack-management routes are admin-only
# ---------------------------------------------------------------------------


def _auth_enabled_config() -> DomainConfig:
    base = load_config(MEDICARE_YAML)
    return base.model_copy(update={"auth": AuthConfig(enabled=True)})


def _client_with_user(roles: list[str]) -> TestClient:
    app = create_app()
    config = _auth_enabled_config()
    app.dependency_overrides[get_domain_config] = lambda: config
    app.dependency_overrides[get_current_user] = lambda: User(user_id="u", roles=roles)
    return TestClient(app)


class TestRbac:
    @pytest.mark.parametrize("roles", [["viewer"], ["analyst"]])
    def test_non_admin_denied_on_every_pack_route(self, roles: list[str]) -> None:
        client = _client_with_user(roles)
        assert client.get("/config/packs").status_code == 403
        assert (
            client.post(
                "/config/validate", json={"pack": "medicare_fraud"}
            ).status_code
            == 403
        )
        assert client.post("/config/apply", json={}).status_code == 403
        assert (
            client.post(
                "/config/switch", json={"pack": "food_supply_chain"}
            ).status_code
            == 403
        )

    def test_admin_allowed(self) -> None:
        client = _client_with_user(["admin"])
        assert client.get("/config/packs").status_code == 200
        resp = client.post("/config/validate", json={"pack": "medicare_fraud"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
