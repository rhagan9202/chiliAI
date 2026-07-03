"""Tests for config.store — the file-backed active domain-pack pointer.

Covers the frozen T2 store contract: pointer > env precedence, atomic
temp-file + ``os.replace`` writes, loud failures on corrupt state, and the
``load_active_config`` loader wrapper.
"""

from __future__ import annotations

import json
import os
from datetime import timezone
from pathlib import Path

import pytest

from config.loader import ConfigLoadError, load_active_config
from config.store import (
    CONFIG_PATH_ENV_VAR,
    DEFAULT_STATE_PATH,
    STATE_PATH_ENV_VAR,
    ActivePackStoreError,
    clear_active_pack,
    read_active_pack,
    resolve_config_path,
    resolve_state_path,
    write_active_pack,
)

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"
FOOD_YAML = DEFAULTS_DIR / "food_supply_chain.yaml"


@pytest.fixture
def state_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the store at an isolated per-test state file."""
    path = tmp_path / "state" / "active_pack.json"
    monkeypatch.setenv(STATE_PATH_ENV_VAR, str(path))
    return path


# ---------------------------------------------------------------------------
# resolve_state_path
# ---------------------------------------------------------------------------


class TestResolveStatePath:
    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(STATE_PATH_ENV_VAR, "/somewhere/state.json")
        assert resolve_state_path() == Path("/somewhere/state.json")

    def test_default_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(STATE_PATH_ENV_VAR, raising=False)
        assert resolve_state_path() == DEFAULT_STATE_PATH

    def test_blank_env_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(STATE_PATH_ENV_VAR, "   ")
        assert resolve_state_path() == DEFAULT_STATE_PATH


# ---------------------------------------------------------------------------
# write_active_pack / read_active_pack
# ---------------------------------------------------------------------------


class TestWriteReadRoundtrip:
    def test_read_returns_none_when_absent(self, state_path: Path) -> None:
        assert read_active_pack() is None

    def test_roundtrip(self, state_path: Path) -> None:
        written = write_active_pack(FOOD_YAML, pack_name="food_supply_chain")
        read_back = read_active_pack()
        assert read_back is not None
        assert read_back.config_path == str(FOOD_YAML)
        assert read_back.pack_name == "food_supply_chain"
        assert read_back == written

    def test_pack_name_defaults_to_none(self, state_path: Path) -> None:
        write_active_pack(MEDICARE_YAML)
        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.pack_name is None

    def test_updated_at_is_tz_aware_utc(self, state_path: Path) -> None:
        pointer = write_active_pack(MEDICARE_YAML)
        assert pointer.updated_at.tzinfo is not None
        assert pointer.updated_at.utcoffset() == timezone.utc.utcoffset(None)

    def test_accepts_str_path(self, state_path: Path) -> None:
        write_active_pack(str(MEDICARE_YAML))
        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.config_path == str(MEDICARE_YAML)

    def test_creates_parent_directories(self, state_path: Path) -> None:
        assert not state_path.parent.exists()
        write_active_pack(MEDICARE_YAML)
        assert state_path.is_file()

    def test_rejects_missing_config_file(self, state_path: Path) -> None:
        with pytest.raises(ActivePackStoreError, match="does not exist"):
            write_active_pack(state_path.parent / "nope.yaml")
        assert read_active_pack() is None  # nothing persisted

    def test_overwrite_replaces_previous_pointer(self, state_path: Path) -> None:
        write_active_pack(MEDICARE_YAML, pack_name="medicare_fraud")
        write_active_pack(FOOD_YAML, pack_name="food_supply_chain")
        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.config_path == str(FOOD_YAML)
        assert pointer.pack_name == "food_supply_chain"


class TestReadFailuresAreLoud:
    def test_corrupt_json_raises(self, state_path: Path) -> None:
        state_path.parent.mkdir(parents=True)
        state_path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ActivePackStoreError, match="Corrupt"):
            read_active_pack()

    def test_wrong_shape_raises(self, state_path: Path) -> None:
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"unexpected": True}), encoding="utf-8")
        with pytest.raises(ActivePackStoreError, match="Corrupt"):
            read_active_pack()

    def test_unreadable_file_raises(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_active_pack(MEDICARE_YAML)

        def raise_oserror(*args: object, **kwargs: object) -> str:
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", raise_oserror)
        with pytest.raises(ActivePackStoreError, match="Cannot read"):
            read_active_pack()


class TestWriteAtomicity:
    def test_failed_replace_keeps_previous_pointer_and_leaves_no_litter(
        self, state_path: Path
    ) -> None:
        write_active_pack(MEDICARE_YAML, pack_name="medicare_fraud")

        def raise_oserror(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(os, "replace", raise_oserror)
            with pytest.raises(ActivePackStoreError, match="Cannot write"):
                write_active_pack(FOOD_YAML, pack_name="food_supply_chain")

        # Old pointer survives untouched, and the temp file was cleaned up.
        pointer = read_active_pack()
        assert pointer is not None
        assert pointer.config_path == str(MEDICARE_YAML)
        assert sorted(p.name for p in state_path.parent.iterdir()) == [
            state_path.name
        ]


# ---------------------------------------------------------------------------
# clear_active_pack
# ---------------------------------------------------------------------------


class TestClearActivePack:
    def test_clear_returns_true_when_pointer_existed(self, state_path: Path) -> None:
        write_active_pack(MEDICARE_YAML)
        assert clear_active_pack() is True
        assert read_active_pack() is None

    def test_clear_returns_false_when_absent(self, state_path: Path) -> None:
        assert clear_active_pack() is False

    def test_clear_failure_raises(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_active_pack(MEDICARE_YAML)

        def raise_oserror(*args: object, **kwargs: object) -> None:
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "unlink", raise_oserror)
        with pytest.raises(ActivePackStoreError, match="Cannot remove"):
            clear_active_pack()


# ---------------------------------------------------------------------------
# resolve_config_path — pointer > env > error
# ---------------------------------------------------------------------------


class TestResolveConfigPathPrecedence:
    def test_pointer_wins_over_env(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(MEDICARE_YAML))
        write_active_pack(FOOD_YAML)
        assert resolve_config_path() == FOOD_YAML

    def test_env_fallback_when_no_pointer(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(MEDICARE_YAML))
        assert resolve_config_path() == MEDICARE_YAML

    def test_env_fallback_after_clear(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(MEDICARE_YAML))
        write_active_pack(FOOD_YAML)
        clear_active_pack()
        assert resolve_config_path() == MEDICARE_YAML

    def test_error_when_neither(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(CONFIG_PATH_ENV_VAR, raising=False)
        with pytest.raises(ActivePackStoreError, match="No active-pack pointer"):
            resolve_config_path()


# ---------------------------------------------------------------------------
# load_active_config — the loader wrapper over resolve_config_path
# ---------------------------------------------------------------------------


class TestLoadActiveConfig:
    def test_follows_pointer_over_env(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(MEDICARE_YAML))
        write_active_pack(FOOD_YAML)
        assert load_active_config().domain.name == "food_supply_chain"

    def test_env_fallback(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(MEDICARE_YAML))
        assert load_active_config().domain.name == "medicare_fraud"

    def test_store_error_reraised_as_config_load_error(
        self, state_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(CONFIG_PATH_ENV_VAR, raising=False)
        with pytest.raises(ConfigLoadError, match="No active-pack pointer"):
            load_active_config()

    def test_corrupt_pointer_reraised_as_config_load_error(
        self, state_path: Path
    ) -> None:
        state_path.parent.mkdir(parents=True)
        state_path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="Corrupt"):
            load_active_config()
