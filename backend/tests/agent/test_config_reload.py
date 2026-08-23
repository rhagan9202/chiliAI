"""Behavioral tests for worker dependency rebuild on ``config.updated`` (E6, T4).

Covers the frozen consumer semantics from the config-updated interface:

- the worker rebuilds its dependency set from the *active* config resolver
  after a ``config.updated`` delivery (payload is advisory);
- multiple pending events collapse into a single rebuild of the newest state;
- redelivery of an already-applied ``correlation_id`` is skipped (idempotent);
- a failed reload logs loudly and keeps the previous dependencies serving;
- ``run_worker`` swaps dependencies only *between* drain iterations — an
  in-flight drain always completes with the dependencies it started with.

Everything runs on the in-memory event bus; no Redis required.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent.coordinator import (
    CONFIG_UPDATED_EVENT_TYPE,
    ConfigReloadState,
    WorkerDependencies,
    apply_pending_config_updates,
    build_worker_dependencies,
    run_worker,
)
from agent.health import HealthState
from agent.models import HealthSettings, RetryPolicy
from agent.policy import StagePolicyRegistry
from config.store import write_active_pack
from events.types import ConfigUpdatedEvent

WORKER_LOGGER = "chili.worker"


def _write_pack(
    directory: Path,
    name: str,
    *,
    peer_stats: bool,
    analytics: dict[str, object] | None = None,
) -> Path:
    """Write a minimal valid domain pack and return its path."""

    pack: dict[str, object] = {
        "domain": {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "description": f"Test pack {name}",
        },
        "entities": [
            {
                "name": "thing",
                "display_label": "Thing",
                "icon": "box",
                "properties": {
                    "thing_id": {"type": "string", "display": "ID", "required": True}
                },
            }
        ],
        "relationships": [],
        "capabilities": {"peer_stats": peer_stats},
        **({"analytics": analytics} if analytics is not None else {}),
        "ingestion": {"sources": [{"type": "file_upload", "formats": ["txt"]}]},
        "alerts": {"thresholds": {}},
    }
    path = directory / f"{name}.json"
    path.write_text(json.dumps(pack), encoding="utf-8")
    return path


@pytest.fixture()
def worker_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pin the worker to in-memory adapters and a known active pack.

    The repo-level conftest already isolates ``CHILI_ACTIVE_PACK_STATE_PATH``
    per test; this fixture additionally targets a minimal ``pack_a`` (with
    ``peer_stats`` disabled, an observable config-derived toggle) and forces
    the in-memory event bus / workflow store regardless of ambient env.
    """

    monkeypatch.setenv("CHILI_EVENT_BUS_BACKEND", "in-memory")
    monkeypatch.setenv("CHILI_WORKFLOW_RUN_STORE_BACKEND", "in_memory")
    pack_a = _write_pack(tmp_path, "pack_a", peer_stats=False)
    monkeypatch.setenv("CHILI_CONFIG_PATH", str(pack_a))
    return tmp_path


@dataclass
class _FactoryStub:
    """Counting stand-in for ``build_worker_dependencies``."""

    result: WorkerDependencies | None = None
    error: Exception | None = None
    calls: int = 0

    def __call__(self) -> WorkerDependencies:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None, "factory stub needs a result"
        return self.result


def test_event_type_constant_matches_frozen_interface() -> None:
    assert CONFIG_UPDATED_EVENT_TYPE == "config.updated"
    assert ConfigUpdatedEvent(pack_name="p").event_type == CONFIG_UPDATED_EVENT_TYPE


def test_rebuild_on_event_reflects_new_active_config(
    worker_env: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A config.updated delivery rebuilds deps from the active-config resolver.

    Exercises the real resolution path: the active-pack pointer written by
    the config API (pointer > ``CHILI_CONFIG_PATH``) retargets the rebuild,
    and the payload itself is advisory.
    """

    deps = build_worker_dependencies()
    assert deps.peer_stats_enabled is False

    pack_b = _write_pack(worker_env, "pack_b", peer_stats=True)
    write_active_pack(pack_b, pack_name="pack_b")
    event = ConfigUpdatedEvent(
        pack_name="pack_b",
        pack_path=str(pack_b),
        previous_pack_name="pack_a",
        reason="switch",
    )
    deps.event_bus.publish(event)

    state = ConfigReloadState()
    with caplog.at_level(logging.INFO, logger=WORKER_LOGGER):
        rebuilt = apply_pending_config_updates(deps, state=state)

    assert rebuilt is not deps
    assert rebuilt.peer_stats_enabled is True
    assert state.last_applied_correlation_id == event.correlation_id
    assert "Worker dependencies rebuilt for domain pack 'pack_b'" in caplog.text


def test_no_pending_event_keeps_current_deps_without_rebuild(
    worker_env: Path,
) -> None:
    deps = build_worker_dependencies()
    stub = _FactoryStub(result=deps)
    state = ConfigReloadState()

    assert apply_pending_config_updates(deps, state=state, deps_factory=stub) is deps
    assert stub.calls == 0
    assert state.last_applied_correlation_id is None


def test_pending_events_collapse_into_single_rebuild(worker_env: Path) -> None:
    """Several queued config.updated events trigger exactly one rebuild."""

    deps = build_worker_dependencies()
    replacement = build_worker_dependencies()
    stub = _FactoryStub(result=replacement)
    events = [
        ConfigUpdatedEvent(pack_name=f"pack_{index}", reason="switch")
        for index in range(3)
    ]
    for event in events:
        deps.event_bus.publish(event)

    state = ConfigReloadState()
    rebuilt = apply_pending_config_updates(deps, state=state, deps_factory=stub)

    assert rebuilt is replacement
    assert stub.calls == 1
    # The newest pending event wins the idempotency bookkeeping.
    assert state.last_applied_correlation_id == events[-1].correlation_id

    # All three deliveries were acked on the old bus — polling it again does
    # not rebuild a second time.
    assert (
        apply_pending_config_updates(deps, state=state, deps_factory=stub)
        is deps
    )
    assert stub.calls == 1


def test_failed_reload_logs_loudly_and_retains_old_deps(
    worker_env: Path, caplog: pytest.LogCaptureFixture
) -> None:
    deps = build_worker_dependencies()
    stub = _FactoryStub(error=RuntimeError("boom: config invalid"))
    event = ConfigUpdatedEvent(pack_name="pack_broken", reason="apply")
    deps.event_bus.publish(event)

    state = ConfigReloadState()
    with caplog.at_level(logging.ERROR, logger=WORKER_LOGGER):
        result = apply_pending_config_updates(deps, state=state, deps_factory=stub)

    # Old dependencies keep serving; the failed delivery never marks state.
    assert result is deps
    assert stub.calls == 1
    assert state.last_applied_correlation_id is None
    assert "CONFIG RELOAD FAILED" in caplog.text
    assert "pack_broken" in caplog.text

    # The delivery was still acked: no redelivery hot-loop on the next poll.
    assert (
        apply_pending_config_updates(deps, state=state, deps_factory=stub)
        is deps
    )
    assert stub.calls == 1


def test_redelivered_correlation_id_is_idempotent(
    worker_env: Path, caplog: pytest.LogCaptureFixture
) -> None:
    deps = build_worker_dependencies()
    replacement = build_worker_dependencies()
    stub = _FactoryStub(result=replacement)
    state = ConfigReloadState()

    deps.event_bus.publish(
        ConfigUpdatedEvent(correlation_id="corr-dup", pack_name="pack_b")
    )
    current = apply_pending_config_updates(deps, state=state, deps_factory=stub)
    assert current is replacement
    assert stub.calls == 1

    # Simulate transport redelivery: the same correlation_id arrives again on
    # the (now current) bus. The rebuild is skipped.
    current.event_bus.publish(
        ConfigUpdatedEvent(correlation_id="corr-dup", pack_name="pack_b")
    )
    with caplog.at_level(logging.INFO, logger=WORKER_LOGGER):
        again = apply_pending_config_updates(current, state=state, deps_factory=stub)

    assert again is replacement
    assert stub.calls == 1
    assert state.last_applied_correlation_id == "corr-dup"
    assert "skipping" in caplog.text


def test_run_worker_swaps_deps_only_between_drain_iterations(
    worker_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An event arriving mid-drain takes effect only at the next iteration.

    The first drain iteration publishes ``config.updated`` while it is still
    in flight (an event handler is running). The worker must finish that
    iteration with the original dependencies and dispatch every subsequent
    iteration with the rebuilt set.
    """

    deps_v1 = build_worker_dependencies()
    deps_v2 = build_worker_dependencies()
    build_calls = 0

    def fake_build() -> WorkerDependencies:
        nonlocal build_calls
        build_calls += 1
        return deps_v1 if build_calls == 1 else deps_v2

    seen: list[WorkerDependencies] = []

    async def fake_drain(
        deps: WorkerDependencies,
        *,
        policy: RetryPolicy,
        stage_policy_registry: StagePolicyRegistry,
        health_state: HealthState,
    ) -> int:
        seen.append(deps)
        if len(seen) == 1:
            # config.updated lands while this drain iteration is mid-flight.
            deps.event_bus.publish(
                ConfigUpdatedEvent(pack_name="pack_b", reason="switch")
            )
        return 1

    monkeypatch.setattr("agent.coordinator.build_worker_dependencies", fake_build)
    monkeypatch.setattr("agent.coordinator._drain_once", fake_drain)

    async def _run() -> None:
        worker_task = asyncio.create_task(
            run_worker(health_settings=HealthSettings(port=18143))
        )
        try:
            for _ in range(500):
                if len(seen) >= 3:
                    break
                await asyncio.sleep(0.01)
        finally:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task

    with caplog.at_level(logging.INFO, logger=WORKER_LOGGER):
        asyncio.run(_run())

    assert len(seen) >= 3
    # The in-flight iteration completed with the original dependencies.
    assert seen[0] is deps_v1
    # Every iteration after the swap point runs with the rebuilt set.
    assert all(iteration_deps is deps_v2 for iteration_deps in seen[1:])
    # Exactly one rebuild happened (initial build + one hot-swap).
    assert build_calls == 2
    assert "Worker dependencies rebuilt for domain pack 'pack_b'" in caplog.text


def test_the_worker_honours_the_packs_risk_settings(worker_env: Path) -> None:
    """The worker scores the batches, so it must use the pack's risk settings.

    It previously passed none of them to `create_risk_service` and silently used
    library defaults. Harmless while no pack overrode them — and invisible for
    the same reason, since removing the wiring broke no test here.

    `min_risk_signals` is the one that matters most: it was a hardcoded 2 that
    zeroed the entire risk pipeline whenever a pack's configured metrics
    outnumbered the ones its data could produce.
    """
    pack = _write_pack(
        worker_env,
        "risk_pack",
        peer_stats=True,
        analytics={
            "min_risk_signals": 1,
            "medium_risk_threshold": 0.4,
            "high_risk_threshold": 0.7,
        },
    )
    write_active_pack(pack, pack_name="risk_pack")

    deps = build_worker_dependencies()

    risk_service = deps.risk_service
    assert risk_service is not None
    assert risk_service.min_signals == 1
    assert risk_service.default_medium_risk_threshold == 0.4
    assert risk_service.default_high_risk_threshold == 0.7
