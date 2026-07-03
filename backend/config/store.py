"""File-backed active domain-pack pointer store.

Persists a small JSON pointer identifying the currently active domain pack so
domain hot-swaps survive process restarts and propagate between the API and
worker containers. Both containers mount the same ``chili-object-data`` volume
at ``/app/data``, so the default state path (``data/config/active_pack.json``,
resolved relative to the process working directory, ``/app`` in containers) is
a shared channel: the API writes the pointer on ``POST /config/apply|switch``
and the worker's next dependency rebuild follows it.

The pointer is deliberately **not** routed through the config-derived
``ObjectStore`` singleton: the pointer must be readable *before* any domain
configuration is loaded (the object-store backend itself comes from the config
being resolved), which would be circular. A plain state file with an atomic
temp-file + ``os.replace`` write gives the same shared-volume durability
without the bootstrap cycle.

Resolution precedence (see :func:`resolve_config_path`):

1. Active-pack pointer (this store), when one has been written.
2. ``CHILI_CONFIG_PATH`` environment variable.
3. Error (``ActivePackStoreError``).

Set ``CHILI_ACTIVE_PACK_STATE_PATH`` to relocate the state file (tests point it
at a temp directory for isolation; :func:`clear_active_pack` reverts a
deployment to plain env-based resolution).
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

__all__ = [
    "ActivePackPointer",
    "ActivePackStoreError",
    "CONFIG_PATH_ENV_VAR",
    "DEFAULT_STATE_PATH",
    "STATE_PATH_ENV_VAR",
    "clear_active_pack",
    "read_active_pack",
    "resolve_config_path",
    "resolve_state_path",
    "write_active_pack",
]

STATE_PATH_ENV_VAR = "CHILI_ACTIVE_PACK_STATE_PATH"
CONFIG_PATH_ENV_VAR = "CHILI_CONFIG_PATH"
DEFAULT_STATE_PATH = Path("data/config/active_pack.json")


class ActivePackStoreError(Exception):
    """Raised when the active-pack pointer cannot be read, written, or resolved."""


class ActivePackPointer(BaseModel):
    """Persisted pointer to the currently active domain pack."""

    config_path: str
    pack_name: str | None = None
    updated_at: datetime


def resolve_state_path() -> Path:
    """Return the pointer state-file path (env override > shared default)."""
    raw = os.environ.get(STATE_PATH_ENV_VAR)
    if raw is not None and raw.strip():
        return Path(raw)
    return DEFAULT_STATE_PATH


def read_active_pack() -> ActivePackPointer | None:
    """Return the persisted active-pack pointer, or ``None`` when absent.

    Raises ``ActivePackStoreError`` when a pointer file exists but cannot be
    read or parsed — a corrupt pointer fails loudly instead of silently
    reverting the deployment to a different domain.
    """
    state_path = resolve_state_path()
    if not state_path.is_file():
        return None
    try:
        raw = state_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ActivePackStoreError(
            f"Cannot read active-pack state file {state_path}: {exc}"
        ) from exc
    try:
        return ActivePackPointer.model_validate_json(raw)
    except ValidationError as exc:
        raise ActivePackStoreError(
            f"Corrupt active-pack state file {state_path}: {exc}"
        ) from exc


def write_active_pack(
    config_path: str | Path,
    *,
    pack_name: str | None = None,
) -> ActivePackPointer:
    """Atomically persist ``config_path`` as the active domain pack.

    Callers MUST have fully validated the pack first (``load_config(path)``) —
    this store only guards the cheap invariant that the target file exists, so
    a persisted pointer is always resolvable (swap-once-success: validate,
    then persist, then reset caches).

    The write is atomic (unique temp file in the state directory + ``os.replace``),
    so a concurrent reader sees either the previous pointer or the new one,
    never a partial file. Raises ``ActivePackStoreError`` on a missing target
    or filesystem failure.
    """
    target = Path(config_path)
    if not target.is_file():
        raise ActivePackStoreError(
            f"Cannot activate '{target}': config file does not exist."
        )
    pointer = ActivePackPointer(
        config_path=str(target),
        pack_name=pack_name,
        updated_at=datetime.now(timezone.utc),
    )
    state_path = resolve_state_path()
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=state_path.parent, prefix=".active_pack.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(pointer.model_dump_json())
            os.replace(tmp_name, state_path)
        except OSError:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ActivePackStoreError(
            f"Cannot write active-pack state file {state_path}: {exc}"
        ) from exc
    return pointer


def clear_active_pack() -> bool:
    """Remove the active-pack pointer; return whether one existed.

    After clearing, :func:`resolve_config_path` falls back to
    ``CHILI_CONFIG_PATH``.
    """
    state_path = resolve_state_path()
    try:
        state_path.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ActivePackStoreError(
            f"Cannot remove active-pack state file {state_path}: {exc}"
        ) from exc
    return True


def resolve_config_path() -> Path:
    """Return the active domain-config path: pointer > env > error.

    Raises ``ActivePackStoreError`` when no pointer has been written and
    ``CHILI_CONFIG_PATH`` is unset.
    """
    pointer = read_active_pack()
    if pointer is not None:
        return Path(pointer.config_path)
    env_path = os.environ.get(CONFIG_PATH_ENV_VAR)
    if env_path:
        return Path(env_path)
    raise ActivePackStoreError(
        "No active-pack pointer has been written and CHILI_CONFIG_PATH is not set."
    )
