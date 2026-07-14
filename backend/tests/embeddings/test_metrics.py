"""Tests for embeddings usage metrics."""

from __future__ import annotations

from prometheus_client import REGISTRY

from embeddings.metrics import estimate_tokens, record_embedding_usage


def _sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def test_estimate_tokens_rounds_up_and_floors_at_one() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_record_embedding_usage_increments_counters() -> None:
    labels = {"provider": "metrics-test", "model": "metrics-model-a"}
    token_labels = {
        **labels,
        "knowledge_base_id": "kb-metrics",
        "source": "reported",
    }
    requests_before = _sample("embedding_requests_total", labels)
    hits_before = _sample("embedding_texts_total", {**labels, "cache_result": "hit"})
    misses_before = _sample(
        "embedding_texts_total", {**labels, "cache_result": "miss"}
    )
    tokens_before = _sample("embedding_tokens_total", token_labels)

    record_embedding_usage(
        provider="metrics-test",
        model_name="metrics-model-a",
        knowledge_base_id="kb-metrics",
        cache_hits=2,
        cache_misses=3,
        tokens=42,
        token_source="reported",
    )

    assert _sample("embedding_requests_total", labels) - requests_before == 1.0
    assert (
        _sample("embedding_texts_total", {**labels, "cache_result": "hit"})
        - hits_before
        == 2.0
    )
    assert (
        _sample("embedding_texts_total", {**labels, "cache_result": "miss"})
        - misses_before
        == 3.0
    )
    assert _sample("embedding_tokens_total", token_labels) - tokens_before == 42.0


def test_record_embedding_usage_skips_empty_series() -> None:
    labels = {"provider": "metrics-test", "model": "metrics-model-zero"}

    record_embedding_usage(
        provider="metrics-test",
        model_name="metrics-model-zero",
        knowledge_base_id=None,
        cache_hits=0,
        cache_misses=0,
        tokens=0,
        token_source="cached",
    )

    assert _sample("embedding_requests_total", labels) == 1.0
    assert (
        REGISTRY.get_sample_value(
            "embedding_texts_total", {**labels, "cache_result": "hit"}
        )
        is None
    )
    assert (
        REGISTRY.get_sample_value(
            "embedding_tokens_total",
            {**labels, "knowledge_base_id": "none", "source": "cached"},
        )
        is None
    )
