"""Tests for the config API router."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config
from config.loader import load_config
from config.schema import DomainConfig

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


@pytest.fixture()
def config() -> DomainConfig:
    return load_config(MEDICARE_YAML)


@pytest.fixture()
def client(config: DomainConfig) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_domain_config] = lambda: config
    return TestClient(app)


class TestConfigRouter:
    def test_get_domain_returns_200(self, client: TestClient) -> None:
        resp = client.get("/config/domain")
        assert resp.status_code == 200

    def test_response_contains_domain_info(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        assert data["domain"]["name"] == "medicare_fraud"
        assert data["domain"]["display_name"] == "Medicare Fraud Detection"

    def test_response_contains_entities(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        names = {e["name"] for e in data["entities"]}
        assert "provider" in names
        assert "claim" in names

    def test_response_contains_relationships(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        names = {r["name"] for r in data["relationships"]}
        assert "submitted_by" in names

    def test_response_contains_capabilities(self, client: TestClient) -> None:
        data = client.get("/config/domain").json()
        assert data["capabilities"]["timeseries"] is True
        assert data["capabilities"]["gnn"] is True

    def test_health_still_works(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
