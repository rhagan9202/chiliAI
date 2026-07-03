"""Tests for the domain hot-swap core in ``api.dependencies`` (config.05).

Covers: the singleton registry regression guard (every ``@lru_cache`` site in
``api/dependencies.py`` must be registered), post-swap freshness of the
config singleton / DI singletons / rebuilt ``app.state.api_state``, the
generation token, and swap-once-success rollback behavior.
"""

from __future__ import annotations

import ast
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.dependencies as dependencies
from api.app import create_app
from api.state import ApiState
from config.loader import ConfigLoadError, load_config
from config.schema import DomainConfig
from config.store import ActivePackStoreError, write_active_pack
from rag.protocols import RagServiceProtocol

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"
FOOD_YAML = DEFAULTS_DIR / "food_supply_chain.yaml"

DEPENDENCIES_SOURCE = (
    Path(__file__).resolve().parent.parent.parent / "api" / "dependencies.py"
)


@pytest.fixture(autouse=True)
def isolate_config_caches() -> Iterator[None]:
    """Reset all config-derived singletons around every test in this module."""
    dependencies.reset_domain_config_caches()
    yield
    dependencies.reset_domain_config_caches()


# ---------------------------------------------------------------------------
# Registry regression guard
# ---------------------------------------------------------------------------


def _is_lru_cache_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id == "lru_cache"
    if isinstance(target, ast.Attribute):
        return target.attr == "lru_cache"
    return False


def _lru_cache_decorated_functions(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    decorated: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_is_lru_cache_decorator(dec) for dec in node.decorator_list):
                decorated.add(node.name)
    return decorated


def test_registry_covers_every_lru_cache_site_in_dependencies() -> None:
    """Adding an ``@lru_cache`` singleton without registering it must fail.

    An unregistered singleton would silently survive a domain hot-swap and
    keep serving the previous pack's backends.
    """
    decorated = _lru_cache_decorated_functions(DEPENDENCIES_SOURCE)
    registered = set(dependencies.CONFIG_CACHE_REGISTRY.keys())
    missing = decorated - registered
    stale = registered - decorated
    assert not missing, (
        f"@lru_cache singletons missing from CONFIG_CACHE_REGISTRY: {sorted(missing)}. "
        "Register them in api/dependencies.py so domain hot-swaps clear them."
    )
    assert not stale, (
        f"CONFIG_CACHE_REGISTRY entries with no @lru_cache site: {sorted(stale)}."
    )


def test_registry_entries_are_the_live_module_attributes() -> None:
    """The registry must hold the actual wrappers, not stale copies."""
    for name, wrapper in dependencies.CONFIG_CACHE_REGISTRY.items():
        assert getattr(dependencies, name) is wrapper, name


# ---------------------------------------------------------------------------
# Post-swap singleton freshness
# ---------------------------------------------------------------------------


def test_domain_config_follows_pointer_after_reset() -> None:
    assert dependencies.get_domain_config().domain.name == "medicare_fraud"

    write_active_pack(FOOD_YAML, pack_name="food_supply_chain")
    # Cached until the swap core clears it — in-flight resolutions keep the
    # old pack.
    assert dependencies.get_domain_config().domain.name == "medicare_fraud"

    dependencies.reset_domain_config_caches()
    assert dependencies.get_domain_config().domain.name == "food_supply_chain"


def test_reset_clears_every_registered_singleton() -> None:
    """The reset is all-or-nothing at the registry level: no cache survives."""
    # Populate a few caches (the cheap, in-memory-safe ones) so the reset has
    # live entries to clear; the assertion below still covers all 35 wrappers.
    dependencies.get_domain_config()
    dependencies.get_parser_registry()
    dependencies.get_object_store()
    dependencies.get_knowledge_base_repository()
    assert any(
        wrapper.cache_info().currsize > 0
        for wrapper in dependencies.CONFIG_CACHE_REGISTRY.values()
    )

    dependencies.reset_domain_config_caches()

    still_cached = [
        name
        for name, wrapper in dependencies.CONFIG_CACHE_REGISTRY.items()
        if wrapper.cache_info().currsize > 0
    ]
    assert still_cached == [], (
        f"Singletons survived the swap reset: {still_cached}"
    )


def test_reset_rebuilds_di_singletons() -> None:
    config_before = dependencies.get_domain_config()
    registry_before = dependencies.get_parser_registry()
    kb_repo_before = dependencies.get_knowledge_base_repository()
    object_store_before = dependencies.get_object_store()

    dependencies.reset_domain_config_caches()

    assert dependencies.get_domain_config() is not config_before
    assert dependencies.get_parser_registry() is not registry_before
    assert dependencies.get_knowledge_base_repository() is not kb_repo_before
    assert dependencies.get_object_store() is not object_store_before


def test_generation_token_is_monotonic() -> None:
    start = dependencies.get_config_generation()
    first = dependencies.reset_domain_config_caches()
    second = dependencies.reset_domain_config_caches()
    assert first == start + 1
    assert second == first + 1
    assert dependencies.get_config_generation() == second


def test_concurrent_resets_are_serialized() -> None:
    """The module lock serializes swaps: N resets bump the generation by N."""
    start = dependencies.get_config_generation()
    thread_count = 8
    barrier = threading.Barrier(thread_count)

    def do_reset() -> None:
        barrier.wait()
        dependencies.reset_domain_config_caches()

    threads = [threading.Thread(target=do_reset) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert dependencies.get_config_generation() == start + thread_count


# ---------------------------------------------------------------------------
# Per-app state purge + api_state rebuild
# ---------------------------------------------------------------------------


def test_reset_with_app_purges_config_derived_state_and_rebuilds_api_state() -> None:
    app = FastAPI()
    sentinels = {
        "api_state": object(),
        "evidence_pack_repository": object(),
        "case_repository": object(),
        "alert_repository": object(),
        "conversation_repository": object(),
        "policy_repository": object(),
    }
    for attr, value in sentinels.items():
        setattr(app.state, attr, value)

    dependencies.reset_domain_config_caches(app)

    for attr in sentinels:
        if attr == "api_state":
            continue
        assert getattr(app.state, attr, None) is None, f"{attr} not purged"
    assert isinstance(app.state.api_state, ApiState)
    assert app.state.api_state is not sentinels["api_state"]


def test_rebuilt_api_state_uses_the_new_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a swap, build_api_state composes ApiState from the new config."""
    seen_configs: list[DomainConfig | None] = []
    real_create_api_state = dependencies.create_api_state

    def recording_create_api_state(
        domain_config: DomainConfig | None = None,
        *,
        rag_service: RagServiceProtocol | None = None,
    ) -> ApiState:
        seen_configs.append(domain_config)
        return real_create_api_state(domain_config, rag_service=rag_service)

    monkeypatch.setattr(
        dependencies, "create_api_state", recording_create_api_state
    )

    app = FastAPI()
    write_active_pack(FOOD_YAML, pack_name="food_supply_chain")
    dependencies.reset_domain_config_caches(app)

    assert seen_configs, "api_state was not rebuilt"
    rebuilt_config = seen_configs[-1]
    assert rebuilt_config is not None
    assert rebuilt_config.domain.name == "food_supply_chain"


def test_build_api_state_falls_back_when_rag_composition_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_rag_service() -> RagServiceProtocol:
        raise RuntimeError("composition failed")

    monkeypatch.setattr(dependencies, "get_rag_service", broken_rag_service)
    state = dependencies.build_api_state()
    assert isinstance(state, ApiState)
    assert state.rag_service is not None  # seeded in-memory fallback


# ---------------------------------------------------------------------------
# End-to-end: created app hot-swaps in place
# ---------------------------------------------------------------------------


def test_created_app_serves_new_domain_after_swap() -> None:
    app = create_app()
    with TestClient(app) as client:
        before = client.get("/config/domain")
        assert before.status_code == 200
        assert before.json()["domain"]["name"] == "medicare_fraud"

        # Swap-once-success: the pack was validated by load_config in the
        # round-trip loader tests; persist the pointer, then reset.
        write_active_pack(FOOD_YAML, pack_name="food_supply_chain")
        dependencies.reset_domain_config_caches(app)

        after = client.get("/config/domain")
        assert after.status_code == 200
        assert after.json()["domain"]["name"] == "food_supply_chain"


# ---------------------------------------------------------------------------
# Swap-once-success rollback discipline
# ---------------------------------------------------------------------------


def test_failed_candidate_load_leaves_every_cache_untouched(tmp_path: Path) -> None:
    """Step 1 of swap-once-success: a candidate that fails validation mutates
    nothing — every singleton keeps serving the old pack."""
    config_before = dependencies.get_domain_config()
    object_store_before = dependencies.get_object_store()
    kb_repo_before = dependencies.get_knowledge_base_repository()
    generation_before = dependencies.get_config_generation()

    bad_candidate = tmp_path / "invalid_pack.yaml"
    bad_candidate.write_text("domain: {name: broken}\n", encoding="utf-8")
    with pytest.raises(ConfigLoadError):
        load_config(bad_candidate)

    assert dependencies.get_domain_config() is config_before
    assert dependencies.get_object_store() is object_store_before
    assert dependencies.get_knowledge_base_repository() is kb_repo_before
    assert dependencies.get_config_generation() == generation_before


def test_failed_pointer_write_leaves_every_cache_untouched(tmp_path: Path) -> None:
    config_before = dependencies.get_domain_config()
    object_store_before = dependencies.get_object_store()
    generation_before = dependencies.get_config_generation()

    with pytest.raises(ActivePackStoreError):
        write_active_pack(tmp_path / "missing_pack.yaml")

    # Steps 1–2 failing must not touch any cache: the old pack keeps serving.
    assert dependencies.get_domain_config() is config_before
    assert dependencies.get_object_store() is object_store_before
    assert dependencies.get_config_generation() == generation_before
