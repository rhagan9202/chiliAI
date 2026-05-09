"""LLM bridge adapter that delegates rag answer generation to the llm service."""

from __future__ import annotations

from collections.abc import Iterator

from llm.models import MessageRole
from llm.protocols import LlmServiceProtocol
from llm.service_models import ChatMessageInput, GenerateRequest
from rag.models import (
    RagGenerationRequest,
    RagGenerationResult,
    RetrievedContextItem,
)


_DEFAULT_SYSTEM_PROMPT = (
    "You are a retrieval-augmented assistant. Use the provided context items "
    "to answer the user's question. If the context is insufficient, say so."
)
_CHAR_PER_TOKEN = 4
_BUDGET_FRACTION = 0.8
_MIN_TRUNCATED_CONTENT_CHARS = 16


class ServiceAnswerGenerator:
    """Generate rag answers by delegating to an `LlmServiceProtocol` implementation."""

    def __init__(
        self,
        llm_service: LlmServiceProtocol,
        *,
        max_tokens: int,
        model_name: str,
        temperature: float = 0.2,
        knowledge_base_id_in_request: bool = True,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("ServiceAnswerGenerator max_tokens must be positive.")
        if not model_name.strip():
            raise ValueError("ServiceAnswerGenerator model_name must not be empty.")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError(
                "ServiceAnswerGenerator temperature must be between 0.0 and 2.0."
            )
        self._llm_service = llm_service
        self._max_tokens = max_tokens
        self._model_name = model_name
        self._temperature = temperature
        self._propagate_kb_id = knowledge_base_id_in_request

    def generate(self, request: RagGenerationRequest) -> RagGenerationResult:
        system_prompt = (request.system_prompt or _DEFAULT_SYSTEM_PROMPT).strip()
        budget_chars = int(self._max_tokens * _BUDGET_FRACTION) * _CHAR_PER_TOKEN
        fitted_items = _fit_context_to_budget(
            request.context_items,
            system_prompt=system_prompt,
            question=request.question,
            graph_summary=_graph_summary(request),
            budget_chars=budget_chars,
        )

        prompt = _assemble_prompt(
            system_prompt=system_prompt,
            context_items=fitted_items,
            graph_summary=_graph_summary(request),
            question=request.question,
        )

        generate_request = GenerateRequest(
            knowledge_base_id=request.knowledge_base_id if self._propagate_kb_id else None,
            model_name=self._model_name,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            messages=[
                ChatMessageInput(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessageInput(role=MessageRole.USER, content=prompt),
            ],
        )

        response = self._llm_service.generate(generate_request)
        return RagGenerationResult(
            request_id=request.request_id,
            answer=response.completion,
            provider=response.provider,
            model_name=response.model_name,
        )

    def stream_generate(self, request: RagGenerationRequest) -> Iterator[str]:
        # Streaming via the LLM service is asynchronous; until the rag pipeline
        # supports an async streaming path, fall back to a single-shot
        # generation and emit the completion as one chunk. This keeps the
        # iterator contract synchronous while preserving the production code
        # path through ``LlmServiceProtocol``.
        result = self.generate(request)
        yield result.answer


def _graph_summary(request: RagGenerationRequest) -> str | None:
    if request.graph_context is None:
        return None
    summary = request.graph_context.summary
    if summary is None or summary.strip() == "":
        return None
    return summary


def _assemble_prompt(
    *,
    system_prompt: str,
    context_items: list[RetrievedContextItem],
    graph_summary: str | None,
    question: str,
) -> str:
    sections: list[str] = []
    if context_items:
        rendered_items = "\n\n".join(
            f"[{index + 1}] (record={item.record_id}, score={item.score:.4f})\n{item.content}"
            for index, item in enumerate(context_items)
        )
        sections.append(f"Context:\n{rendered_items}")
    else:
        sections.append("Context: (no retrieved context available)")
    if graph_summary is not None:
        sections.append(f"Graph context: {graph_summary}")
    sections.append(f"Question: {question}")
    return "\n\n".join(sections)


def _fit_context_to_budget(
    context_items: list[RetrievedContextItem],
    *,
    system_prompt: str,
    question: str,
    graph_summary: str | None,
    budget_chars: int,
) -> list[RetrievedContextItem]:
    if budget_chars <= 0:
        return []

    overhead_chars = (
        len(system_prompt) + len(question) + (len(graph_summary) if graph_summary else 0)
    )
    available_for_context = max(budget_chars - overhead_chars, 0)
    if available_for_context == 0:
        return []

    sorted_items = sorted(
        enumerate(context_items),
        key=lambda pair: pair[1].score,
        reverse=True,
    )
    selected: list[tuple[int, RetrievedContextItem]] = []
    total = 0
    for original_index, item in sorted_items:
        item_cost = len(item.content)
        if total + item_cost <= available_for_context:
            selected.append((original_index, item))
            total += item_cost
            continue
        remaining = available_for_context - total
        if remaining >= _MIN_TRUNCATED_CONTENT_CHARS:
            truncated_content = item.content[:remaining].rstrip()
            if truncated_content:
                truncated = item.model_copy(update={"content": truncated_content})
                selected.append((original_index, truncated))
                total += len(truncated_content)
        break

    selected.sort(key=lambda pair: pair[0])
    return [item for _, item in selected]


__all__ = ["ServiceAnswerGenerator"]
