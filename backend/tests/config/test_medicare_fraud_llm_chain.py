from __future__ import annotations

from pathlib import Path

from config.loader import load_config


def test_llm_chain_loads_with_openai_primary_and_ollama_fallback() -> None:
    path = Path(__file__).parents[2] / "config" / "defaults" / "medicare_fraud_cms_desynpuf.yaml"
    config = load_config(path)

    assert config.llm is not None
    assert config.llm.provider == "openai"
    assert config.llm.model == "gpt-4o-mini"
    assert config.llm.fallback is not None
    assert config.llm.fallback.provider == "ollama"
    assert config.llm.fallback.model == "llama3.1:8b"
    assert config.llm.fallback.base_url == "http://localhost:11434"
