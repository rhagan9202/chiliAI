"""Tests for the RAG chat router."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.chat import get_rag_service, router
from rag.exceptions import RagConfigurationError
from rag.protocols import RagServiceProtocol
from rag.service_models import (
    RagAnswer,
    RagCitation,
    RagQueryRequest,
    RagQueryResponse,
    RagStreamChunk,
)


class StubRagService:
    """A deterministic stub satisfying ``RagServiceProtocol`` for tests."""

    def __init__(
        self,
        *,
        known_kb_ids: set[str],
        answer_content: str = "Deterministic answer.",
        answer_sources: list[str] | None = None,
        stream_tokens: list[str] | None = None,
        stream_sources: list[str] | None = None,
    ) -> None:
        self._known_kb_ids = set(known_kb_ids)
        self._answer_content = answer_content
        self._answer_sources = list(answer_sources or ["doc-1", "doc-2"])
        self._stream_tokens = list(stream_tokens or ["Hello", " ", "world"])
        self._stream_sources = list(stream_sources or ["doc-1"])
        self.calls: list[tuple[str, str]] = []

    def answer(self, request: RagQueryRequest) -> RagQueryResponse:  # pragma: no cover - unused here
        raise NotImplementedError

    def answer_question(
        self,
        *,
        knowledge_base_id: str,
        question: str,
    ) -> RagAnswer:
        self.calls.append((knowledge_base_id, question))
        if knowledge_base_id not in self._known_kb_ids:
            raise RagConfigurationError(
                f"Knowledge base '{knowledge_base_id}' is not registered."
            )
        return RagAnswer(content=self._answer_content, sources=list(self._answer_sources))

    def stream_answer(self, request: RagQueryRequest) -> Iterator[RagStreamChunk]:
        self.calls.append((request.knowledge_base_id, request.question))
        if request.knowledge_base_id not in self._known_kb_ids:
            raise RagConfigurationError(
                f"Knowledge base '{request.knowledge_base_id}' is not registered."
            )
        for token in self._stream_tokens:
            yield RagStreamChunk(chunk_text=token, is_final=False)
        yield RagStreamChunk(
            chunk_text="",
            is_final=True,
            citations=[
                RagCitation(
                    record_id=source,
                    content_id=source,
                    score=0.0,
                    snippet="",
                )
                for source in self._stream_sources
            ],
        )


def _build_app(service: RagServiceProtocol) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_rag_service] = lambda: service
    return app


@pytest.fixture()
def stub_service() -> StubRagService:
    return StubRagService(known_kb_ids={"kb-known"})


def test_send_message_returns_answer_and_sources(stub_service: StubRagService) -> None:
    app = _build_app(stub_service)
    client = TestClient(app)

    response = client.post(
        "/chat/conversations/conv-1/messages",
        json={"content": "Why was claim 42 denied?", "kb_id": "kb-known"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "Deterministic answer."
    assert payload["sources"] == ["doc-1", "doc-2"]
    assert stub_service.calls == [("kb-known", "Why was claim 42 denied?")]


def test_send_message_returns_400_for_blank_content(stub_service: StubRagService) -> None:
    app = _build_app(stub_service)
    client = TestClient(app)

    response = client.post(
        "/chat/conversations/conv-1/messages",
        json={"content": "   ", "kb_id": "kb-known"},
    )

    assert response.status_code == 422  # Pydantic v2 validation error


def test_send_message_returns_400_for_empty_content_via_router(
    stub_service: StubRagService,
) -> None:
    app = _build_app(stub_service)
    client = TestClient(app)

    response = client.post(
        "/chat/conversations/conv-1/messages",
        json={"content": "", "kb_id": "kb-known"},
    )

    assert response.status_code == 422


def test_send_message_returns_404_for_missing_kb(stub_service: StubRagService) -> None:
    app = _build_app(stub_service)
    client = TestClient(app)

    response = client.post(
        "/chat/conversations/conv-1/messages",
        json={"content": "Tell me more", "kb_id": "kb-unknown"},
    )

    assert response.status_code == 404
    payload = response.json()
    assert "kb-unknown" in payload["detail"]


def test_stream_message_returns_sse_with_done_sentinel(
    stub_service: StubRagService,
) -> None:
    app = _build_app(stub_service)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/chat/conversations/conv-1/messages",
        params={"stream": "true"},
        json={"content": "Tell me more", "kb_id": "kb-known"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = b"".join(response.iter_bytes()).decode("utf-8")

    events = _parse_sse_events(body)
    assert len(events) == 4  # 3 token chunks + final done sentinel

    tokens: list[str] = []
    for event in events:
        token = event["token"]
        assert isinstance(token, str)
        tokens.append(token)
    assert "".join(tokens) == "Hello world"

    final = events[-1]
    assert final["done"] is True
    assert final["token"] == ""
    assert final["sources"] == ["doc-1"]


def test_stream_message_emits_error_event_for_unknown_kb(
    stub_service: StubRagService,
) -> None:
    app = _build_app(stub_service)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/chat/conversations/conv-1/messages",
        params={"stream": "true"},
        json={"content": "Tell me more", "kb_id": "kb-unknown"},
    ) as response:
        assert response.status_code == 200
        body = b"".join(response.iter_bytes()).decode("utf-8")

    events = _parse_sse_events(body)
    assert len(events) == 1
    assert events[0]["done"] is True
    error_message = events[0]["error"]
    assert isinstance(error_message, str)
    assert "kb-unknown" in error_message


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for raw_event in body.split("\n\n"):
        line = raw_event.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[len("data: ") :]))
    return events
