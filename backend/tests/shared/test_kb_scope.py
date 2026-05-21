"""Unit tests for the dual-graph scope resolver."""

import logging
from dataclasses import dataclass

import pytest

from config.schema import AlertsConfig, CapabilitiesConfig, DomainConfig, DomainInfo, IngestionConfig, ValidationConfig
from shared.kb_scope import resolve_kb_scope


def _minimal_domain_config(default_reference_kb_id: str | None = None) -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(
            name="test_domain",
            display_name="Test Domain",
            description="Test domain.",
        ),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        alerts=AlertsConfig(thresholds={}),
        validation=ValidationConfig(
            max_file_size_mb=1,
            allowed_content_types=["text/plain", "application/json"],
        ),
        default_reference_kb_id=default_reference_kb_id,
    )


@dataclass
class _StubKbRepository:
    """Minimal KnowledgeBaseExistenceCheck stub."""

    existing_ids: set[str]

    def get(self, knowledge_base_id: str) -> object | None:
        return object() if knowledge_base_id in self.existing_ids else None


def test_returns_primary_only_when_no_reference_configured() -> None:
    config = _minimal_domain_config(default_reference_kb_id=None)
    repo = _StubKbRepository(existing_ids={"kb-claims"})

    scope = resolve_kb_scope("kb-claims", config, repo)

    assert scope == ["kb-claims"]


def test_returns_primary_and_reference_when_both_configured_and_exist() -> None:
    config = _minimal_domain_config(default_reference_kb_id="kb-policy")
    repo = _StubKbRepository(existing_ids={"kb-claims", "kb-policy"})

    scope = resolve_kb_scope("kb-claims", config, repo)

    assert scope == ["kb-claims", "kb-policy"]


def test_returns_primary_only_when_primary_is_the_reference() -> None:
    """No self-attach loop when the analyst queries the policy KB directly."""
    config = _minimal_domain_config(default_reference_kb_id="kb-policy")
    repo = _StubKbRepository(existing_ids={"kb-policy"})

    scope = resolve_kb_scope("kb-policy", config, repo)

    assert scope == ["kb-policy"]


def test_returns_primary_only_and_logs_warning_when_reference_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _minimal_domain_config(default_reference_kb_id="kb-missing")
    repo = _StubKbRepository(existing_ids={"kb-claims"})

    with caplog.at_level(logging.WARNING, logger="shared.kb_scope"):
        scope = resolve_kb_scope("kb-claims", config, repo)

    assert scope == ["kb-claims"]
    warning_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "WARNING"
        and record.name == "shared.kb_scope"
    ]
    assert len(warning_messages) == 1
    assert "kb-missing" in warning_messages[0]
    assert "kb-claims" in warning_messages[0]
