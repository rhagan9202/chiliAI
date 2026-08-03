"""Tests for the domain hot-swap core in ``api.dependencies`` (config.05).

Covers: the singleton registry regression guard (every functools cache site
in ``api/dependencies.py`` must be registered), post-swap freshness of the
config singleton / DI singletons / rebuilt ``app.state.api_state``, the
generation token, swap-once-success rollback behavior, the app.state
memoizer/swap race (red-cell M2), the boot-time pointer resolution (M1),
and the relocated production auth guardrail (C1).
"""

from __future__ import annotations

import ast
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import api.dependencies as dependencies
from api.app import create_app
from api.state import ApiState
from config.loader import ConfigLoadError, load_config
from config.schema import AuthConfig, DomainConfig
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


# Both functools cache factories memoize process-wide; either would let a
# singleton survive a swap if unregistered.
_CACHE_FACTORY_NAMES = frozenset({"lru_cache", "cache"})


def _cache_decorator_bindings(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Return (direct decorator names, functools module aliases) in ``tree``.

    Resolves aliased imports (``from functools import lru_cache as lc``,
    ``import functools as ft``) so a renamed cache decorator cannot dodge the
    registry guard.
    """
    direct: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "functools":
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "functools":
            for alias in node.names:
                if alias.name in _CACHE_FACTORY_NAMES:
                    direct.add(alias.asname or alias.name)
    return direct, modules


def _is_cache_decorator(node: ast.expr, direct: set[str], modules: set[str]) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id in direct
    if isinstance(target, ast.Attribute):
        return (
            isinstance(target.value, ast.Name)
            and target.value.id in modules
            and target.attr in _CACHE_FACTORY_NAMES
        )
    return False


def _cache_decorated_functions_in_source(source: str) -> set[str]:
    tree = ast.parse(source)
    direct, modules = _cache_decorator_bindings(tree)
    decorated: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(
                _is_cache_decorator(dec, direct, modules)
                for dec in node.decorator_list
            ):
                decorated.add(node.name)
    return decorated


def test_ast_guard_catches_cache_and_aliased_decorators() -> None:
    """The guard itself must see functools.cache and aliased imports (m1)."""
    source = "\n".join(
        [
            "import functools",
            "import functools as ft",
            "from functools import cache, lru_cache as lc",
            "@lc(maxsize=1)",
            "def a() -> None: ...",
            "@cache",
            "def b() -> None: ...",
            "@functools.cache",
            "def c() -> None: ...",
            "@ft.lru_cache(maxsize=1)",
            "def d() -> None: ...",
            "@property",
            "def e() -> None: ...",
        ]
    )
    assert _cache_decorated_functions_in_source(source) == {"a", "b", "c", "d"}


def test_registry_covers_every_cache_site_in_dependencies() -> None:
    """Adding a functools-cached singleton without registering it must fail.

    An unregistered singleton would silently survive a domain hot-swap and
    keep serving the previous pack's backends.
    """
    decorated = _cache_decorated_functions_in_source(
        DEPENDENCIES_SOURCE.read_text(encoding="utf-8")
    )
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
        "audit_log_service": object(),
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


# ---------------------------------------------------------------------------
# app.state memoizer vs. swap race (red-cell M2)
# ---------------------------------------------------------------------------


def _request_for(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app})


def test_stale_memoizer_build_is_discarded_when_swap_completes_mid_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M2: a per-app memoizer build that races a swap is never memoized.

    Deterministic version of the threadpool interleaving: a request thread
    builds an api_state against the old pack, the locked reset completes
    before the memoizer write, and the write must then discard the stale
    candidate and rebuild against the new pack — instead of poisoning
    ``app.state`` with an old-pack object until the next swap.
    """
    app = FastAPI()
    real_create_api_state = dependencies.create_api_state
    build_count = 0

    def racing_create_api_state(
        domain_config: DomainConfig | None = None,
        *,
        rag_service: RagServiceProtocol | None = None,
    ) -> ApiState:
        nonlocal build_count
        build_count += 1
        state = real_create_api_state(domain_config, rag_service=rag_service)
        if build_count == 1:
            # The swap completes between this (old-pack) build finishing and
            # the memoizer write reacquiring the lock.
            dependencies.reset_domain_config_caches()
        return state

    monkeypatch.setattr(dependencies, "create_api_state", racing_create_api_state)

    resolved = dependencies.get_api_state(_request_for(app))

    assert build_count == 2, "stale first build must be discarded and rebuilt"
    assert app.state.api_state is resolved


def test_memoizer_returns_existing_state_without_rebuilding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fast path returns the app-attached object without any factory call."""
    app = FastAPI()

    def exploding_create_api_state(
        domain_config: DomainConfig | None = None,
        *,
        rag_service: RagServiceProtocol | None = None,
    ) -> ApiState:
        raise AssertionError("factory must not run when state is memoized")

    request = _request_for(app)
    first = dependencies.get_api_state(request)
    monkeypatch.setattr(dependencies, "create_api_state", exploding_create_api_state)
    assert dependencies.get_api_state(request) is first


def test_repository_memoizers_are_swap_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The repository memoizers share the same guarded write path (M2).

    ``get_case_repository``'s factory resolves ``get_connection_provider``;
    triggering a swap from inside that resolution simulates a reset completing
    while the repository build is in flight.
    """
    app = FastAPI()
    build_count = 0

    def racing_provider() -> None:
        nonlocal build_count
        build_count += 1
        if build_count == 1:
            dependencies.reset_domain_config_caches()
        return None  # in-memory repository path

    monkeypatch.setattr(dependencies, "get_connection_provider", racing_provider)

    resolved = dependencies.get_case_repository(_request_for(app))

    assert build_count == 2, "stale first build must be discarded and rebuilt"
    assert app.state.case_repository is resolved


# ---------------------------------------------------------------------------
# Production auth guardrail — public swap-facing symbol (red-cell C1)
# ---------------------------------------------------------------------------


def test_guardrail_rejects_disabled_auth_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pack without auth must be rejected before activation under production."""
    monkeypatch.setenv("CHILI_ENV", "production")
    with pytest.raises(RuntimeError, match="AuthConfig.enabled must be True"):
        dependencies.enforce_production_guardrail(None)
    with pytest.raises(RuntimeError, match="AuthConfig.enabled must be True"):
        dependencies.enforce_production_guardrail(AuthConfig(enabled=False))


def test_guardrail_rejects_incomplete_auth_in_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILI_ENV", "staging")
    with pytest.raises(RuntimeError, match="missing required fields"):
        dependencies.enforce_production_guardrail(AuthConfig(enabled=True))


def test_guardrail_is_a_noop_under_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHILI_ENV", "local")
    dependencies.enforce_production_guardrail(None)  # must not raise


def test_app_module_uses_the_dependencies_guardrail() -> None:
    """C1 freeze: api.app must consume the public symbol T3 also consumes."""
    import api.app as app_module

    assert (
        app_module.enforce_production_guardrail
        is dependencies.enforce_production_guardrail
    )
    assert app_module.load_chili_environment is dependencies.load_chili_environment


# ---------------------------------------------------------------------------
# Boot-time resolution matches what DI serves (red-cell M1)
# ---------------------------------------------------------------------------


def test_create_app_boot_follows_the_active_pack_pointer() -> None:
    """Boot must validate and serve the pointer's pack, not just env config."""
    write_active_pack(FOOD_YAML, pack_name="food_supply_chain")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/config/domain")
        assert response.status_code == 200
        assert response.json()["domain"]["name"] == "food_supply_chain"


def test_create_app_boot_fails_loudly_on_poisoned_pointer(tmp_path: Path) -> None:
    """A pointer to an invalid pack must fail startup, not serve unvalidated."""
    poisoned = tmp_path / "poisoned_pack.yaml"
    poisoned.write_text("domain: {name: broken}\n", encoding="utf-8")
    # write_active_pack only guards existence; validation is the boot's job.
    write_active_pack(poisoned)
    with pytest.raises(ConfigLoadError):
        create_app()


def test_create_app_boots_a_pointer_only_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a resolvable pointer, boot must not require CHILI_CONFIG_PATH."""
    monkeypatch.delenv("CHILI_CONFIG_PATH", raising=False)
    write_active_pack(MEDICARE_YAML, pack_name="medicare_fraud")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/config/domain")
        assert response.status_code == 200
        assert response.json()["domain"]["name"] == "medicare_fraud"
