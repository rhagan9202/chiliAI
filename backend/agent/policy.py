"""Stage-level worker execution policy hooks."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from pydantic import ValidationError

from agent.exceptions import AgentConfigurationError
from agent.models import RetryPolicy

STAGE_POLICY_ENV_VAR = "CHILI_STAGE_POLICY_JSON"
_SUPPORTED_POLICY_FIELDS = frozenset(
    {
        "max_retries",
        "backoff_seconds",
        "base_delay_seconds",
        "timeout_seconds",
        "fatal_exception_types",
    }
)


@dataclass(frozen=True, slots=True)
class StagePolicy:
    """Execution controls for a single worker stage.

    ``timeout_seconds`` is an **alarm budget, not a deadline**. Handlers run in
    the default executor and a running thread cannot be cancelled, so exceeding
    the budget makes ``run_handler_with_retry`` log the overrun loudly and keep
    waiting for the stage's real outcome. It does not abandon, dead-letter or
    acknowledge work that is still in flight — doing either would let the
    pipeline advance under a run marked FAILED, or hand the delivery back to
    ``reclaim_stale_pending`` for a duplicate run. Bounding a stage's wall clock
    requires cooperative cancellation inside the handler itself.
    """

    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: float | None = None
    fatal_exception_types: tuple[type[BaseException], ...] = ()

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")


class StagePolicyRegistry:
    """Lookup table for event-type-specific worker stage policies."""

    def __init__(
        self,
        policies: Mapping[str, StagePolicy] | None = None,
        *,
        default_retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._policies = dict(policies or {})
        self._default_policy = StagePolicy(
            retry_policy=default_retry_policy or RetryPolicy()
        )

    def get(self, event_type: str) -> StagePolicy:
        """Return the configured policy for ``event_type`` or the default."""

        return self._policies.get(event_type, self._default_policy)

    def register(self, event_type: str, policy: StagePolicy) -> None:
        """Register or replace the policy for ``event_type``."""

        self._policies[event_type] = policy


def load_stage_policy_registry_from_env(
    env: Mapping[str, str] | None = None,
    *,
    default_retry_policy: RetryPolicy | None = None,
) -> StagePolicyRegistry:
    """Build a stage policy registry from ``CHILI_STAGE_POLICY_JSON``.

    The JSON object maps event type strings to policy objects. Supported policy
    fields are ``max_retries``, ``backoff_seconds``/``base_delay_seconds``, and
    ``timeout_seconds`` (see :class:`StagePolicy` — an alarm budget, not a
    deadline). ``fatal_exception_types`` is intentionally rejected for env
    configuration because resolving exception names safely requires an explicit
    allowlist.
    """

    source = os.environ if env is None else env
    raw = source.get(STAGE_POLICY_ENV_VAR)
    if raw is None or raw.strip() == "":
        return StagePolicyRegistry(default_retry_policy=default_retry_policy)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentConfigurationError(
            f"{STAGE_POLICY_ENV_VAR} must be valid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise AgentConfigurationError(f"{STAGE_POLICY_ENV_VAR} must be a JSON object.")

    parsed_obj = cast("dict[object, object]", parsed)
    policies: dict[str, StagePolicy] = {}
    for event_type, value in parsed_obj.items():
        if not isinstance(event_type, str) or event_type.strip() == "":
            raise AgentConfigurationError(
                f"{STAGE_POLICY_ENV_VAR} keys must be non-empty event type strings."
            )
        if not isinstance(value, dict):
            raise AgentConfigurationError(
                f"{STAGE_POLICY_ENV_VAR}[{event_type!r}] must be a JSON object."
            )
        policies[event_type] = _parse_stage_policy(
            event_type, cast("Mapping[str, object]", value)
        )
    return StagePolicyRegistry(
        policies,
        default_retry_policy=default_retry_policy,
    )


def _parse_stage_policy(event_type: str, value: Mapping[str, object]) -> StagePolicy:
    unknown_fields = set(value) - _SUPPORTED_POLICY_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise AgentConfigurationError(
            f"Unsupported stage policy field(s) for {event_type!r}: {fields}."
        )
    if "fatal_exception_types" in value:
        raise AgentConfigurationError(
            "CHILI_STAGE_POLICY_JSON does not support fatal_exception_types; "
            "configure fatal exception classes in code with an explicit allowlist."
        )
    if "backoff_seconds" in value and "base_delay_seconds" in value:
        raise AgentConfigurationError(
            f"Stage policy for {event_type!r} must use either backoff_seconds "
            "or base_delay_seconds, not both."
        )

    retry_args: dict[str, object] = {}
    if "max_retries" in value:
        retry_args["max_retries"] = value["max_retries"]
    if "backoff_seconds" in value:
        retry_args["base_delay_seconds"] = value["backoff_seconds"]
    if "base_delay_seconds" in value:
        retry_args["base_delay_seconds"] = value["base_delay_seconds"]

    try:
        retry_policy = RetryPolicy.model_validate(retry_args)
        return StagePolicy(
            retry_policy=retry_policy,
            timeout_seconds=value.get("timeout_seconds"),  # type: ignore[arg-type]
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise AgentConfigurationError(
            f"Invalid stage policy for {event_type!r}: {exc}"
        ) from exc


__all__ = [
    "STAGE_POLICY_ENV_VAR",
    "StagePolicy",
    "StagePolicyRegistry",
    "load_stage_policy_registry_from_env",
]
