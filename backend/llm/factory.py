"""Factory for constructing an ``LlmClientProtocol`` from ``LlmConfig``.

Call :func:`create_llm_client` from dependency injection (``api/dependencies.py``)
and from the worker coordinator (``agent/coordinator.py``).  This is the single
authoritative place that knows which provider string maps to which adapter.
"""

from __future__ import annotations

import logging

from config.schema import LlmConfig
from llm.adapters.fallback import FallbackLlmClient
from llm.adapters.in_memory import InMemoryLlmClient
from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmConfigurationError


__all__ = ["create_llm_client"]

logger = logging.getLogger(__name__)


def create_llm_client(config: LlmConfig) -> LlmClientProtocol:
    """Construct an LlmClientProtocol from configuration, gracefully skipping
    providers that fail to construct (e.g. missing API key).

    If ``config.fallback`` is set the primary client is wrapped in a
    :class:`~llm.adapters.fallback.FallbackLlmClient`.  Fallback chains are
    resolved recursively, so ``openai → anthropic → ollama`` becomes
    ``FallbackLlmClient(openai, [FallbackLlmClient(anthropic, [ollama])])``.

    If the primary provider fails to construct (e.g. missing ``OPENAI_API_KEY``)
    the factory falls through to the configured fallback chain instead of
    propagating the error.  If every provider in the chain fails to construct
    a :exc:`~llm.exceptions.LlmConfigurationError` is raised with a clear
    description of all failures.
    """

    failures: list[tuple[str, str]] = []
    client = _build_chain(config, failures)
    if client is None:
        failure_detail = "; ".join(
            f"{provider!r}: {reason}" for provider, reason in failures
        )
        raise LlmConfigurationError(
            f"All LLM providers in the configured chain failed to construct: "
            f"[{failure_detail}]. "
            "Set required env vars (e.g. OPENAI_API_KEY) or configure a provider "
            "that does not require external credentials (e.g. 'local')."
        )
    return client


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_chain(
    config: LlmConfig,
    failures: list[tuple[str, str]],
) -> LlmClientProtocol | None:
    """Recursively build the provider chain.

    Appends ``(provider, error_message)`` to *failures* for each provider that
    fails to construct.  Returns the constructed client (possibly wrapped in
    :class:`~llm.adapters.fallback.FallbackLlmClient`), or ``None`` if every
    provider in this sub-chain failed to construct.
    """

    primary: LlmClientProtocol | None = None
    try:
        primary = _instantiate_provider(config)
    except LlmConfigurationError as exc:
        failures.append((config.provider, str(exc)))
        logger.warning(
            "llm provider %r failed to construct, skipping: %s",
            config.provider,
            exc,
        )

    fallback: LlmClientProtocol | None = None
    if config.fallback is not None:
        fallback = _build_chain(config.fallback, failures)

    if primary is not None and fallback is not None:
        return FallbackLlmClient(primary=primary, fallbacks=[fallback])
    if primary is not None:
        return primary
    # primary is None — return fallback (may itself be None if chain is exhausted)
    return fallback


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
