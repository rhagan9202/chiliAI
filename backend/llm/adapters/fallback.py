"""Fallback decorator that tries an ordered list of llm clients."""

from __future__ import annotations

import logging

from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmProviderError
from llm.models import GenerationRequest, GenerationResult


logger = logging.getLogger(__name__)


class FallbackLlmClient:
    """Try `primary`; on transient failure try each entry of `fallbacks` in order.

    Implements `LlmClientProtocol`. Constructed by the factory when
    `LlmConfig.fallback` is set.
    """

    def __init__(
        self,
        *,
        primary: LlmClientProtocol,
        fallbacks: list[LlmClientProtocol],
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks

    def generate(self, request: GenerationRequest) -> GenerationResult:
        chain: list[LlmClientProtocol] = [self._primary, *self._fallbacks]
        last_error: Exception | None = None
        for index, client in enumerate(chain):
            try:
                return client.generate(request)
            except LlmProviderError as exc:
                last_error = exc
                logger.warning(
                    "llm provider %d/%d failed: %s",
                    index + 1,
                    len(chain),
                    exc,
                )
        raise LlmProviderError(
            f"All {len(chain)} llm providers exhausted."
        ) from last_error


__all__ = ["FallbackLlmClient"]
