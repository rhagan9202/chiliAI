"""Tests for the Air Force housing API router."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.housing import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_overview_returns_safe_empty_executive_kpi_model() -> None:
    response = _client().get(
        "/housing/overview",
        params={"period_start": "2026-06-01", "period_end": "2026-06-30"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "portfolio_summary": {
            "total_installations": 0,
            "installations_reporting": 0,
            "open_work_orders": 0,
            "overdue_work_orders": 0,
            "occupancy_rate": None,
            "resident_satisfaction": None,
        },
        "executive_kpis": [],
    }


def test_overview_accepts_missing_period_params() -> None:
    response = _client().get("/housing/overview")

    assert response.status_code == 200
    assert response.json()["period_start"] is None
    assert response.json()["period_end"] is None
    assert response.json()["executive_kpis"] == []


def test_installations_returns_safe_empty_map_and_list_model() -> None:
    response = _client().get(
        "/housing/installations",
        params={"period_start": "2026-06-01", "period_end": "2026-06-30"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "total": 0,
        "items": [],
        "map_points": [],
    }


def test_installations_accepts_missing_period_params() -> None:
    response = _client().get("/housing/installations")

    assert response.status_code == 200
    assert response.json()["period_start"] is None
    assert response.json()["period_end"] is None
    assert response.json()["items"] == []
    assert response.json()["map_points"] == []
