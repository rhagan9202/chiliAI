"""Tests for the SAFE-CMS-012 identity resolution API router."""

from __future__ import annotations

from typing import Callable, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from analytics.identity_resolution import (
    IdentityDecisionService,
    IdentityResolutionService,
    InMemoryIdentityLinkRepository,
)
import api.dependencies as dependencies
from api.app import create_app
from api.middleware.auth import User, get_current_user
from auditlog.models import PLATFORM_TENANT_ID, AuditEventQuery
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.service import AuditLogService
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from events.adapters.in_memory import InMemoryEventBus
from tests.analytics.test_identity_resolution_repository import _link


def _override_dependency(app: FastAPI, name: str, value: object) -> None:
    dependency = getattr(dependencies, name, None)
    if dependency is None:
        pytest.fail(f"Missing API dependency '{name}'.")
    app.dependency_overrides[cast(Callable[..., object], dependency)] = lambda: value


def _identity_client() -> tuple[
    TestClient,
    InMemoryIdentityLinkRepository,
    InMemoryEventBus,
    AuditLogService,
]:
    app = create_app()
    repository = InMemoryIdentityLinkRepository()
    event_bus = InMemoryEventBus()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    _override_dependency(app, "get_identity_link_repository", repository)
    _override_dependency(app, "get_event_bus", event_bus)
    _override_dependency(app, "get_audit_log_service", audit_service)
    _override_dependency(app, "get_identity_resolution_service", IdentityResolutionService())
    _override_dependency(
        app,
        "get_identity_decision_service",
        IdentityDecisionService(
            repository,
            event_bus=event_bus,
            audit_log_service=audit_service,
        ),
    )
    return TestClient(app), repository, event_bus, audit_service


def _auth_enabled_config() -> DomainConfig:
    return load_config().model_copy(update={"auth": AuthConfig(enabled=True)})


def _auth_identity_client(
    user: User,
) -> tuple[
    TestClient,
    InMemoryIdentityLinkRepository,
    InMemoryEventBus,
    AuditLogService,
]:
    app = create_app()
    repository = InMemoryIdentityLinkRepository()
    event_bus = InMemoryEventBus()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    app.dependency_overrides[dependencies.get_domain_config] = _auth_enabled_config
    app.dependency_overrides[get_current_user] = lambda: user
    _override_dependency(app, "get_identity_link_repository", repository)
    _override_dependency(app, "get_event_bus", event_bus)
    _override_dependency(app, "get_audit_log_service", audit_service)
    _override_dependency(app, "get_identity_resolution_service", IdentityResolutionService())
    _override_dependency(
        app,
        "get_identity_decision_service",
        IdentityDecisionService(
            repository,
            event_bus=event_bus,
            audit_log_service=audit_service,
        ),
    )
    return TestClient(app), repository, event_bus, audit_service


def test_get_canonical_identity_detail_lists_kb_scoped_source_links() -> None:
    client, repository, _, _ = _identity_client()
    repository.upsert_link(_link())
    repository.upsert_link(
        _link("identity_link:kb2:canonical-1:source-1").model_copy(
            update={"knowledge_base_id": "kb2"},
            deep=True,
        )
    )

    response = client.get(
        "/identity/canonical/canonical%3A1",
        params={"knowledge_base_id": "kb1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb1"
    assert payload["canonical_entity_id"] == "canonical:1"
    assert payload["total"] == 1
    assert payload["links"][0]["id"] == "identity_link:kb1:canonical-1:source-1"
    assert payload["links"][0]["source_refs"] == ["source-system:a"]


def test_resolve_identity_candidates_scores_connector_payload() -> None:
    client, _, _, _ = _identity_client()

    response = client.post(
        "/identity/resolve-candidates",
        json={
            "knowledge_base_id": "kb1",
            "source_entity": {
                "id": "source:1",
                "type": "provider_source",
                "properties": {
                    "provider_name": "General Hospital",
                    "npi": "1234567890",
                },
            },
            "candidates": [
                {
                    "knowledge_base_id": "kb1",
                    "entity": {
                        "id": "canonical:1",
                        "type": "provider",
                        "properties": {
                            "provider_name": "General Hospital",
                            "npi": "1234567890",
                        },
                    },
                }
            ],
            "natural_key_fields": ["provider_name"],
            "identifier_fields": ["npi"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb1"
    assert payload["source_entity_id"] == "source:1"
    assert payload["candidates"][0]["entity_id"] == "canonical:1"
    assert payload["candidates"][0]["confidence"] == "high"
    assert payload["candidates"][0]["match_reasons"]


def test_record_identity_decision_returns_link_and_writes_audit_metadata() -> None:
    client, repository, event_bus, audit_service = _identity_client()
    repository.upsert_link(_link())

    response = client.post(
        "/identity/links/identity_link%3Akb1%3Acanonical-1%3Asource-1/decision",
        json={
            "knowledge_base_id": "kb1",
            "decision": "approve_merge",
            "actor_user_id": "steward-1",
            "actor_email": "steward-1@example.test",
            "actor_roles": ["data_steward"],
            "correlation_id": "corr-identity-api",
            "comment": "same entity after source review",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_state"] == "merged"
    assert payload["decision_history"][0]["decision"] == "approve_merge"
    assert event_bus.published_events[0].correlation_id == "corr-identity-api"
    events = audit_service.list_events(
        AuditEventQuery(
            knowledge_base_id="kb1",
            action_prefix="identity_link.",
        )
    )
    assert events.total_items == 1


def test_caller_supplied_tenant_id_cannot_reach_the_audit_ledger() -> None:
    """Regression guard for the audit-evasion vector this endpoint used to carry.

    `tenant_id` was an accepted request field forwarded unvalidated into the
    ledger, so a steward could post one arbitrary value and file their own
    merge/split under a tenant no KB- or platform-scoped supervisor query would
    look in. The event must land under the platform tenant regardless of what
    the caller sends, and must be reachable by a plain KB-scoped query.
    """

    client, repository, _, audit_service = _identity_client()
    repository.upsert_link(_link())

    response = client.post(
        "/identity/links/identity_link%3Akb1%3Acanonical-1%3Asource-1/decision",
        json={
            "knowledge_base_id": "kb1",
            "decision": "approve_merge",
            "actor_user_id": "steward-1",
            "tenant_id": "attacker-chosen-tenant",
        },
    )

    assert response.status_code == 200
    events = audit_service.list_events(
        AuditEventQuery(knowledge_base_id="kb1", action_prefix="identity_link.")
    )
    assert events.total_items == 1
    assert events.items[0].tenant_id == PLATFORM_TENANT_ID
    # And nothing was filed under the value the caller tried to choose.
    hidden = audit_service.list_events(
        AuditEventQuery(tenant_id="attacker-chosen-tenant")
    )
    assert hidden.total_items == 0


def test_get_canonical_identity_detail_hides_unauthorized_kb() -> None:
    client, repository, _, _ = _auth_identity_client(
        User(user_id="viewer-1", roles=["viewer"], knowledge_base_ids=["kb-allowed"])
    )
    repository.upsert_link(_link())

    response = client.get(
        "/identity/canonical/canonical%3A1",
        params={"knowledge_base_id": "kb1"},
    )

    assert response.status_code == 404


def test_resolve_identity_candidates_hides_unauthorized_kb() -> None:
    client, _, _, _ = _auth_identity_client(
        User(user_id="analyst-1", roles=["analyst"], knowledge_base_ids=["kb-allowed"])
    )

    response = client.post(
        "/identity/resolve-candidates",
        json={
            "knowledge_base_id": "kb1",
            "source_entity": {"id": "source:1", "type": "provider_source"},
            "candidates": [],
        },
    )

    assert response.status_code == 404


def test_record_identity_decision_uses_authenticated_actor_metadata() -> None:
    client, repository, _, audit_service = _auth_identity_client(
        User(
            user_id="analyst-1",
            roles=["analyst"],
            email="analyst-1@example.test",
            knowledge_base_ids=["kb1"],
        )
    )
    repository.upsert_link(_link())

    response = client.post(
        "/identity/links/identity_link%3Akb1%3Acanonical-1%3Asource-1/decision",
        json={
            "knowledge_base_id": "kb1",
            "decision": "approve_merge",
            "actor_user_id": "forged-user",
            "actor_email": "forged@example.test",
            "actor_roles": ["admin"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_history"][0]["actor_user_id"] == "analyst-1"
    events = audit_service.list_events(
        AuditEventQuery(
            knowledge_base_id="kb1",
            action_prefix="identity_link.",
        )
    )
    assert events.items[0].actor_user_id == "analyst-1"
    assert events.items[0].actor_email == "analyst-1@example.test"
    assert events.items[0].actor_roles == ["analyst"]


def test_record_identity_decision_hides_unauthorized_kb() -> None:
    client, repository, event_bus, audit_service = _auth_identity_client(
        User(user_id="analyst-1", roles=["analyst"], knowledge_base_ids=["kb-allowed"])
    )
    repository.upsert_link(_link())

    response = client.post(
        "/identity/links/identity_link%3Akb1%3Acanonical-1%3Asource-1/decision",
        json={
            "knowledge_base_id": "kb1",
            "decision": "approve_merge",
        },
    )

    assert response.status_code == 404
    stored = repository.get_link(
        knowledge_base_id="kb1",
        link_id="identity_link:kb1:canonical-1:source-1",
    )
    assert stored is not None
    assert stored.review_state == "steward_review"
    assert event_bus.published_events == []
    events = audit_service.list_events(
        AuditEventQuery(
            knowledge_base_id="kb1",
            action_prefix="identity_link.",
        )
    )
    assert events.total_items == 0
