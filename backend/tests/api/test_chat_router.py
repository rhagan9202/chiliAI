"""Tests for the consolidated /chat router (rag.py).

Non-streaming behavior is also covered in test_phase5_stateful_routes.py; this
module focuses on the streaming branch and the 404 paths that the consolidated
router took over from the old chat.py.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api.app import create_app


def _new_conversation_id(client: TestClient) -> str:
    created = client.post(
        "/chat/conversations",
        json={"knowledge_base_id": "kb-1", "title": "Streaming test"},
    )
    assert created.status_code == 200
    return str(created.json()["id"])


def test_send_message_returns_full_conversation() -> None:
    """Non-streaming POST returns the Phase 5 ChatConversationResponse contract."""
    client = TestClient(create_app())
    conversation_id = _new_conversation_id(client)

    response = client.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"content": "Why was claim 42 denied?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == conversation_id
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"


def test_send_message_404_for_unknown_conversation() -> None:
    """Unknown conversation ids resolve to 404, not 500 from a bare KeyError."""
    client = TestClient(create_app())

    response = client.post(
        "/chat/conversations/does-not-exist/messages",
        json={"content": "anything"},
    )

    assert response.status_code == 404


def test_stream_message_returns_sse_with_done_sentinel() -> None:
    """``?stream=true`` returns text/event-stream and terminates with done sentinel."""
    client = TestClient(create_app())
    conversation_id = _new_conversation_id(client)

    with client.stream(
        "POST",
        f"/chat/conversations/{conversation_id}/messages",
        params={"stream": "true"},
        json={"content": "Tell me more"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = b"".join(response.iter_bytes()).decode("utf-8")

    events = _parse_sse_events(body)
    assert len(events) >= 2  # at least one token chunk + final done sentinel
    assert events[-1]["done"] is True
    assert "sources" in events[-1]


def test_stream_message_404_for_unknown_conversation() -> None:
    """Streaming path also 404s for unknown conversation ids before opening the stream."""
    client = TestClient(create_app())

    response = client.post(
        "/chat/conversations/missing/messages",
        params={"stream": "true"},
        json={"content": "anything"},
    )

    assert response.status_code == 404


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for raw_event in body.split("\n\n"):
        line = raw_event.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[len("data: ") :]))
    return events
