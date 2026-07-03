"""Configuration API router — serves domain config and manages domain packs.

Read routes (viewer) expose the active :class:`~config.schema.DomainConfig`,
feature flags, and the config JSON schema. Pack-management routes (admin)
implement the domain hot-swap surface (E4):

- ``GET /config/packs`` — list packs in the allowed config directories plus
  the active-pack resolution state.
- ``POST /config/validate`` — dry-run full validation (zero mutation).
- ``POST /config/apply`` — validate → persist pointer → swap caches → emit
  ``config.updated`` (reason ``"apply"``).
- ``POST /config/switch`` — same pipeline for activating a different pack
  (reason ``"switch"``).

Allowed config directories are ``config/defaults`` plus any directories in the
``CHILI_CONFIG_PACK_DIRS`` environment variable (``os.pathsep``-separated).
User-supplied pack references must resolve (symlinks followed) inside an
allowed directory — path traversal is rejected.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from api import dependencies
from api.config_models import (
    ActivePackState,
    ApplyPackRequest,
    ConfigSwapResponse,
    ConfigValidationIssue,
    PackListResponse,
    PackSummary,
    SwitchPackRequest,
    ValidatePackRequest,
    ValidatePackResponse,
)
from api.contracts import DomainFeaturesResponse
from api.dependencies import (
    get_domain_config,
    get_domain_config_features_payload,
    get_domain_config_schema_payload,
)
from api.middleware.rbac import require_role
from api.state import ApiState
from config.loader import ConfigLoadError, load_config
from config.schema import DomainConfig
from config.store import (
    CONFIG_PATH_ENV_VAR,
    ActivePackStoreError,
    read_active_pack,
    resolve_config_path,
    write_active_pack,
)
from events.types import ConfigUpdatedEvent

__all__ = ["PACK_DIRS_ENV_VAR", "router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["configuration"])

PACK_DIRS_ENV_VAR = "CHILI_CONFIG_PACK_DIRS"
_PACK_SUFFIXES = (".yaml", ".yml", ".json")
_DEFAULTS_DIR = Path(__file__).resolve().parents[2] / "config" / "defaults"


@router.get(
    "/domain",
    response_model=DomainConfig,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_domain(
    config: DomainConfig = Depends(get_domain_config),
) -> DomainConfig:
    """Return the active domain configuration."""
    return config


@router.get(
    "/features",
    response_model=DomainFeaturesResponse,
    dependencies=[Depends(require_role("viewer"))],
)
async def get_features(
    features: dict[str, object] = Depends(get_domain_config_features_payload),
) -> dict[str, object]:
    """Return feature flags and enabled page metadata for the frontend."""
    return features


@router.get("/domain/schema", dependencies=[Depends(require_role("viewer"))])
async def get_domain_schema(
    schema: dict[str, object] = Depends(get_domain_config_schema_payload),
) -> dict[str, object]:
    """Return the JSON schema for the domain configuration model."""
    return schema


# ---------------------------------------------------------------------------
# Pack management (admin): list / validate / apply / switch
# ---------------------------------------------------------------------------


def _allowed_pack_dirs() -> list[Path]:
    """Return the resolved directories a pack reference may live in."""
    dirs = [_DEFAULTS_DIR]
    raw = os.environ.get(PACK_DIRS_ENV_VAR, "")
    for part in raw.split(os.pathsep):
        if part.strip():
            dirs.append(Path(part.strip()))
    resolved: list[Path] = []
    for directory in dirs:
        real = directory.resolve()
        if real not in resolved:
            resolved.append(real)
    return resolved


def _inside_allowed(path: Path, allowed: list[Path]) -> bool:
    return any(path.is_relative_to(base) for base in allowed)


def _resolve_pack_reference(reference: str) -> Path:
    """Resolve a user-supplied pack reference to a file inside an allowed dir.

    Accepts either a bare pack name (file stem, optionally with a supported
    suffix) looked up in the allowed config directories, or an explicit path
    that must resolve — symlinks followed — inside an allowed directory.
    Raises 400 for traversal/unsupported references, 404 for missing packs.
    """
    cleaned = reference.strip()
    if not cleaned or "\x00" in cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pack reference must be a non-empty pack name or path.",
        )
    allowed = _allowed_pack_dirs()
    as_path = Path(cleaned)

    if len(as_path.parts) == 1 and cleaned not in (".", ".."):
        # Bare pack name: look it up inside the allowed directories only.
        if as_path.suffix and as_path.suffix.lower() not in _PACK_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported pack extension '{as_path.suffix}'. Use .yaml, .yml, or .json.",
            )
        file_names = (
            [cleaned]
            if as_path.suffix
            else [f"{cleaned}{suffix}" for suffix in _PACK_SUFFIXES]
        )
        for base in allowed:
            for file_name in file_names:
                resolved = (base / file_name).resolve()
                if _inside_allowed(resolved, allowed) and resolved.is_file():
                    return resolved
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pack '{cleaned}' not found in the allowed config directories.",
        )

    # Explicit path form: resolve (following symlinks) and containment-check.
    resolved = as_path.resolve()
    if resolved.suffix.lower() not in _PACK_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported pack extension '{resolved.suffix}'. Use .yaml, .yml, or .json.",
        )
    if not _inside_allowed(resolved, allowed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pack reference must resolve inside an allowed config directory.",
        )
    if not resolved.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pack '{cleaned}' not found.",
        )
    return resolved


class _PackParseError(Exception):
    """Raised when a pack file cannot be read or parsed into a mapping."""


def _parse_pack_file(path: Path) -> dict[str, object]:
    """Read + parse a pack file into a mapping (no validation)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _PackParseError(f"Cannot read pack file {path}: {exc}") from exc
    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            data: object = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
    except yaml.YAMLError as exc:
        raise _PackParseError(f"YAML parse error in {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise _PackParseError(f"JSON parse error in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise _PackParseError(f"Pack file {path} must contain a mapping at the top level.")
    return {str(key): value for key, value in data.items()}


def _validation_issues(exc: ValidationError) -> list[ConfigValidationIssue]:
    """Map a pydantic ValidationError to structured field-level issues."""
    issues: list[ConfigValidationIssue] = []
    for error in exc.errors(include_url=False):
        loc = [str(part) for part in error["loc"]]
        issues.append(
            ConfigValidationIssue(
                loc=loc,
                field=".".join(loc),
                message=error["msg"],
                error_type=error["type"],
            )
        )
    return issues


def _active_pack_state() -> tuple[Path | None, ActivePackState]:
    """Return the resolved active pack path and its resolution state."""
    try:
        pointer = read_active_pack()
    except ActivePackStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Active-pack pointer is unreadable: {exc}",
        ) from exc
    if pointer is not None:
        path = Path(pointer.config_path).resolve()
        return path, ActivePackState(
            config_path=str(path),
            pack_name=pointer.pack_name,
            source="pointer",
            updated_at=pointer.updated_at,
        )
    env_path = os.environ.get(CONFIG_PATH_ENV_VAR)
    if env_path:
        path = Path(env_path).resolve()
        return path, ActivePackState(config_path=str(path), source="env")
    return None, ActivePackState(source="none")


def _summarize_pack(path: Path, active_path: Path | None) -> PackSummary:
    """Fully validate one pack file and project it into a summary row."""
    domain_name: str | None = None
    display_name: str | None = None
    error: str | None = None
    try:
        pack_config = load_config(path)
    except ConfigLoadError as exc:
        error = str(exc)
    else:
        domain_name = pack_config.domain.name
        display_name = pack_config.domain.display_name
    return PackSummary(
        name=path.stem,
        file_name=path.name,
        path=str(path),
        domain_name=domain_name,
        display_name=display_name,
        valid=error is None,
        error=error,
        active=active_path is not None and path == active_path,
    )


def _current_pack_name() -> str | None:
    """Best-effort name of the pack serving right now (for previous_pack_name)."""
    try:
        pointer = read_active_pack()
    except ActivePackStoreError:
        pointer = None
    if pointer is not None and pointer.pack_name:
        return pointer.pack_name
    try:
        return dependencies.get_domain_config().domain.name
    except Exception:  # noqa: BLE001 — a broken current config must not block a repair swap
        return None


def _rag_degraded_to_fallback(request: Request) -> bool:
    """Detect whether the rebuilt api_state fell back to the seeded RAG pipeline.

    On successful composition ``build_api_state`` wires the (cached) live RAG
    service into ``app.state.api_state``, so an identity mismatch — or a
    composition that still raises — means the fallback is serving.
    """
    api_state = getattr(request.app.state, "api_state", None)
    if not isinstance(api_state, ApiState):
        return False
    try:
        live = dependencies.get_rag_service()
    except Exception:  # noqa: BLE001 — composition failure is exactly the degraded signal
        return True
    return api_state.rag_service is not live


def _publish_config_updated(
    new_config: DomainConfig,
    pack_path: Path,
    previous_pack_name: str | None,
    reason: str,
) -> bool:
    """Publish ``config.updated`` after a durable swap; never fail the request."""
    try:
        event_bus = dependencies.get_event_bus()
        event_bus.publish(
            ConfigUpdatedEvent(
                pack_name=new_config.domain.name,
                pack_path=str(pack_path),
                previous_pack_name=previous_pack_name,
                reason=reason,
                source="api.config",
            )
        )
    except Exception:  # noqa: BLE001 — the swap already succeeded; surface via event_published
        logger.exception(
            "Failed to publish config.updated after %s of pack '%s'.",
            reason,
            new_config.domain.name,
        )
        return False
    return True


def _activate_pack(
    candidate: Path,
    *,
    reason: Literal["apply", "switch"],
    request: Request,
) -> ConfigSwapResponse:
    """Swap-once-success pipeline: validate → persist pointer → reset → emit.

    A failure in validation or pointer persistence mutates nothing — the old
    pack keeps serving (see the swap-core contract in api.dependencies).
    """
    previous_pack_name = _current_pack_name()
    try:
        new_config = load_config(candidate)
    except ConfigLoadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pack validation failed; active configuration unchanged. {exc}",
        ) from exc
    try:
        write_active_pack(candidate, pack_name=new_config.domain.name)
    except ActivePackStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not persist the active-pack pointer; active configuration unchanged. {exc}",
        ) from exc
    generation = dependencies.reset_domain_config_caches(request.app)
    rag_degraded = _rag_degraded_to_fallback(request)
    event_published = _publish_config_updated(
        new_config, candidate, previous_pack_name, reason
    )
    return ConfigSwapResponse(
        status="applied",
        reason=reason,
        pack_name=new_config.domain.name,
        pack_path=str(candidate),
        previous_pack_name=previous_pack_name,
        generation=generation,
        rag_degraded_to_fallback=rag_degraded,
        event_published=event_published,
    )


@router.get(
    "/packs",
    response_model=PackListResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def list_packs() -> PackListResponse:
    """List available domain packs and the active-pack resolution state."""
    active_path, active_state = _active_pack_state()
    packs: list[PackSummary] = []
    seen: set[Path] = set()
    for base in _allowed_pack_dirs():
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            resolved = path.resolve()
            if (
                resolved.suffix.lower() not in _PACK_SUFFIXES
                or not resolved.is_file()
                or resolved in seen
            ):
                continue
            seen.add(resolved)
            packs.append(_summarize_pack(resolved, active_path))
    return PackListResponse(
        packs=packs,
        active=active_state,
        generation=dependencies.get_config_generation(),
    )


@router.post(
    "/validate",
    response_model=ValidatePackResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def validate_pack(payload: ValidatePackRequest) -> ValidatePackResponse:
    """Dry-run full validation of a pack; never mutates pointer, caches, or state."""
    if payload.content is not None:
        data = payload.content
    else:
        # The request model guarantees exactly one of pack/content is set.
        pack_path = _resolve_pack_reference(payload.pack or "")
        try:
            data = _parse_pack_file(pack_path)
        except _PackParseError as exc:
            return ValidatePackResponse(
                valid=False,
                errors=[
                    ConfigValidationIssue(
                        message=str(exc),
                        error_type="parse_error",
                    )
                ],
            )
    try:
        candidate = DomainConfig.model_validate(data)
    except ValidationError as exc:
        return ValidatePackResponse(valid=False, errors=_validation_issues(exc))
    return ValidatePackResponse(
        valid=True,
        pack_name=candidate.domain.name,
        display_name=candidate.domain.display_name,
    )


@router.post(
    "/apply",
    response_model=ConfigSwapResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def apply_pack(payload: ApplyPackRequest, request: Request) -> ConfigSwapResponse:
    """Validate and (re-)apply a pack; without ``pack`` re-applies the active one."""
    if payload.pack is not None:
        candidate = _resolve_pack_reference(payload.pack)
    else:
        try:
            candidate = resolve_config_path().resolve()
        except ActivePackStoreError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No active pack to re-apply: {exc}",
            ) from exc
    return _activate_pack(candidate, reason="apply", request=request)


@router.post(
    "/switch",
    response_model=ConfigSwapResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def switch_pack(payload: SwitchPackRequest, request: Request) -> ConfigSwapResponse:
    """Activate a different existing pack (validate → persist → swap → emit)."""
    candidate = _resolve_pack_reference(payload.pack)
    return _activate_pack(candidate, reason="switch", request=request)
