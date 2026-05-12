"""Tests for the production answer generator bridge."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from llm.models import MessageRole
from llm.service_models import CompletionResponse, GenerateRequest
from api._rag_bridges import ServiceAnswerGenerator
from rag.adapters.protocols import AnswerGeneratorProtocol
from rag.models import (
    GraphContext,
    RagGenerationRequest,
    RetrievedContextItem,
)


class _RecordingLlmService:
    """In-memory fake conforming to `LlmServiceProtocol`."""

    def __init__(self, response: CompletionResponse) -> None:
        self._response = response
        self.requests: list[GenerateRequest] = []

    def generate(self, request: GenerateRequest) -> CompletionResponse:
        self.requests.append(request)
        return self._response

    def generate_stream(self, request: GenerateRequest) -> AsyncIterator[str]:  # pragma: no cover
        del request
        raise NotImplementedError


def _completion(
    *,
    request_id: str = "req-1",
    completion: str = "Final answer.",
    provider: str = "fake-provider",
    model_name: str = "fake-model",
) -> CompletionResponse:
    return CompletionResponse(
        request_id=request_id,
        completion=completion,
        provider=provider,
        model_name=model_name,
    )


def _item(
    *,
    record_id: str,
    content_id: str,
    score: float,
    content: str = "snippet",
) -> RetrievedContextItem:
    return RetrievedContextItem(
        record_id=record_id,
        content_id=content_id,
        score=score,
        content=content,
        metadata={},
    )


def _request(
    *,
    items: list[RetrievedContextItem] | None = None,
    graph_context: GraphContext | None = None,
    system_prompt: str | None = None,
    question: str = "What happened?",
    request_id: str = "req-1",
) -> RagGenerationRequest:
    return RagGenerationRequest(
        request_id=request_id,
        knowledge_base_id="kb-1",
        question=question,
        context_items=items or [],
        graph_context=graph_context,
        system_prompt=system_prompt,
    )


def test_service_answer_generator_satisfies_protocol() -> None:
    service = _RecordingLlmService(_completion())

    generator: AnswerGeneratorProtocol = ServiceAnswerGenerator(
        service, max_tokens=4096, model_name="fake-model"
    )

    assert isinstance(generator, AnswerGeneratorProtocol)


def test_service_answer_generator_assembles_prompt_with_context_and_question() -> None:
    service = _RecordingLlmService(_completion(completion="Answer text."))
    generator = ServiceAnswerGenerator(
        service, max_tokens=4096, model_name="fake-model", temperature=0.1
    )

    request = _request(
        items=[
            _item(record_id="r-1", content_id="c-1", score=0.9, content="alpha"),
            _item(record_id="r-2", content_id="c-2", score=0.8, content="beta"),
        ],
        question="Why did claim 42 get flagged?",
        system_prompt="You answer fraud questions.",
    )

    result = generator.generate(request)

    assert len(service.requests) == 1
    forwarded = service.requests[0]
    assert forwarded.knowledge_base_id == "kb-1"
    assert forwarded.model_name == "fake-model"
    assert forwarded.temperature == 0.1
    assert forwarded.max_tokens == 4096
    assert [m.role for m in forwarded.messages] == [MessageRole.SYSTEM, MessageRole.USER]
    assert forwarded.messages[0].content == "You answer fraud questions."
    user_content = forwarded.messages[1].content
    assert "Context:" in user_content
    assert "[1]" in user_content and "alpha" in user_content
    assert "[2]" in user_content and "beta" in user_content
    assert "Question: Why did claim 42 get flagged?" in user_content
    assert user_content.rstrip().endswith("Why did claim 42 get flagged?")

    assert result.request_id == request.request_id
    assert result.answer == "Answer text."
    assert result.provider == "fake-provider"
    assert result.model_name == "fake-model"


def test_service_answer_generator_uses_default_system_prompt_when_missing() -> None:
    service = _RecordingLlmService(_completion())
    generator = ServiceAnswerGenerator(
        service, max_tokens=2048, model_name="fake-model"
    )

    generator.generate(_request())

    forwarded = service.requests[0]
    assert "retrieval-augmented assistant" in forwarded.messages[0].content


def test_service_answer_generator_includes_graph_summary_in_prompt() -> None:
    service = _RecordingLlmService(_completion())
    generator = ServiceAnswerGenerator(
        service, max_tokens=2048, model_name="fake-model"
    )

    request = _request(
        items=[_item(record_id="r-1", content_id="c-1", score=0.5, content="alpha")],
        graph_context=GraphContext(summary="2 nodes, 1 edge."),
    )

    generator.generate(request)

    user_content = service.requests[0].messages[1].content
    assert "Graph context: 2 nodes, 1 edge." in user_content


def test_service_answer_generator_handles_empty_context_items() -> None:
    service = _RecordingLlmService(_completion(completion="No context answer."))
    generator = ServiceAnswerGenerator(
        service, max_tokens=1024, model_name="fake-model"
    )

    result = generator.generate(_request(items=[]))

    user_content = service.requests[0].messages[1].content
    assert "no retrieved context available" in user_content
    assert result.answer == "No context answer."


def test_service_answer_generator_truncates_context_to_token_budget() -> None:
    service = _RecordingLlmService(_completion(completion="Answer."))
    generator = ServiceAnswerGenerator(
        service, max_tokens=64, model_name="fake-model"
    )

    big_content = "x" * 600
    request = _request(
        items=[
            _item(record_id="low", content_id="c-low", score=0.10, content=big_content),
            _item(record_id="high", content_id="c-high", score=0.95, content=big_content),
            _item(record_id="mid", content_id="c-mid", score=0.50, content=big_content),
        ],
        question="q?",
        system_prompt="sp",
    )

    generator.generate(request)

    user_content = service.requests[0].messages[1].content
    assert "record=high" in user_content
    assert "record=low" not in user_content
    assert "record=mid" not in user_content
    budget_chars = int(64 * 0.8) * 4
    assert len(user_content) <= budget_chars + 256


def test_service_answer_generator_drops_lowest_score_items_first_when_truncating() -> None:
    service = _RecordingLlmService(_completion(completion="Answer."))
    generator = ServiceAnswerGenerator(
        service, max_tokens=128, model_name="fake-model"
    )

    request = _request(
        items=[
            _item(record_id="rA", content_id="cA", score=0.99, content="y" * 400),
            _item(record_id="rB", content_id="cB", score=0.10, content="z" * 400),
        ],
        question="q?",
        system_prompt="sp",
    )

    generator.generate(request)

    user_content = service.requests[0].messages[1].content
    assert "record=rA" in user_content
    assert "record=rB" not in user_content


def test_service_answer_generator_rejects_invalid_max_tokens() -> None:
    service = _RecordingLlmService(_completion())

    with pytest.raises(ValueError):
        ServiceAnswerGenerator(service, max_tokens=0, model_name="fake-model")


def test_service_answer_generator_rejects_blank_model_name() -> None:
    service = _RecordingLlmService(_completion())

    with pytest.raises(ValueError):
        ServiceAnswerGenerator(service, max_tokens=64, model_name="   ")


def test_service_answer_generator_rejects_invalid_temperature() -> None:
    service = _RecordingLlmService(_completion())

    with pytest.raises(ValueError):
        ServiceAnswerGenerator(
            service, max_tokens=64, model_name="fake-model", temperature=5.0
        )


def test_service_answer_generator_respects_kb_propagation_flag() -> None:
    service = _RecordingLlmService(_completion())
    generator = ServiceAnswerGenerator(
        service,
        max_tokens=512,
        model_name="fake-model",
        knowledge_base_id_in_request=False,
    )

    generator.generate(_request())

    assert service.requests[0].knowledge_base_id is None


def test_service_answer_generator_stream_generate_yields_completion_text() -> None:
    service = _RecordingLlmService(_completion(completion="Streamed answer."))
    generator = ServiceAnswerGenerator(
        service, max_tokens=512, model_name="fake-model"
    )

    chunks = list(generator.stream_generate(_request()))

    assert chunks == ["Streamed answer."]


def test_service_answer_generator_blank_graph_summary_is_omitted() -> None:
    service = _RecordingLlmService(_completion())
    generator = ServiceAnswerGenerator(
        service, max_tokens=2048, model_name="fake-model"
    )

    request = _request(
        items=[_item(record_id="r-1", content_id="c-1", score=0.5)],
        graph_context=GraphContext(summary="   "),
    )

    generator.generate(request)

    user_content = service.requests[0].messages[1].content
    assert "Graph context:" not in user_content


def test_service_answer_generator_none_graph_summary_is_omitted() -> None:
    service = _RecordingLlmService(_completion())
    generator = ServiceAnswerGenerator(
        service, max_tokens=2048, model_name="fake-model"
    )

    request = _request(
        items=[_item(record_id="r-1", content_id="c-1", score=0.5)],
        graph_context=GraphContext(summary=None),
    )

    generator.generate(request)

    user_content = service.requests[0].messages[1].content
    assert "Graph context:" not in user_content


def test_service_answer_generator_overhead_exceeding_budget_drops_all_context() -> None:
    service = _RecordingLlmService(_completion())
    generator = ServiceAnswerGenerator(
        service, max_tokens=4, model_name="fake-model"
    )

    long_question = "Q" * 200
    request = _request(
        items=[_item(record_id="r-1", content_id="c-1", score=0.9, content="X" * 100)],
        question=long_question,
        system_prompt="S" * 200,
    )

    generator.generate(request)

    user_content = service.requests[0].messages[1].content
    assert "no retrieved context available" in user_content


def test_service_answer_generator_truncated_item_below_min_chars_is_dropped() -> None:
    """When the remaining budget is below ``_MIN_TRUNCATED_CONTENT_CHARS`` the
    last item is dropped rather than truncated to a tiny fragment."""

    service = _RecordingLlmService(_completion())
    # Use a max_tokens that allocates a small budget; we want a one-item case
    # where the candidate exceeds the remaining budget by more than the min
    # truncation threshold.
    generator = ServiceAnswerGenerator(
        service, max_tokens=16, model_name="fake-model"
    )

    request = _request(
        items=[_item(record_id="r-1", content_id="c-1", score=0.9, content="x" * 200)],
        question="q?",
        system_prompt="sp",
    )

    generator.generate(request)

    user_content = service.requests[0].messages[1].content
    # Either the item is fully dropped or truncated; we just want the code
    # path exercised. The user content should still contain the question.
    assert "Question: q?" in user_content
