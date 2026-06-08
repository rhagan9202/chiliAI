"""Tests for the in-memory risk-history writer."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.risk.adapters.in_memory import InMemoryRiskHistoryWriter
from analytics.risk.adapters.protocols import RiskHistoryWriter
from analytics.risk.models import RiskAssessmentRecord, RiskFactor


def _record(request_id: str, *, score: float, entity_id: str = "claim:c1") -> RiskAssessmentRecord:
    return RiskAssessmentRecord(
        knowledge_base_id="kb-1",
        entity_id=entity_id,
        request_id=request_id,
        overall_score=score,
        risk_level="high",
        factors=[
            RiskFactor(
                factor_name="anomaly",
                raw_value=0.9,
                weight=1.0,
                contribution=0.9,
            )
        ],
        assessed_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )


def _record_for_kb(
    request_id: str, *, kb: str, score: float, entity_id: str = "claim:c1"
) -> RiskAssessmentRecord:
    return RiskAssessmentRecord(
        knowledge_base_id=kb,
        entity_id=entity_id,
        request_id=request_id,
        overall_score=score,
        risk_level="high",
        factors=[
            RiskFactor(
                factor_name="anomaly",
                raw_value=0.9,
                weight=1.0,
                contribution=0.9,
            )
        ],
        assessed_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )


def test_writer_satisfies_protocol() -> None:
    writer: RiskHistoryWriter = InMemoryRiskHistoryWriter()
    assert writer.load_historical_score(knowledge_base_id="kb-x", entity_id="e-x") is None


def test_write_assessment_is_idempotent_per_request_id() -> None:
    writer = InMemoryRiskHistoryWriter()
    assert writer.write_assessment(_record("req-1", score=0.7)) is True
    assert writer.write_assessment(_record("req-1", score=0.7)) is False


def test_load_historical_score_returns_latest() -> None:
    writer = InMemoryRiskHistoryWriter()
    writer.write_assessment(_record("req-1", score=0.4))
    later = _record("req-2", score=0.8)
    later = later.model_copy(
        update={"assessed_at": datetime(2026, 5, 17, tzinfo=timezone.utc)}
    )
    writer.write_assessment(later)
    assert (
        writer.load_historical_score(knowledge_base_id="kb-1", entity_id="claim:c1")
        == 0.8
    )


def test_delete_by_kb_removes_only_target_kb() -> None:
    writer = InMemoryRiskHistoryWriter()
    # Seed two records for kb1 and one for kb2.
    writer.write_assessment(_record_for_kb("req-k1a", kb="kb1", score=0.3))
    writer.write_assessment(_record_for_kb("req-k1b", kb="kb1", score=0.7, entity_id="claim:c2"))
    writer.write_assessment(_record_for_kb("req-k2a", kb="kb2", score=0.5))

    removed = writer.delete_by_kb("kb1")
    assert removed == 2

    # kb1 records are gone.
    assert writer.load_historical_score(knowledge_base_id="kb1", entity_id="claim:c1") is None
    assert writer.load_historical_score(knowledge_base_id="kb1", entity_id="claim:c2") is None

    # kb2 record is intact.
    assert writer.load_historical_score(knowledge_base_id="kb2", entity_id="claim:c1") == 0.5

    # Idempotent: second call removes nothing.
    assert writer.delete_by_kb("kb1") == 0
