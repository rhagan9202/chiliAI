"""Factory for constructing an ``LlmClientProtocol`` from ``LlmConfig``.

Call :func:`create_llm_client` from dependency injection (``api/dependencies.py``)
and from the worker coordinator (``agent/coordinator.py``).  This is the single
authoritative place that knows which provider string maps to which adapter.
"""

from __future__ import annotations

from config.schema import LlmConfig
from llm.adapters.fallback import FallbackLlmClient
from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmConfigurationError


__all__ = ["create_llm_client"]


def create_llm_client(config: LlmConfig) -> LlmClientProtocol:
    """Construct an LlmClient from configuration.

    If ``config.fallback`` is set the primary client is wrapped in a
    :class:`~llm.adapters.fallback.FallbackLlmClient`.  Fallback chains are
    resolved recursively, so ``openai → anthropic → ollama`` becomes
    ``FallbackLlmClient(openai, [FallbackLlmClient(anthropic, [ollama])])``.
    """

    primary = _instantiate_provider(config)
    if config.fallback is None:
        return primary
    fallback_client = _resolve_fallback_chain(config.fallback)
    return FallbackLlmClient(primary=primary, fallbacks=[fallback_client])


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _instantiate_provider(config: LlmConfig) -> LlmClientProtocol:
    """Create the bare provider client (no fallback wrapping)."""

    provider = config.provider

    if provider == "local":
        return InMemoryLlmClient(provider=provider)

    if provider == "ollama":
        from llm.adapters.ollama_adapter import OllamaLlmClient

        return OllamaLlmClient(
            base_url=config.base_url or "http://localhost:11434",
        )

    if provider == "openai":
        try:
            from llm.adapters.openai_adapter import OpenAILlmClient
        except ImportError as exc:
            raise LlmConfigurationError(
                "The optional openai dependency is not installed. "
                "Install chili-backend[openai]."
            ) from exc
        return OpenAILlmClient(config)

    if provider == "anthropic":
        try:
            from llm.adapters.anthropic_adapter import AnthropicLlmClient
        except ImportError as exc:
            raise LlmConfigurationError(
                "The optional anthropic dependency is not installed. "
                "Install chili-backend[anthropic]."
            ) from exc
        return AnthropicLlmClient(config)

    raise LlmConfigurationError(
        f"Unknown llm provider: {provider!r}. "
        "Supported: 'local', 'ollama', 'openai', 'anthropic'."
    )


def _resolve_fallback_chain(config: LlmConfig) -> LlmClientProtocol:
    """Recursively resolve a fallback config, returning a (possibly wrapped) client."""

    primary = _instantiate_provider(config)
    if config.fallback is None:
        return primary
    inner_fallback = _resolve_fallback_chain(config.fallback)
    return FallbackLlmClient(primary=primary, fallbacks=[inner_fallback])
