"""Prometheus usage counters and token estimation for embeddings (BL-019)."""

from __future__ import annotations

import math
from typing import Literal

from prometheus_client import Counter

__all__ = [
    "TokenSource",
    "embedding_requests_total",
    "embedding_texts_total",
    "embedding_tokens_total",
    "estimate_tokens",
    "record_embedding_usage",
]

TokenSource = Literal["reported", "estimated", "cached"]

_CHARS_PER_TOKEN_ESTIMATE = 4

embedding_requests_total: Counter = Counter(
    "embedding_requests_total",
    "Total embed() calls served by the embeddings service.",
    ["provider", "model"],
)

embedding_texts_total: Counter = Counter(
    "embedding_texts_total",
    "Total texts submitted for embedding, split by cache result.",
    ["provider", "model", "cache_result"],
)

embedding_tokens_total: Counter = Counter(
    "embedding_tokens_total",
    "Embedding tokens consumed, provider-reported or estimated.",
    ["provider", "model", "knowledge_base_id", "source"],
)


def estimate_tokens(content: str) -> int:
    """Estimate token usage conservatively without a tokenizer dependency."""

    return max(1, math.ceil(len(content) / _CHARS_PER_TOKEN_ESTIMATE))


def record_embedding_usage(
    *,
    provider: str,
    model_name: str,
    knowledge_base_id: str | None,
    cache_hits: int,
    cache_misses: int,
    tokens: int,
    token_source: TokenSource,
) -> None:
    """Record one embed() call on the shared default Prometheus registry."""

    embedding_requests_total.labels(provider=provider, model=model_name).inc()
    if cache_hits > 0:
        embedding_texts_total.labels(
            provider=provider, model=model_name, cache_result="hit"
        ).inc(cache_hits)
    if cache_misses > 0:
        embedding_texts_total.labels(
            provider=provider, model=model_name, cache_result="miss"
        ).inc(cache_misses)
    if tokens > 0:
        embedding_tokens_total.labels(
            provider=provider,
            model=model_name,
            knowledge_base_id=knowledge_base_id or "none",
            source=token_source,
        ).inc(tokens)
