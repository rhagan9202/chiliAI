from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import LlmConfig


def test_ollama_is_accepted_as_provider() -> None:
    config = LlmConfig(provider="ollama", model="llama3.1:8b")
    assert config.provider == "ollama"


def test_base_url_is_accepted() -> None:
    config = LlmConfig(provider="ollama", model="llama3.1:8b", base_url="http://ollama:11434")
    assert config.base_url == "http://ollama:11434"


def test_fallback_chain_is_accepted() -> None:
    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        fallback=LlmConfig(provider="ollama", model="llama3.1:8b"),
    )
    assert config.fallback is not None
    assert config.fallback.provider == "ollama"
    assert config.fallback.model == "llama3.1:8b"


def test_nested_fallback_chain_is_accepted() -> None:
    # Primary openai → fallback anthropic → fallback ollama
    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        fallback=LlmConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            fallback=LlmConfig(provider="ollama", model="llama3.1:8b"),
        ),
    )
    assert config.fallback is not None
    assert config.fallback.fallback is not None
    assert config.fallback.fallback.provider == "ollama"


def test_unknown_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        LlmConfig.model_validate({"provider": "vllm"})
