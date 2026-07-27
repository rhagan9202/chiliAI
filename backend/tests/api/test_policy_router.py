"""Tests for the policy items + triage router (BL-011)."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from policy.adapters.in_memory import InMemoryPolicyItemRepository
from policy.models import PolicyItem, PolicyItemStatus
from shared.utils import generate_id, utc_now


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient over a fresh app with isolated per-app state."""
    return TestClient(create_app())


@pytest.fixture
def seed_policy_item(client: TestClient) -> Callable[..., str]:
    """Upsert one open policy item via the app's policy repository.

    Ensures the per-app repository exists (in-memory by default), mirroring how
    durable rows are seeded for the cases routes.
    """

    def _seed(
        *,
        kb: str = "kb-1",
        rule_id: str = "rule-1",
        target_ref: str = "claim-9",
        title: str = "Claim claim-9 exceeds billing threshold",
        status: str = "open",
    ) -> str:
        app = cast(FastAPI, client.app)
        repository = getattr(app.state, "policy_repository", None)
        if not isinstance(repository, InMemoryPolicyItemRepository):
            repository = InMemoryPolicyItemRepository()
            app.state.policy_repository = repository
        now = utc_now()
        item = PolicyItem(
            id=generate_id(),
            knowledge_base_id=kb,
            rule_id=rule_id,
            rule_pack_id="pack-1",
            target_kind="entity",
            target_ref=target_ref,
            title=title,
            severity="high",
            matched_fields={"properties.amount": 1200.0},
            citations=[],
            status=cast(PolicyItemStatus, status),
            created_at=now,
            updated_at=now,
        )
        stored = repository.upsert(item)
        return stored.id

    return _seed


def test_list_and_get_and_triage_items(
    client: TestClient, seed_policy_item: Callable[..., str]
) -> None:
    kb = "kb-1"
    item_id = seed_policy_item(kb=kb)

    listed = client.get(f"/policy/items?knowledge_base_id={kb}")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = client.get(f"/policy/items/{item_id}?knowledge_base_id={kb}")
    assert detail.status_code == 200
    assert detail.json()["item"]["status"] == "open"

    triaged = client.post(
        f"/policy/items/{item_id}/triage?knowledge_base_id={kb}",
        json={"action": "defer", "note": "later"},
    )
    assert triaged.status_code == 200
    assert triaged.json()["item"]["status"] == "deferred"

    # second triage on a disposed item -> 409
    again = client.post(
        f"/policy/items/{item_id}/triage?knowledge_base_id={kb}",
        json={"action": "accept"},
    )
    assert again.status_code == 409


def test_list_accepts_a_repeated_status_parameter(
    client: TestClient, seed_policy_item: Callable[..., str]
) -> None:
    """"Open OR escalated" has to be expressible in one request (UXA-401)."""
    kb = "kb-multi"
    seed_policy_item(kb=kb, rule_id="r-open", target_ref="claim-1", title="Upcoding")
    seed_policy_item(
        kb=kb, rule_id="r-esc", target_ref="claim-2", title="Unbundling", status="escalated"
    )
    seed_policy_item(
        kb=kb, rule_id="r-rej", target_ref="claim-3", title="Duplicate", status="rejected"
    )

    both = client.get(f"/policy/items?knowledge_base_id={kb}&status=open&status=escalated")

    assert both.status_code == 200
    body = both.json()
    assert body["total"] == 2
    assert {item["title"] for item in body["items"]} == {"Upcoding", "Unbundling"}

    # The pre-multi-select single-status form still works.
    single = client.get(f"/policy/items?knowledge_base_id={kb}&status=rejected")
    assert single.json()["total"] == 1


def test_list_reports_status_counts_that_ignore_the_active_filter(
    client: TestClient, seed_policy_item: Callable[..., str]
) -> None:
    """Every filter option shows its count, so counts cannot follow the filter."""
    kb = "kb-counts"
    seed_policy_item(kb=kb, rule_id="r-1", target_ref="claim-1")
    seed_policy_item(kb=kb, rule_id="r-2", target_ref="claim-2")
    seed_policy_item(kb=kb, rule_id="r-3", target_ref="claim-3", status="escalated")

    filtered = client.get(f"/policy/items?knowledge_base_id={kb}&status=escalated")

    body = filtered.json()
    assert body["total"] == 1
    assert body["status_counts"] == {"open": 2, "escalated": 1}


def test_list_searches_titles(
    client: TestClient, seed_policy_item: Callable[..., str]
) -> None:
    kb = "kb-search"
    seed_policy_item(kb=kb, rule_id="r-1", target_ref="claim-1", title="Upcoding suspected")
    seed_policy_item(kb=kb, rule_id="r-2", target_ref="claim-2", title="Duplicate billing")

    found = client.get(f"/policy/items?knowledge_base_id={kb}&q=upcoding")

    body = found.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Upcoding suspected"
    # Counts still describe the whole KB, so the strip keeps its numbers.
    assert body["status_counts"] == {"open": 2}


def test_legacy_gap_routes_are_gone(client: TestClient) -> None:
    assert client.get("/policy/gaps").status_code == 404


def test_no_seed_methods_outside_tests() -> None:
    # de-seed regression: ApiState must not expose policy-gap seeding anymore.
    import api.state as state_mod

    assert not hasattr(state_mod, "PolicyGapRecord")
    assert not hasattr(state_mod.ApiState, "_seed_policy_gaps")
    assert not hasattr(state_mod.ApiState, "list_policy_gaps")
