"""Tests for the consolidated /chat router (rag.py).

Non-streaming behavior is also covered in test_phase5_stateful_routes.py; this
module focuses on the streaming branch and the 404 paths that the consolidated
router took over from the old chat.py.
"""

from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config, get_session_store
from api.middleware.session_store import InMemorySessionStore, SessionRecord
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig


def _domain_with_auth() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _save_session(
    store: InMemorySessionStore,
    *,
    session_id: str,
    roles: list[str],
) -> None:
    now = time.time()
    store.save(
        SessionRecord(
            session_id=session_id,
            user_id=session_id,
            roles=roles,
            email=f"{session_id}@example.com",
            access_token="access-token",
            refresh_token="refresh-token",
            access_token_expires_at=now + 3600,
            id_token="id-token",
            created_at=now,
            ttl_seconds=3600,
        )
    )


def _app_with_auth_sessions() -> tuple[FastAPI, InMemorySessionStore]:
    app = create_app()
    store = InMemorySessionStore()
    _save_session(store, session_id="sid-viewer", roles=["viewer"])
    _save_session(store, session_id="sid-analyst", roles=["analyst"])
    app.dependency_overrides[get_domain_config] = _domain_with_auth
    app.dependency_overrides[get_session_store] = lambda: store
    return app, store


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


def test_viewer_cannot_create_or_add_chat_messages_when_auth_enabled() -> None:
    app, _store = _app_with_auth_sessions()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-viewer")
        create_response = client.post(
            "/chat/conversations",
            json={"knowledge_base_id": "kb-1", "title": "Viewer write"},
        )
        message_response = client.post(
            "/chat/conversations/conv-1/messages",
            json={"content": "Can I mutate this thread?"},
        )

    assert create_response.status_code == 403
    assert message_response.status_code == 403


def test_analyst_can_add_chat_message_when_auth_enabled() -> None:
    app, _store = _app_with_auth_sessions()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-analyst")
        created = client.post(
            "/chat/conversations",
            json={"knowledge_base_id": "kb-1", "title": "Analyst write"},
        )
        conversation_id = created.json()["id"]
        updated = client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"content": "Why is this claim risky?"},
        )

    assert created.status_code == 200
    assert updated.status_code == 200


def test_viewer_can_read_chat_conversation_when_auth_enabled() -> None:
    app, _store = _app_with_auth_sessions()

    with TestClient(app) as client:
        client.cookies.set("chiliai_session", "sid-analyst")
        created = client.post(
            "/chat/conversations",
            json={"knowledge_base_id": "kb-1", "title": "Readable thread"},
        )
        conversation_id = created.json()["id"]

        client.cookies.set("chiliai_session", "sid-viewer")
        read_response = client.get(f"/chat/conversations/{conversation_id}")

    assert read_response.status_code == 200
    assert read_response.json()["id"] == conversation_id


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
