"""Tests for CMS DE-SynPUF fixture ingestion through the records pipeline.

These tests verify that the fixture CSV files (backend/tests/records/fixtures/cms/)
can be parsed, validated, and mapped to graph entities and relationships using
the medicare_fraud_cms_desynpuf domain config.  All checks run fully in-memory;
no external services are required.
"""

from __future__ import annotations

import pathlib

import pytest

from config.loader import load_config
from config.schema import DomainConfig, RecordFeedConfig, RecordsConfig
from records.adapters.sources.file_source import CsvFileSource
from records.mappers.feed_mapper import MappedGraph, map_batch
from records.models import RawRecord
from records.validation import validate_rows
from shared.utils import utc_now

_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "cms"
_CMS_CONFIG_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "config"
    / "defaults"
    / "medicare_fraud_cms_desynpuf.yaml"
)


@pytest.fixture(scope="module")
def cms_config() -> DomainConfig:
    config = load_config(str(_CMS_CONFIG_PATH))
    assert isinstance(config.records, RecordsConfig), "CMS config must have a records section"
    return config


def _feed(config: DomainConfig, name: str) -> RecordFeedConfig:
    """Return the named feed from the config, asserting it exists."""
    assert config.records is not None
    match = next((f for f in config.records.feeds if f.name == name), None)
    assert match is not None, f"Feed '{name}' not found in config"
    return match


def _load_csv(filename: str) -> list[dict[str, object]]:
    raw = (_FIXTURES / filename).read_bytes()
    return CsvFileSource().read_rows(raw)


def _rows_to_records(
    rows: list[dict[str, object]],
    *,
    feed_name: str,
    record_type: str,
    id_field: str,
    id_template: str | None = None,
) -> list[RawRecord]:
    now = utc_now()
    records: list[RawRecord] = []
    for i, row in enumerate(rows):
        if id_template:
            record_id = id_template.format(**{k: str(v) for k, v in row.items()})
        else:
            record_id = str(row[id_field])
        records.append(
            RawRecord(
                knowledge_base_id="kb-cms-test",
                record_type=record_type,
                record_id=record_id,
                payload=row,
                source_type="file_upload",
                source_ref=f"{feed_name}.csv",
                correlation_id=f"test-corr-{i}",
                content_hash=f"hash-{i}",
                ingested_at=now,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Column-count smoke tests — fixtures must exactly match CMS file layouts
# ---------------------------------------------------------------------------


def test_beneficiary_fixture_has_correct_column_count() -> None:
    rows = _load_csv("beneficiary_2008_sample.csv")
    assert len(rows) == 10
    # Blank cells are normalised to absent, but the required key must be present.
    for row in rows:
        assert "DESYNPUF_ID" in row


def test_carrier_claims_fixture_has_correct_column_count() -> None:
    rows = _load_csv("carrier_claims_sample.csv")
    assert len(rows) == 30
    for row in rows:
        assert "DESYNPUF_ID" in row
        assert "CLM_ID" in row
        assert "PRF_PHYSN_NPI_1" in row


def test_inpatient_fixture_has_correct_column_count() -> None:
    rows = _load_csv("inpatient_claims_sample.csv")
    assert len(rows) == 20
    for row in rows:
        assert "CLM_ID" in row
        assert "SEGMENT" in row


def test_outpatient_fixture_has_correct_column_count() -> None:
    rows = _load_csv("outpatient_claims_sample.csv")
    assert len(rows) == 20


def test_pde_fixture_has_correct_column_count() -> None:
    rows = _load_csv("pde_sample.csv")
    assert len(rows) == 30
    for row in rows:
        assert "PDE_ID" in row
        assert "SRVC_DT" in row


# ---------------------------------------------------------------------------
# Validation tests — feed schemas accept fixture data without errors
# ---------------------------------------------------------------------------


def test_beneficiary_rows_pass_validation(cms_config: DomainConfig) -> None:
    rows = _load_csv("beneficiary_2008_sample.csv")
    feed = _feed(cms_config, "beneficiary_2008")
    coerced = validate_rows(feed, rows)
    assert len(coerced) == 10
    # Birth dates coerced from YYYYMMDD to ISO-8601
    for row in coerced:
        bd = row.get("BENE_BIRTH_DT")
        if bd is not None:
            assert isinstance(bd, str)
            assert len(str(bd)) == 10
            assert str(bd)[4] == "-"


def test_carrier_rows_pass_validation(cms_config: DomainConfig) -> None:
    rows = _load_csv("carrier_claims_sample.csv")
    feed = _feed(cms_config, "carrier_claims_a")
    coerced = validate_rows(feed, rows)
    assert len(coerced) == 30
    # Service dates converted to ISO
    for row in coerced:
        sdt = row.get("CLM_FROM_DT")
        if sdt is not None:
            assert str(sdt)[4] == "-"


def test_inpatient_rows_pass_validation(cms_config: DomainConfig) -> None:
    rows = _load_csv("inpatient_claims_sample.csv")
    feed = _feed(cms_config, "inpatient_claims")
    coerced = validate_rows(feed, rows)
    assert len(coerced) == 20


def test_outpatient_rows_pass_validation(cms_config: DomainConfig) -> None:
    rows = _load_csv("outpatient_claims_sample.csv")
    feed = _feed(cms_config, "outpatient_claims")
    coerced = validate_rows(feed, rows)
    assert len(coerced) == 20


def test_pde_rows_pass_validation(cms_config: DomainConfig) -> None:
    rows = _load_csv("pde_sample.csv")
    feed = _feed(cms_config, "pde")
    coerced = validate_rows(feed, rows)
    assert len(coerced) == 30
    # Numeric fields coerced
    for row in coerced:
        assert isinstance(row["QTY_DSPNSD_NUM"], float)
        assert isinstance(row["DAYS_SUPLY_NUM"], int)


# ---------------------------------------------------------------------------
# Graph mapping tests — entities and edges are created from fixture data
# ---------------------------------------------------------------------------


def test_beneficiary_feed_creates_beneficiary_entities(
    cms_config: DomainConfig,
) -> None:
    rows = _load_csv("beneficiary_2008_sample.csv")
    feed = _feed(cms_config, "beneficiary_2008")
    coerced = validate_rows(feed, rows)
    records = _rows_to_records(coerced, feed_name="beneficiary_2008",
                               record_type=feed.record_type, id_field=feed.id_field)
    graph: MappedGraph = map_batch(feed, records)
    assert len(graph.entities) == 10
    entity_types = {e.type for e in graph.entities}
    assert entity_types == {"beneficiary"}
    assert len(graph.relationships) == 0


def test_carrier_feed_creates_claims_providers_and_edges(
    cms_config: DomainConfig,
) -> None:
    rows = _load_csv("carrier_claims_sample.csv")
    feed = _feed(cms_config, "carrier_claims_a")
    coerced = validate_rows(feed, rows)
    records = _rows_to_records(coerced, feed_name="carrier_claims_a",
                               record_type=feed.record_type, id_field=feed.id_field)
    graph: MappedGraph = map_batch(feed, records)

    entity_types = {e.type for e in graph.entities}
    assert "claim" in entity_types
    assert "beneficiary" in entity_types
    assert "provider" in entity_types

    rel_types = {r.type for r in graph.relationships}
    assert "billed_for" in rel_types      # claim → beneficiary
    assert "submitted_by" in rel_types    # claim → provider

    # 30 unique claim IDs, 10 beneficiaries, 3 providers
    claims = [e for e in graph.entities if e.type == "claim"]
    benes  = [e for e in graph.entities if e.type == "beneficiary"]
    provs  = [e for e in graph.entities if e.type == "provider"]
    assert len(claims) == 30
    assert len(benes) == 10
    assert len(provs) == 3

    # 30 billed_for edges + 30 submitted_by edges
    billed = [r for r in graph.relationships if r.type == "billed_for"]
    submitted = [r for r in graph.relationships if r.type == "submitted_by"]
    assert len(billed) == 30
    assert len(submitted) == 30


def test_inpatient_feed_creates_claims_facilities_and_edges(
    cms_config: DomainConfig,
) -> None:
    rows = _load_csv("inpatient_claims_sample.csv")
    feed = _feed(cms_config, "inpatient_claims")
    coerced = validate_rows(feed, rows)
    # id_template for composite record keys; entity id uses CLM_ID (merges segments)
    records = _rows_to_records(
        coerced,
        feed_name="inpatient_claims",
        record_type=feed.record_type,
        id_field=feed.id_field,
        id_template=feed.id_template,
    )
    graph: MappedGraph = map_batch(feed, records)

    entity_types = {e.type for e in graph.entities}
    assert "claim" in entity_types
    assert "beneficiary" in entity_types
    assert "facility" in entity_types

    rel_types = {r.type for r in graph.relationships}
    assert "billed_for" in rel_types
    assert "performed_at" in rel_types

    # 10 unique CLM_IDs (2 segments each merge into one claim node)
    claims = [e for e in graph.entities if e.type == "claim"]
    assert len(claims) == 10
    facilities = [e for e in graph.entities if e.type == "facility"]
    assert len(facilities) == 3


def test_pde_feed_creates_drug_claims_and_billed_for_edges(
    cms_config: DomainConfig,
) -> None:
    rows = _load_csv("pde_sample.csv")
    feed = _feed(cms_config, "pde")
    coerced = validate_rows(feed, rows)
    records = _rows_to_records(coerced, feed_name="pde",
                               record_type=feed.record_type, id_field=feed.id_field)
    graph: MappedGraph = map_batch(feed, records)

    assert {e.type for e in graph.entities} == {"claim", "beneficiary"}
    rel_types = {r.type for r in graph.relationships}
    assert "billed_for" in rel_types

    drug_claims = [e for e in graph.entities if e.type == "claim"]
    assert len(drug_claims) == 30  # unique PDE_IDs


def test_cross_feed_beneficiary_ids_are_consistent() -> None:
    """Beneficiaries referenced in claims must match those in the bene file."""
    bene_rows = _load_csv("beneficiary_2008_sample.csv")
    carrier_rows = _load_csv("carrier_claims_sample.csv")

    bene_ids = {str(r["DESYNPUF_ID"]) for r in bene_rows}
    carrier_bene_ids = {str(r["DESYNPUF_ID"]) for r in carrier_rows}

    # All carrier claims reference beneficiaries that exist in the bene file
    assert carrier_bene_ids.issubset(bene_ids)
