"""`GET /chat/conversations?kb=` lists a knowledge base's conversations (UXA-403)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _create(client: TestClient, *, kb: str, title: str) -> str:
    response = client.post(
        "/chat/conversations", json={"knowledge_base_id": kb, "title": title}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def test_lists_only_the_requested_knowledge_bases_conversations() -> None:
    client = _client()
    _create(client, kb="kb-1", title="First")
    _create(client, kb="kb-1", title="Second")
    _create(client, kb="kb-2", title="Other")

    payload = client.get("/chat/conversations", params={"kb": "kb-1"}).json()

    assert payload["page"]["total_items"] == 2
    assert {item["title"] for item in payload["items"]} == {"First", "Second"}


def test_summarizes_each_conversation_without_shipping_every_message() -> None:
    client = _client()
    conversation_id = _create(client, kb="kb-1", title="Redwood review")
    client.post(
        f"/chat/conversations/{conversation_id}/messages",
        params={"knowledge_base_id": "kb-1"},
        json={"content": "Why is this flagged?"},
    )

    item = client.get("/chat/conversations", params={"kb": "kb-1"}).json()["items"][0]

    assert item["id"] == conversation_id
    assert item["title"] == "Redwood review"
    assert item["message_count"] >= 1
    assert item["last_message"]
    assert "messages" not in item


def test_reports_an_empty_page_for_a_knowledge_base_with_no_conversations() -> None:
    payload = _client().get("/chat/conversations", params={"kb": "kb-empty"}).json()

    assert payload["items"] == []
    assert payload["page"]["total_items"] == 0


def test_requires_the_knowledge_base_scope() -> None:
    # Listing every conversation in the workspace is not a question the UI
    # asks, and answering it would leak across knowledge bases.
    assert _client().get("/chat/conversations").status_code == 422
