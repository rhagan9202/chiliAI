"""Tests for authorize-then-dispatch capability execution.

The ordering assertions here are the security property: authorization must run
before anything is invoked, and an audited capability must leave a record
whether it succeeded or failed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping

import pytest

from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEventQuery
from auditlog.service import AuditLogService
from capabilities.models import (
    CapabilityManifest,
    CapabilityPermission,
)
from capabilities.executors import (
    clear_executors,
    register_executor,
)
from capabilities.service import (
    CapabilityRegistryService,
    create_default_capability_registry_service,
)

_KB_ID = "kb-1"
_ACTOR = "operator-1"


@pytest.fixture(autouse=True)
def clear_executor_registry() -> Iterator[None]:
    """The executor map is module-level state; leaking it across tests hides bugs."""

    clear_executors()
    yield
    clear_executors()


def _recording_executor(
    log: list[str],
) -> Callable[[Mapping[str, object]], Mapping[str, object]]:
    def _run(payload: Mapping[str, object]) -> Mapping[str, object]:
        log.append("ran")
        return {}

    return _run


def _capturing_executor(
    seen: list[Mapping[str, object]],
) -> Callable[[Mapping[str, object]], Mapping[str, object]]:
    def _run(payload: Mapping[str, object]) -> Mapping[str, object]:
        seen.append(payload)
        return {}

    return _run


def _constant_executor(
    value: Mapping[str, object],
) -> Callable[[Mapping[str, object]], Mapping[str, object]]:
    def _run(payload: Mapping[str, object]) -> Mapping[str, object]:
        return value

    return _run


def _audit() -> AuditLogService:
    return AuditLogService(InMemoryAuditLogRepository())


def _service() -> CapabilityRegistryService:
    return create_default_capability_registry_service()


def _audited_manifest() -> CapabilityManifest:
    """A read capability that requires an audit record."""

    return CapabilityManifest(
        capability_id="test.audited",
        version="v1",
        module="tests",
        label="Audited",
        description="A capability that requires auditing.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class="write",
        permission=CapabilityPermission(
            required_roles=["analyst"], requires_audit=True
        ),
    )


def _unaudited_manifest() -> CapabilityManifest:
    return CapabilityManifest(
        capability_id="test.unaudited",
        version="v1",
        module="tests",
        label="Unaudited",
        description="A capability that does not require auditing.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class="read",
        permission=CapabilityPermission(
            required_roles=["analyst"], requires_audit=False
        ),
    )


def _execute(
    service: CapabilityRegistryService,
    capability_id: str,
    *,
    audit: AuditLogService,
    actor_roles: list[str] | None = None,
    payload: Mapping[str, object] | None = None,
):
    return service.execute(
        capability_id,
        payload=payload or {},
        actor_user_id=_ACTOR,
        actor_roles=actor_roles or ["analyst"],
        domain_name="medicare_fraud",
        environment_tag="local",
        knowledge_base_id=_KB_ID,
        audit_service=audit,
    )


# --- ordering ---------------------------------------------------------------


def test_denies_before_invoking_the_executor() -> None:
    """Authorization runs first, so a denied call never reaches the tool.

    If dispatch happened first the side effect would already have occurred by
    the time the envelope said "denied".
    """
    invoked: list[str] = []
    service = _service()
    service.register(_audited_manifest())
    register_executor("test.audited", _recording_executor(invoked))

    envelope = _execute(
        service, "test.audited", audit=_audit(), actor_roles=["viewer"]
    )

    assert envelope.success is False
    assert envelope.error_code == "capability_role_denied"
    assert invoked == []


def test_a_denied_call_is_not_dispatched_even_when_context_is_missing() -> None:
    """The Task 1 fail-closed branches must also gate dispatch."""
    invoked: list[str] = []
    service = _service()
    service.register(_audited_manifest())
    register_executor("test.audited", _recording_executor(invoked))

    envelope = service.execute(
        "test.audited",
        payload={},
        actor_user_id=_ACTOR,
        actor_roles=["analyst"],
        domain_name=None,
        environment_tag="local",
        knowledge_base_id=_KB_ID,
        audit_service=_audit(),
    )

    assert envelope.success is False
    assert envelope.error_code == "domain_not_supplied"
    assert invoked == []


# --- dispatch ---------------------------------------------------------------


def test_executes_and_returns_the_executor_output() -> None:
    service = _service()
    service.register(_unaudited_manifest())
    register_executor("test.unaudited", _constant_executor({"peers": 4}))

    envelope = _execute(service, "test.unaudited", audit=_audit())

    assert envelope.success is True
    assert envelope.output == {"peers": 4}


def test_passes_the_payload_through_to_the_executor() -> None:
    seen: list[Mapping[str, object]] = []
    service = _service()
    service.register(_unaudited_manifest())
    register_executor("test.unaudited", _capturing_executor(seen))

    _execute(
        service, "test.unaudited", audit=_audit(), payload={"entity_id": "e-1"}
    )

    assert seen == [{"entity_id": "e-1"}]


def test_denies_a_capability_with_no_registered_executor() -> None:
    """A manifest without an executor is a registry that promises what it cannot do."""
    service = _service()
    service.register(_unaudited_manifest())

    envelope = _execute(service, "test.unaudited", audit=_audit())

    assert envelope.success is False
    assert envelope.error_code == "capability_not_executable"


def test_returns_a_failure_envelope_when_the_executor_raises() -> None:
    """A tool blowing up is a failed capability call, not a failed workflow step.

    The step executor decides what to do about it; surfacing the exception here
    would dead-letter the event and lose the audit record.
    """

    def _boom(payload: Mapping[str, object]) -> Mapping[str, object]:
        raise RuntimeError("upstream down")

    service = _service()
    service.register(_unaudited_manifest())
    register_executor("test.unaudited", _boom)

    envelope = _execute(service, "test.unaudited", audit=_audit())

    assert envelope.success is False
    assert envelope.error_code == "capability_execution_failed"
    assert envelope.error_message is not None
    assert "upstream down" in envelope.error_message


# --- audit ------------------------------------------------------------------


def test_writes_an_audit_event_when_requires_audit_is_set() -> None:
    """`requires_audit` stops being a flag nothing reads."""
    audit = _audit()
    service = _service()
    service.register(_audited_manifest())
    register_executor("test.audited", _constant_executor({"ok": True}))

    _execute(service, "test.audited", audit=audit)

    events = audit.list_events(AuditEventQuery(knowledge_base_id=_KB_ID))
    assert events.total_items == 1
    assert events.items[0].action == "capability.execute"
    assert events.items[0].resource_id == "test.audited"
    assert events.items[0].outcome == "success"


def test_the_audit_record_names_the_actual_actor_not_their_roles() -> None:
    """`actor_user_id` is identity; `actor_roles` is authorization context.

    Deriving the id from the roles would put a fabricated actor into an
    append-only ledger while the field meant for the real one sat unused — the
    ledger would be actively misleading rather than merely incomplete.
    """
    audit = _audit()
    service = _service()
    service.register(_audited_manifest())
    register_executor("test.audited", _constant_executor({"ok": True}))

    _execute(service, "test.audited", audit=audit, actor_roles=["analyst"])

    event = audit.list_events(AuditEventQuery(knowledge_base_id=_KB_ID)).items[0]
    assert event.actor_user_id == _ACTOR
    assert event.actor_roles == ["analyst"]


def test_a_failed_execution_is_still_audited() -> None:
    """The calls worth auditing are exactly the ones that might go wrong."""

    def _boom(payload: Mapping[str, object]) -> Mapping[str, object]:
        raise RuntimeError("upstream down")

    audit = _audit()
    service = _service()
    service.register(_audited_manifest())
    register_executor("test.audited", _boom)

    _execute(service, "test.audited", audit=audit)

    events = audit.list_events(AuditEventQuery(knowledge_base_id=_KB_ID))
    assert events.total_items == 1
    assert events.items[0].outcome == "failure"
    assert events.items[0].failure_reason is not None


def test_a_denied_call_is_still_audited() -> None:
    """A refused attempt on an audited capability is exactly what a ledger is for."""
    audit = _audit()
    service = _service()
    service.register(_audited_manifest())
    register_executor("test.audited", _constant_executor({"ok": True}))

    _execute(service, "test.audited", audit=audit, actor_roles=["viewer"])

    events = audit.list_events(AuditEventQuery(knowledge_base_id=_KB_ID))
    assert events.total_items == 1
    assert events.items[0].outcome == "failure"


def test_does_not_audit_a_capability_that_does_not_require_it() -> None:
    audit = _audit()
    service = _service()
    service.register(_unaudited_manifest())
    register_executor("test.unaudited", _constant_executor({"ok": True}))

    _execute(service, "test.unaudited", audit=audit)

    assert audit.list_events(AuditEventQuery(knowledge_base_id=_KB_ID)).total_items == 0


def test_execution_survives_an_audit_write_failure() -> None:
    """A broken ledger must not silently discard the outcome of the work.

    AuditLogService already captures write failures rather than raising; this
    asserts execute() inherits that instead of losing the envelope.
    """

    class _FailingRepository(InMemoryAuditLogRepository):
        def append(self, event):  # type: ignore[no-untyped-def]
            raise RuntimeError("ledger unavailable")

    audit = AuditLogService(_FailingRepository())
    service = _service()
    service.register(_audited_manifest())
    register_executor("test.audited", _constant_executor({"ok": True}))

    envelope = _execute(service, "test.audited", audit=audit)

    assert envelope.success is True
    assert audit.failed_write_count == 1


def test_every_bound_executor_names_a_registered_capability() -> None:
    """A typo in a capability id binds an executor nothing will ever look up.

    `register_executor("rag.querry", ...)` is silent: the manifest still
    authorizes, the lookup still misses, and the call fails as
    `capability_not_executable` with nothing pointing at the typo.
    """
    from capabilities.executors import registered_capability_ids

    service = _service()
    known = {manifest.capability_id for manifest in service.list_capabilities().items}

    orphans = {
        capability_id
        for capability_id in registered_capability_ids()
        if capability_id not in known and not capability_id.startswith("test.")
    }

    assert not orphans, f"executors bound to unregistered capabilities: {sorted(orphans)}"


def test_a_registered_manifest_without_an_executor_is_reported_not_crashed() -> None:
    """The current state of every shipped capability, stated honestly.

    Nothing binds executors yet — Task 5 wires them with their services bound
    in a closure. Until then an authorized call must degrade to a clear
    `capability_not_executable`, not an AttributeError or a silent success.
    """
    service = _service()
    audit = _audit()

    envelope = service.execute(
        "rag.query",
        payload={},
        actor_user_id=_ACTOR,
        actor_roles=["analyst"],
        domain_name="medicare_fraud",
        environment_tag="local",
        knowledge_base_id=_KB_ID,
        audit_service=audit,
    )

    assert envelope.success is False
    assert envelope.error_code == "capability_not_executable"
