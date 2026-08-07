"""The runtime environment vocabulary.

One definition, because this name is used in two places that must agree: the
value `CHILI_ENV` is validated against, and the `environment_tags` a capability
manifest declares it supports. When they drifted apart, capability manifests
listed a "test" environment that never exists and omitted "local" — the default
for the entire dev stack — so every capability call outside dev or production
was denied.
"""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

__all__ = ["SUPPORTED_ENVIRONMENT_TAGS", "EnvironmentTag"]

EnvironmentTag: TypeAlias = Literal["local", "dev", "staging", "production"]

# Ordered least- to most-privileged, which is also deployment order.
SUPPORTED_ENVIRONMENT_TAGS: Final[tuple[EnvironmentTag, ...]] = (
    "local",
    "dev",
    "staging",
    "production",
)
