from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm.adapters.fallback import FallbackLlmClient
from llm.exceptions import LlmProviderError
from llm.models import (
    ChatMessage,
    CompletionMetadata,
    GenerationRequest,
    GenerationResult,
    MessageRole,
)


def _request() -> GenerationRequest:
    return GenerationRequest(
        request_id="r1",
        model_name="m",
        messages=[ChatMessage(role=MessageRole.USER, content="hi")],
    )


def _result(provider: str) -> GenerationResult:
    return GenerationResult(
        request_id="r1",
        completion="ok",
        metadata=CompletionMetadata(provider=provider, model_name="m", temperature=0.2, max_tokens=128),
    )


def test_primary_success_skips_fallback() -> None:
    primary = MagicMock()
    primary.generate.return_value = _result("primary")
    fallback = MagicMock()

    client = FallbackLlmClient(primary=primary, fallbacks=[fallback])
    result = client.generate(_request())

    assert result.metadata.provider == "primary"
    fallback.generate.assert_not_called()


def test_primary_failure_uses_first_fallback() -> None:
    primary = MagicMock()
    primary.generate.side_effect = LlmProviderError("primary down")
    fallback = MagicMock()
    fallback.generate.return_value = _result("fallback-1")

    client = FallbackLlmClient(primary=primary, fallbacks=[fallback])
    result = client.generate(_request())

    assert result.metadata.provider == "fallback-1"
    fallback.generate.assert_called_once()


def test_all_failures_raise_chain_exhausted() -> None:
    primary = MagicMock()
    primary.generate.side_effect = LlmProviderError("primary down")
    fallback = MagicMock()
    fallback.generate.side_effect = LlmProviderError("fallback down")

    client = FallbackLlmClient(primary=primary, fallbacks=[fallback])
    with pytest.raises(LlmProviderError) as excinfo:
        client.generate(_request())
    assert "exhausted" in str(excinfo.value).lower()


def test_two_fallbacks_tried_in_order() -> None:
    primary = MagicMock()
    primary.generate.side_effect = LlmProviderError("primary down")
    fb1 = MagicMock()
    fb1.generate.side_effect = LlmProviderError("fb1 down")
    fb2 = MagicMock()
    fb2.generate.return_value = _result("fallback-2")

    client = FallbackLlmClient(primary=primary, fallbacks=[fb1, fb2])
    result = client.generate(_request())

    assert result.metadata.provider == "fallback-2"
    primary.generate.assert_called_once()
    fb1.generate.assert_called_once()
    fb2.generate.assert_called_once()
