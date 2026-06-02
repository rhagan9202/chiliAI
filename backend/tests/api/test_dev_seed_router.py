"""Tests for the dev/e2e-only seed endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app


def test_dev_seed_writes_real_alert_evidence_case_and_kb() -> None:
    client = TestClient(create_app())

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
