from __future__ import annotations

import pytest

from config.schema import FraudPlaybookConfig
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import PlaybookSnapshot


def _snapshot(
    *,
    domain_name: str = "medicare_fraud",
    playbook_id: str = "provider_billing_spike_review",
    version: str = "v1",
) -> PlaybookSnapshot:
    return PlaybookSnapshot(
        snapshot_id=f"{domain_name}:{playbook_id}:{version}",
        domain_name=domain_name,
        playbook_id=playbook_id,
        version=version,
        status="published",
        source="domain_config",
        definition=FraudPlaybookConfig(
            id=playbook_id,
            version=version,
            title=f"{playbook_id} title",
            status="published",
        ),
        published_by="admin-1",
    )


def test_upsert_and_get_return_deep_copies() -> None:
    repository = InMemoryPlaybookRepository()
    original = _snapshot()

    stored = repository.upsert_snapshot(original)
    stored.definition.title = "mutated returned snapshot"
    original.definition.title = "mutated original"

    found = repository.get_snapshot(
        domain_name="medicare_fraud",
        playbook_id="provider_billing_spike_review",
        version="v1",
    )

    assert found is not None
    assert found.definition.title == "provider_billing_spike_review title"
    found.definition.title = "mutated fetched snapshot"

    found_again = repository.get_snapshot(
        domain_name="medicare_fraud",
        playbook_id="provider_billing_spike_review",
        version="v1",
    )
    assert found_again is not None
    assert found_again.definition.title == "provider_billing_spike_review title"


def test_upsert_rejects_conflicting_existing_snapshot() -> None:
    repository = InMemoryPlaybookRepository()
    repository.upsert_snapshot(_snapshot())

    conflicting = _snapshot()
    conflicting.definition.title = "Different title"

    with pytest.raises(ValueError, match="already exists with different definition"):
        repository.upsert_snapshot(conflicting)

    stored = repository.get_snapshot(
        domain_name="medicare_fraud",
        playbook_id="provider_billing_spike_review",
        version="v1",
    )
    assert stored is not None
    assert stored.definition.title == "provider_billing_spike_review title"


def test_list_snapshots_filters_by_domain_and_paginates_deterministically() -> None:
    repository = InMemoryPlaybookRepository()
    repository.upsert_snapshot(
        _snapshot(playbook_id="identity_mismatch_review", version="v2")
    )
    repository.upsert_snapshot(
        _snapshot(playbook_id="provider_billing_spike_review", version="v1")
    )
    repository.upsert_snapshot(
        _snapshot(
            domain_name="air_force_housing",
            playbook_id="housing_outlier_review",
            version="v1",
        )
    )
    repository.upsert_snapshot(
        _snapshot(playbook_id="identity_mismatch_review", version="v1")
    )

    page = repository.list_snapshots(domain_name="medicare_fraud", limit=2, offset=1)

    assert page.total == 3
    assert [(item.playbook_id, item.version) for item in page.items] == [
        ("identity_mismatch_review", "v2"),
        ("provider_billing_spike_review", "v1"),
    ]
