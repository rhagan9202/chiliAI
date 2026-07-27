"""Request/response DTOs for the config pack-management API.

These models back the admin-only pack routes in ``api.routers.config``
(``GET /config/packs``, ``POST /config/validate|apply|switch``) and are the
source of truth for the generated frontend contracts (exported via OpenAPI).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "ActivePackState",
    "ApplyPackRequest",
    "ConfigSwapResponse",
    "ConfigValidationIssue",
    "PackListResponse",
    "PackSummary",
    "PackTransport",
    "SwitchPackRequest",
    "ValidatePackRequest",
    "ValidatePackResponse",
]


class PackTransport(BaseModel):
    """The event transport a pack would actually run on.

    Effective settings, **not** the pack's declared ``events`` section: the
    environment wins when that section is absent or equal to the default
    ``EventBusConfig()``, so a pack that omits it does not change the transport
    at all. Reported so an operator can see, before confirming a hot-swap,
    whether the swap would abandon queued worker jobs (UXA-404).
    """

    backend: str = Field(description='Effective transport backend ("redis" or "in-memory").')
    uri: str | None = Field(default=None, description="Effective transport URI, when any.")
    stream_prefix: str = Field(description="Effective stream prefix.")
    consumer_group: str = Field(description="Effective consumer group.")


class ConfigValidationIssue(BaseModel):
    """One structured, field-level validation finding for a domain pack."""

    loc: list[str] = Field(
        default_factory=lambda: cast(list[str], []),
        description="Path segments to the offending field (ints stringified).",
    )
    field: str = Field(
        default="",
        description="Dotted-path convenience form of ``loc`` (empty for file-level issues).",
    )
    message: str = Field(description="Human-readable error message.")
    error_type: str = Field(
        description="Machine-readable error category (pydantic error type or 'parse_error')."
    )


class PackSummary(BaseModel):
    """A domain pack discovered in one of the allowed config directories."""

    name: str = Field(description="Pack name (file stem), usable as a pack reference.")
    file_name: str
    path: str = Field(description="Resolved filesystem path of the pack file.")
    domain_name: str | None = Field(
        default=None, description="``domain.name`` from the pack (None when invalid)."
    )
    display_name: str | None = Field(
        default=None, description="``domain.display_name`` from the pack (None when invalid)."
    )
    valid: bool = Field(description="Whether the pack currently passes full validation.")
    error: str | None = Field(
        default=None, description="Validation/parse failure summary when ``valid`` is false."
    )
    transport: PackTransport | None = Field(
        default=None,
        description=(
            "Event transport this pack would run on; null when the pack does not load, "
            "since there is nothing to resolve."
        ),
    )
    active: bool = Field(description="Whether this pack is the currently active one.")


class ActivePackState(BaseModel):
    """How the currently active domain pack is being resolved."""

    config_path: str | None = Field(
        default=None, description="Path of the active pack file (None when unresolvable)."
    )
    pack_name: str | None = Field(
        default=None, description="Pack name recorded in the pointer, when available."
    )
    source: Literal["pointer", "env", "none"] = Field(
        description="Resolution source: active-pack pointer, CHILI_CONFIG_PATH env, or none."
    )
    updated_at: datetime | None = Field(
        default=None, description="When the pointer was last written (pointer source only)."
    )


class PackListResponse(BaseModel):
    """Response for ``GET /config/packs``."""

    packs: list[PackSummary] = Field(default_factory=lambda: cast(list[PackSummary], []))
    active: ActivePackState
    generation: int = Field(
        ge=0, description="Current config swap generation (see get_config_generation)."
    )


class ValidatePackRequest(BaseModel):
    """Dry-run validation input: exactly one of ``pack`` or ``content``.

    ``pack`` is a pack name (file stem in an allowed config directory) or a
    path resolving inside an allowed config directory. ``content`` is an
    inline pack mapping (already parsed, e.g. the JSON form of the YAML).
    """

    pack: str | None = Field(
        default=None, description="Pack name or path within the allowed config directories."
    )
    content: dict[str, object] | None = Field(
        default=None, description="Inline domain-pack mapping to validate."
    )

    @model_validator(mode="after")
    def _exactly_one_source(self) -> ValidatePackRequest:
        if (self.pack is None) == (self.content is None):
            raise ValueError("Provide exactly one of 'pack' or 'content'.")
        return self


class ValidatePackResponse(BaseModel):
    """Response for ``POST /config/validate`` (never mutates server state)."""

    valid: bool
    pack_name: str | None = Field(
        default=None, description="``domain.name`` of the validated pack when valid."
    )
    display_name: str | None = Field(
        default=None, description="``domain.display_name`` of the validated pack when valid."
    )
    errors: list[ConfigValidationIssue] = Field(
        default_factory=lambda: cast(list[ConfigValidationIssue], [])
    )
    transport: PackTransport | None = Field(
        default=None,
        description=(
            "Event transport the validated pack would run on; null when the pack is invalid."
        ),
    )


class ApplyPackRequest(BaseModel):
    """Input for ``POST /config/apply``.

    Omit ``pack`` (or send ``{}``) to re-apply the currently active pack —
    the re-validate-and-swap path after editing the active pack in place.
    """

    pack: str | None = Field(
        default=None,
        description=(
            "Pack name or path within the allowed config directories; "
            "defaults to the currently active pack."
        ),
    )


class SwitchPackRequest(BaseModel):
    """Input for ``POST /config/switch``: activate a different existing pack."""

    pack: str = Field(
        min_length=1,
        description="Pack name or path within the allowed config directories.",
    )


class ConfigSwapResponse(BaseModel):
    """Result of a successful ``POST /config/apply`` or ``POST /config/switch``."""

    status: Literal["applied"]
    reason: Literal["apply", "switch"]
    pack_name: str = Field(description="``domain.name`` of the now-active pack.")
    pack_path: str = Field(description="Resolved path of the now-active pack file.")
    previous_pack_name: str | None = Field(
        default=None, description="Pack that was active before the swap, when known."
    )
    generation: int = Field(
        ge=1,
        description=(
            "New config swap generation; clients can compare against a previously "
            "observed generation to detect mid-request swaps."
        ),
    )
    rag_degraded_to_fallback: bool = Field(
        description=(
            "True when the live RAG composition for the new pack failed and the "
            "API fell back to the seeded in-memory pipeline."
        )
    )
    event_published: bool = Field(
        description=(
            "Whether the config.updated event was published to the event bus "
            "(the swap itself succeeded either way)."
        )
    )
