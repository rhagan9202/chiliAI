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


# ---------------------------------------------------------------------------
# Construction-time failure skipping (graceful fallthrough)
# ---------------------------------------------------------------------------


def test_factory_skips_failing_primary_and_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When primary raises LlmConfigurationError the factory should use fallback directly."""
    import llm.adapters.openai_adapter as _oa
    from llm.exceptions import LlmConfigurationError as _LlmCfgErr

    def _raise(config: object) -> None:
        raise _LlmCfgErr("OPENAI_API_KEY missing")

    monkeypatch.setattr(_oa, "OpenAILlmClient", _raise)
    monkeypatch.setenv("OPENAI_API_KEY", "")

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
    # Primary failed, so result is the bare fallback (not wrapped in FallbackLlmClient)
    assert isinstance(client, OllamaLlmClient)


def test_factory_skips_failing_primary_and_uses_remaining_fallback_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3-level chain openai→ollama→local: patched openai raises, result is FallbackLlmClient(ollama, [local])."""
    import llm.adapters.openai_adapter as _oa
    from llm.exceptions import LlmConfigurationError as _LlmCfgErr

    def _raise(config: object) -> None:
        raise _LlmCfgErr("OPENAI_API_KEY missing")

    monkeypatch.setattr(_oa, "OpenAILlmClient", _raise)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key_env_var="OPENAI_API_KEY",
        fallback=LlmConfig(
            provider="ollama",
            model="llama3.1:8b",
            base_url="http://localhost:11434",
            fallback=LlmConfig(provider="local", model="local-default"),
        ),
    )
    client = create_llm_client(config)
    # openai failed → result is FallbackLlmClient wrapping ollama+local
    assert isinstance(client, FallbackLlmClient)
    assert isinstance(client._primary, OllamaLlmClient)
    assert len(client._fallbacks) == 1
    assert isinstance(client._fallbacks[0], InMemoryLlmClient)


def test_factory_raises_when_entire_chain_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every provider in the chain fails, LlmConfigurationError is raised."""
    import llm.adapters.openai_adapter as _oa
    import llm.adapters.ollama_adapter as _ol
    from llm.exceptions import LlmConfigurationError as _LlmCfgErr

    def _raise_openai(config: object) -> None:
        raise _LlmCfgErr("OPENAI_API_KEY missing")

    def _raise_ollama(*, base_url: str) -> None:
        raise _LlmCfgErr("Ollama unavailable")

    monkeypatch.setattr(_oa, "OpenAILlmClient", _raise_openai)
    monkeypatch.setattr(_ol, "OllamaLlmClient", _raise_ollama)
    monkeypatch.setenv("OPENAI_API_KEY", "")

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
    with pytest.raises(_LlmCfgErr):
        create_llm_client(config)


def test_factory_falls_back_when_only_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider=openai with no fallback and openai raises → LlmConfigurationError."""
    import llm.adapters.openai_adapter as _oa
    from llm.exceptions import LlmConfigurationError as _LlmCfgErr

    def _raise(config: object) -> None:
        raise _LlmCfgErr("OPENAI_API_KEY missing")

    monkeypatch.setattr(_oa, "OpenAILlmClient", _raise)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key_env_var="OPENAI_API_KEY",
    )
    with pytest.raises(_LlmCfgErr):
        create_llm_client(config)


def test_factory_includes_local_as_safety_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider=openai with fallback=local and openai raises → InMemoryLlmClient."""
    import llm.adapters.openai_adapter as _oa
    from llm.exceptions import LlmConfigurationError as _LlmCfgErr

    def _raise(config: object) -> None:
        raise _LlmCfgErr("OPENAI_API_KEY missing")

    monkeypatch.setattr(_oa, "OpenAILlmClient", _raise)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key_env_var="OPENAI_API_KEY",
        fallback=LlmConfig(provider="local", model="local-default"),
    )
    client = create_llm_client(config)
    assert isinstance(client, InMemoryLlmClient)
