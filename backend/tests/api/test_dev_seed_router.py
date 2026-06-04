"""Tests for the dev/e2e-only seed endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app


def _get_client() -> TestClient:
    return TestClient(create_app())


def test_dev_seed_writes_real_alert_evidence_case_and_kb() -> None:
    client = _get_client()

    resp = client.post("/admin/dev-seed")
    assert resp.status_code == 200
    ids = resp.json()
    kb = ids["knowledge_base_id"]
    assert kb and ids["alert_id"] and ids["evidence_pack_id"] and ids["case_id"]

    # The alert is in the real projection feed, KB-scoped.
    alerts = client.get("/alerts").json()["items"]
    seeded = next((a for a in alerts if a["id"] == ids["alert_id"]), None)
    assert seeded is not None
    assert seeded["knowledge_base_id"] == kb
    assert seeded["evidence_pack_id"] == ids["evidence_pack_id"]

    # The evidence pack is served from the real repository.
    ev = client.get(
        f"/evidence-packs/{ids['evidence_pack_id']}", params={"knowledge_base_id": kb}
    )
    assert ev.status_code == 200
    assert ev.json()["subgraph_node_ids"]

    # The case is served from the real repository (KB-scoped). It is independent
    # of the seeded alert so that alert stays promotable in the promote spec.
    case = client.get(f"/cases/{ids['case_id']}", params={"knowledge_base_id": kb})
    assert case.status_code == 200
    assert case.json()["case"]["knowledge_base_id"] == kb
    assert case.json()["case"]["alert_ids"] == []

    # The KB is listed.
    kbs = client.get("/knowledgebases").json()["items"]
    assert any(k["id"] == kb for k in kbs)

    # The seeded entity + its neighborhood are in the REAL graph (the endpoints
    # the workbench / EvidencePackViewer actually query).
    detail = client.get(f"/investigation/entities/{ids['entity_id']}", params={"kb_id": kb})
    assert detail.status_code == 200
    assert detail.json()["entity"]["id"] == ids["entity_id"]

    neighborhood = client.get(
        f"/investigation/entities/{ids['entity_id']}/neighborhood",
        params={"kb_id": kb, "depth": 2},
    )
    assert neighborhood.status_code == 200
    node_ids = {e["id"] for e in neighborhood.json()["entities"]}
    assert {"provider-1", "claim-1", "beneficiary-1"} <= node_ids


def test_dev_seed_serves_entity_via_graph_read_model() -> None:
    # BL-012: /graph/entities/{id} now reads the durable graph the seeder wrote.
    client = _get_client()

    ids = client.post("/admin/dev-seed").json()

    detail = client.get(f"/graph/entities/{ids['entity_id']}")
    assert detail.status_code == 200
    assert detail.json()["entity"]["id"] == ids["entity_id"]


def test_dev_seed_creates_a_conversation() -> None:
    # BL-012: the seeder writes one durable chat conversation for the KB.
    client = _get_client()

    body = client.post("/admin/dev-seed").json()
    conversation_id = body["conversation_id"]
    assert conversation_id

    conversation = client.get(f"/chat/conversations/{conversation_id}")
    assert conversation.status_code == 200
    payload = conversation.json()
    assert payload["knowledge_base_id"] == body["knowledge_base_id"]
    assert len(payload["messages"]) == 2
    assert payload["messages"][-1]["role"] == "assistant"


def test_dev_seed_creates_a_policy_item() -> None:
    client = _get_client()

    res = client.post("/admin/dev-seed")
    assert res.status_code == 200
    body = res.json()
    assert body["policy_item_id"]
    kb = body["knowledge_base_id"]
    got = client.get(f"/policy/items/{body['policy_item_id']}?knowledge_base_id={kb}")
    assert got.status_code == 200
    assert got.json()["item"]["status"] == "open"
