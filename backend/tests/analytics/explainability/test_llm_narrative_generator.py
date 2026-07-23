"""Tests for the LLM-backed narrative generator adapter."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest

from analytics.explainability.adapters.deterministic import DeterministicNarrativeGenerator
from analytics.explainability.adapters.llm_narrative import LlmNarrativeGenerator
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationSubgraph,
)
from llm.exceptions import LlmError, LlmProviderError
from llm.service_models import CompletionResponse, GenerateRequest
from shared.types import Alert


class _StubLlmService:
    def __init__(self, completion: str | None = None, error: Exception | None = None) -> None:
        self._completion = completion
        self._error = error
        self.requests: list[GenerateRequest] = []

    def generate(self, request: GenerateRequest) -> CompletionResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._completion is not None
        return CompletionResponse(
            request_id="req-1",
            completion=self._completion,
            provider="stub",
            model_name=request.model_name,
        )

    async def generate_stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""


def _context(items: list[ExplanationItem]) -> ExplanationContext:
    return ExplanationContext(
        knowledge_base_id="kb-1",
        alert=Alert(
            id="a-1",
            entity_type="provider",
            entity_id="p-1",
            severity="high",
            title="Suspicious Billing Spike",
            reasoning="r",
            created_at=datetime.now(tz=timezone.utc),
        ),
        explanation_items=items,
        subgraph=ExplanationSubgraph(node_ids=["p-1"]),
        confidence=0.8,
        scores={"overall": 0.8},
    )


def _item(source_id: str, rationale: str, score: float = 0.5) -> ExplanationItem:
    return ExplanationItem(
        source_id=source_id,
        source_type="risk_factor",
        quote=f"quote for {source_id}",
        rationale=rationale,
        score=score,
    )


def _generator(service: _StubLlmService) -> LlmNarrativeGenerator:
    return LlmNarrativeGenerator(
        service,
        fallback=DeterministicNarrativeGenerator(),
        model_name="gpt-test",
        temperature=0.3,
        max_tokens=512,
    )


class TestLlmNarrativeGeneratorHappyPath:
    def test_structured_completion_parses_sections_and_evidence_refs(self) -> None:
        items = [_item("src-one", "one"), _item("src-two", "two")]
        completion = (
            "Summary line.\n\n"
            "## Billing Pattern\nDetail about src-one.\n\n"
            "## Network\nOther."
        )
        service = _StubLlmService(completion=completion)
        narrative = _generator(service).summarize(context=_context(items), items=items)

        assert narrative.summary == "Summary line."
        assert len(narrative.sections) == 2
        assert narrative.sections[0].heading == "Billing Pattern"
        assert narrative.sections[0].body == "Detail about src-one."
        assert narrative.sections[0].evidence_refs == ["src-one"]
        assert narrative.sections[1].heading == "Network"
        assert narrative.sections[1].body == "Other."
        # No item's source_id/quote appears verbatim -> falls back to all selected ids.
        assert narrative.sections[1].evidence_refs == ["src-one", "src-two"]

    def test_collapses_newlines_in_section_body(self) -> None:
        items = [_item("src-one", "one")]
        completion = "Summary.\n\n## Heading\nLine one.\nLine two about src-one.\n"
        service = _StubLlmService(completion=completion)
        narrative = _generator(service).summarize(context=_context(items), items=items)

        assert narrative.sections[0].body == "Line one. Line two about src-one."

    def test_heading_less_completion_degrades_to_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A completion ignoring the mandated ``## `` heading format is
        malformed under the prompt contract: per the plan's global error
        constraint it degrades to the deterministic fallback (which always
        produces sections) instead of yielding a section-less narrative.
        Adjudicated during the Task 9 live pass — the dev echo provider never
        emits headings, so summary-only output left every persisted pack with
        empty ``narrative_sections``.
        """
        items = [_item("src-one", "one")]
        completion = "Just a plain paragraph with no markdown headings at all."
        service = _StubLlmService(completion=completion)
        with caplog.at_level(logging.WARNING):
            narrative = _generator(service).summarize(context=_context(items), items=items)

        expected = DeterministicNarrativeGenerator().summarize(
            context=_context(items), items=items
        )
        assert narrative == expected
        assert narrative.sections != []
        assert any("degrading to fallback" in record.message for record in caplog.records)

    def test_sends_constructed_model_parameters(self) -> None:
        items = [_item("src-one", "one")]
        service = _StubLlmService(completion="Summary.\n\n## H\nBody.")
        _generator(service).summarize(context=_context(items), items=items)

        assert len(service.requests) == 1
        request = service.requests[0]
        assert request.model_name == "gpt-test"
        assert request.temperature == 0.3
        assert request.max_tokens == 512
        assert request.knowledge_base_id == "kb-1"
        assert request.messages == []

    def test_prompt_contains_evidence_score_and_alert_title(self) -> None:
        items = [_item("src-one", "distinctive-rationale-text", score=0.5)]
        service = _StubLlmService(completion="Summary.\n\n## H\nBody.")
        _generator(service).summarize(context=_context(items), items=items)

        request = service.requests[0]
        assert request.prompt_template is not None
        user_prompt = request.prompt_template.user_prompt
        assert "distinctive-rationale-text" in user_prompt
        assert "0.50" in user_prompt
        assert "Suspicious Billing Spike" in user_prompt
        assert "src-one" in user_prompt
        assert "quote for src-one" in user_prompt


class TestLlmNarrativeGeneratorDegradesToFallback:
    def test_provider_error_falls_back_to_deterministic_output(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        items = [_item("src-one", "one"), _item("src-two", "two")]
        service = _StubLlmService(error=LlmProviderError("boom"))
        context = _context(items)

        with caplog.at_level(logging.WARNING):
            narrative = _generator(service).summarize(context=context, items=items)

        expected = DeterministicNarrativeGenerator().summarize(context=context, items=items)
        assert narrative == expected
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_base_llm_error_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        items = [_item("src-one", "one")]
        service = _StubLlmService(error=LlmError("generic failure"))
        context = _context(items)

        with caplog.at_level(logging.WARNING):
            narrative = _generator(service).summarize(context=context, items=items)

        expected = DeterministicNarrativeGenerator().summarize(context=context, items=items)
        assert narrative == expected
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_unexpected_exception_falls_back_and_never_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        items = [_item("src-one", "one")]
        service = _StubLlmService(error=RuntimeError("totally unexpected"))
        context = _context(items)

        with caplog.at_level(logging.WARNING):
            narrative = _generator(service).summarize(context=context, items=items)

        expected = DeterministicNarrativeGenerator().summarize(context=context, items=items)
        assert narrative == expected
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_empty_completion_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        items = [_item("src-one", "one")]
        service = _StubLlmService(completion="   ")
        context = _context(items)

        with caplog.at_level(logging.WARNING):
            narrative = _generator(service).summarize(context=context, items=items)

        expected = DeterministicNarrativeGenerator().summarize(context=context, items=items)
        assert narrative == expected
        assert any(record.levelno == logging.WARNING for record in caplog.records)
