from __future__ import annotations

from pathlib import Path

from config.loader import load_config


def test_llm_chain_loads_with_local_primary_openai_ollama_fallbacks() -> None:
    path = Path(__file__).parents[2] / "config" / "defaults" / "medicare_fraud_cms_desynpuf.yaml"
    config = load_config(path)

    assert config.llm is not None
    # Primary is now local so dev stack works without any external credentials.
    assert config.llm.provider == "local"
    assert config.llm.model == "local-default"
    assert config.llm.api_key_env_var is None

    # First-level fallback: openai
    assert config.llm.fallback is not None
    assert config.llm.fallback.provider == "openai"
    assert config.llm.fallback.model == "gpt-4o-mini"
    assert config.llm.fallback.api_key_env_var == "OPENAI_API_KEY"

    # Second-level fallback: ollama
    assert config.llm.fallback.fallback is not None
    assert config.llm.fallback.fallback.provider == "ollama"
    assert config.llm.fallback.fallback.model == "llama3.1:8b"
    assert config.llm.fallback.fallback.base_url == "http://localhost:11434"
