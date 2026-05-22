"""Tests for the LLM factory: provider dispatch and fallback chain wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pytest

from config.schema import LlmConfig
from llm.adapters.fallback import FallbackLlmClient
from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.ollama_adapter import OllamaLlmClient
from llm.factory import create_llm_client


# ---------------------------------------------------------------------------
# Minimal fake OpenAI client (avoids importing the openai SDK)
# ---------------------------------------------------------------------------


class _FakeCompletions(Protocol):
    def create(self, *, model: str, messages: object, temperature: float, max_tokens: int) -> object: ...


@dataclass
class _FakeOpenAIClient:
    """Structural fake matching OpenAIClientProtocol; no SDK import needed."""

    class _Completions:
        def create(self, *, model: str, messages: object, temperature: float, max_tokens: int) -> object:  # noqa: D102
            raise NotImplementedError("not called in factory tests")

    chat: _Completions = _Completions()  # type: ignore[assignment]


def _fake_openai_client_factory(api_key: str) -> _FakeOpenAIClient:
    """Drop-in client_factory that bypasses the real openai import."""
    return _FakeOpenAIClient()


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


def test_factory_returns_in_memory_for_local() -> None:
    config = LlmConfig(provider="local", model="echo")
    client = create_llm_client(config)
    assert isinstance(client, InMemoryLlmClient)


def test_factory_returns_ollama_when_selected() -> None:
    config = LlmConfig(provider="ollama", model="llama3.1:8b", base_url="http://localhost:11434")
    client = create_llm_client(config)
    assert isinstance(client, OllamaLlmClient)


def test_factory_ollama_uses_default_base_url_when_none() -> None:
    config = LlmConfig(provider="ollama", model="llama3.1:8b")
    client = create_llm_client(config)
    assert isinstance(client, OllamaLlmClient)
    # Default base_url applied; client is not wrapped in a fallback.


# ---------------------------------------------------------------------------
# Fallback wrapping
# ---------------------------------------------------------------------------


def test_factory_returns_bare_primary_when_no_fallback() -> None:
    config = LlmConfig(provider="ollama", model="llama3.1:8b")
    client = create_llm_client(config)
    assert isinstance(client, OllamaLlmClient)  # NOT wrapped in FallbackLlmClient


def test_factory_wraps_with_fallback_when_configured() -> None:
    config = LlmConfig(
        provider="ollama",
        model="llama3.1:8b",
        base_url="http://localhost:11434",
        fallback=LlmConfig(
            provider="local",
            model="echo",
        ),
    )
    client = create_llm_client(config)
    assert isinstance(client, FallbackLlmClient)
    # The primary should be an Ollama client and the fallback an in-memory client.
    assert isinstance(client._primary, OllamaLlmClient)
    assert len(client._fallbacks) == 1
    assert isinstance(client._fallbacks[0], InMemoryLlmClient)


def test_factory_wraps_with_fallback_openai_to_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI primary → Ollama fallback; bypass real SDK via client_factory patch."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Patch _create_openai_client so the adapter doesn't need the openai package.
    import llm.adapters.openai_adapter as _oa
    monkeypatch.setattr(_oa, "_create_openai_client", _fake_openai_client_factory)
    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key_env_var="OPENAI_API_KEY",
        fallback=LlmConfig(
            provider="ollama",
            model="llama3.1:8b",
            base_url="http://localhost:11434",
        ),
    )
    client = create_llm_client(config)
    assert isinstance(client, FallbackLlmClient)
    assert isinstance(client._fallbacks[0], OllamaLlmClient)


def test_factory_three_level_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """openai → ollama → local produces nested FallbackLlmClients."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    import llm.adapters.openai_adapter as _oa
    monkeypatch.setattr(_oa, "_create_openai_client", _fake_openai_client_factory)
    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key_env_var="OPENAI_API_KEY",
        fallback=LlmConfig(
            provider="ollama",
            model="llama3.1:8b",
            base_url="http://localhost:11434",
            fallback=LlmConfig(provider="local", model="echo"),
        ),
    )
    client = create_llm_client(config)
    assert isinstance(client, FallbackLlmClient)
    inner = client._fallbacks[0]
    assert isinstance(inner, FallbackLlmClient)
    assert isinstance(inner._primary, OllamaLlmClient)
    assert isinstance(inner._fallbacks[0], InMemoryLlmClient)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_factory_rejects_unknown_provider_via_pydantic_validation() -> None:
    """Pydantic should reject an unknown provider at LlmConfig construction time."""
    with pytest.raises(Exception):
        LlmConfig(provider="vllm")  # type: ignore[arg-type]
