"""Tests for SAFE-CMS-020 governance evaluation baselines."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.explainability.reviews import (
    ExplanationReviewService,
    InMemoryExplanationReviewRepository,
)
from governance.adapters.in_memory import InMemoryGovernanceEvalRepository
from governance.models import (
    GovernanceBaselineDecision,
    GovernanceComponentKind,
    GovernanceDriftSummary,
    GovernanceEvalRun,
    GovernanceEvalRunCreate,
    GovernanceMetricDirection,
    GovernanceMetricInput,
    GovernanceMetricResult,
)
from governance.service import (
    GovernanceEvalApprovalError,
    GovernanceEvalService,
    GovernanceReportService,
)
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import PlaybookSnapshot
from config.schema import FraudPlaybookConfig
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository

BASE_TIME = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
KB_ID = "kb-governance-evals"
DOMAIN_NAME = "medicare_fraud"


def test_record_eval_run_persists_metric_results_and_drift_summary() -> None:
    service = _eval_service()

    run = service.record_eval_run(
        GovernanceEvalRunCreate(
            knowledge_base_id=KB_ID,
            artifact_kind="model",
            artifact_id="risk-scorer",
            artifact_version="candidate-v2",
            baseline_version="prod-v1",
            dataset_id="tn-demo-1pct",
            metrics=[
                _metric("precision", baseline=0.72, candidate=0.78, direction="higher"),
                _metric(
                    "false_positive_rate",
                    baseline=0.22,
                    candidate=0.18,
                    direction="lower",
                ),
            ],
            dataset_source_refs=["explanation_review:pack-1:narrative:narrative"],
            affected_alert_ids=["alert-1"],
            affected_case_ids=["case-1"],
            created_by="model-owner-1",
        )
    )

    assert run.run_id == "kb-governance-evals:model:risk-scorer:candidate-v2:tn-demo-1pct"
    assert run.status == "candidate"
    assert run.created_at == BASE_TIME
    assert [(metric.name, metric.passed) for metric in run.metrics] == [
        ("precision", True),
        ("false_positive_rate", True),
    ]
    assert run.drift_summary.failed_metric_count == 0
    assert run.drift_summary.max_abs_delta == pytest.approx(0.06)
    assert run.dataset_source_refs == ["explanation_review:pack-1:narrative:narrative"]
    assert run.affected_alert_ids == ["alert-1"]
    assert run.affected_case_ids == ["case-1"]

    assert service.get_eval_run(run.run_id) == run


def test_approval_gate_blocks_failed_candidate_metrics() -> None:
    service = _eval_service()
    run = service.record_eval_run(
        GovernanceEvalRunCreate(
            knowledge_base_id=KB_ID,
            artifact_kind="playbook",
            artifact_id="billing-review",
            artifact_version="candidate-v3",
            baseline_version="v2",
            dataset_id="tn-demo-1pct",
            metrics=[
                _metric("precision", baseline=0.72, candidate=0.68, direction="higher"),
            ],
            created_by="model-owner-1",
        )
    )

    with pytest.raises(GovernanceEvalApprovalError, match="failed metrics"):
        service.approve_baseline(
            run_id=run.run_id,
            approved_by="supervisor-1",
            rationale="Promote candidate.",
        )

    assert service.get_eval_run(run.run_id).status == "candidate"


def test_approval_gate_records_baseline_decision_for_passing_candidate() -> None:
    service = _eval_service()
    run = service.record_eval_run(
        GovernanceEvalRunCreate(
            knowledge_base_id=KB_ID,
            artifact_kind="workflow_definition",
            artifact_id="provider-review",
            artifact_version="v2",
            baseline_version="v1",
            dataset_id="tn-demo-1pct",
            metrics=[
                _metric("completion_rate", baseline=0.94, candidate=0.97, direction="higher"),
            ],
            created_by="model-owner-1",
        )
    )

    approved = service.approve_baseline(
        run_id=run.run_id,
        approved_by="supervisor-1",
        rationale="Candidate improves completion rate.",
    )

    assert approved.status == "approved"
    assert approved.approval is not None
    assert approved.approval.decision == "approved"
    assert approved.approval.decided_by == "supervisor-1"
    assert approved.approval.rationale == "Candidate improves completion rate."


def test_reject_baseline_records_decision_and_blocks_release() -> None:
    eval_repository = InMemoryGovernanceEvalRepository()
    eval_service = _eval_service(eval_repository=eval_repository)
    run = eval_service.record_eval_run(
        GovernanceEvalRunCreate(
            knowledge_base_id=KB_ID,
            artifact_kind="playbook",
            artifact_id="billing-review",
            artifact_version="v2",
            baseline_version="v1",
            dataset_id="tn-demo-1pct",
            metrics=[
                _metric("precision", baseline=0.72, candidate=0.78, direction="higher"),
            ],
            created_by="model-owner-1",
        )
    )

    rejected = eval_service.reject_baseline(
        run_id=run.run_id,
        rejected_by="supervisor-1",
        rationale="Needs a larger eval dataset.",
    )
    report = _report_service(eval_repository).build_report(
        knowledge_base_id=KB_ID,
        domain_name=DOMAIN_NAME,
    )

    assert rejected.status == "rejected"
    assert rejected.approval is not None
    assert rejected.approval.decision == "rejected"
    assert ("blocking", "rejected_eval_candidate", run.run_id) in [
        (blocker.severity, blocker.code, blocker.resource_id)
        for blocker in report.release_blockers
    ]


def test_report_requires_approved_eval_coverage_for_production_versions() -> None:
    eval_repository = InMemoryGovernanceEvalRepository()
    report_service = _report_service(eval_repository)

    report = report_service.build_report(
        knowledge_base_id=KB_ID,
        domain_name=DOMAIN_NAME,
    )

    assert [
        (blocker.severity, blocker.code, blocker.resource_type, blocker.resource_id)
        for blocker in report.release_blockers
    ] == [
        (
            "blocking",
            "missing_eval_approval",
            "playbook",
            "billing-review:v1",
        )
    ]
    assert report.release_ready is False

    eval_repository.save_eval_run(
        _approved_run(
            artifact_kind="playbook",
            artifact_id="billing-review",
            artifact_version="v1",
        )
    )
    approved_report = report_service.build_report(
        knowledge_base_id=KB_ID,
        domain_name=DOMAIN_NAME,
    )

    assert approved_report.release_blockers == []
    assert approved_report.release_ready is True


def test_report_blocks_release_for_unapproved_eval_candidate() -> None:
    eval_repository = InMemoryGovernanceEvalRepository()
    eval_service = _eval_service(eval_repository=eval_repository)
    eval_service.record_eval_run(
        GovernanceEvalRunCreate(
            knowledge_base_id=KB_ID,
            artifact_kind="model",
            artifact_id="risk-scorer",
            artifact_version="candidate-v2",
            baseline_version="prod-v1",
            dataset_id="tn-demo-1pct",
            metrics=[
                _metric("precision", baseline=0.72, candidate=0.78, direction="higher"),
            ],
            created_by="model-owner-1",
        )
    )
    report_service = _report_service(eval_repository)

    report = report_service.build_report(
        knowledge_base_id=KB_ID,
        domain_name=DOMAIN_NAME,
    )

    assert [(run.artifact_kind, run.artifact_id, run.status) for run in report.eval_runs] == [
        ("model", "risk-scorer", "candidate")
    ]
    assert [
        (blocker.severity, blocker.code, blocker.resource_type, blocker.resource_id)
        for blocker in report.release_blockers
    ] == [
        (
            "blocking",
            "missing_eval_approval",
            "playbook",
            "billing-review:v1",
        ),
        (
            "blocking",
            "pending_eval_approval",
            "governance_eval_run",
            "kb-governance-evals:model:risk-scorer:candidate-v2:tn-demo-1pct",
        )
    ]
    assert report.release_ready is False


def _eval_service(
    *, eval_repository: InMemoryGovernanceEvalRepository | None = None
) -> GovernanceEvalService:
    return GovernanceEvalService(
        repository=eval_repository or InMemoryGovernanceEvalRepository(),
        clock=lambda: BASE_TIME,
    )


def _approved_run(
    *,
    artifact_kind: GovernanceComponentKind,
    artifact_id: str,
    artifact_version: str,
) -> GovernanceEvalRun:
    return GovernanceEvalRun(
        run_id=f"{KB_ID}:{artifact_kind}:{artifact_id}:{artifact_version}:tn-demo-1pct",
        knowledge_base_id=KB_ID,
        artifact_kind=artifact_kind,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        baseline_version="baseline-v1",
        dataset_id="tn-demo-1pct",
        status="approved",
        metrics=[
            GovernanceMetricResult(
                name="precision",
                baseline_value=0.72,
                candidate_value=0.78,
                threshold=0.0,
                direction="higher",
                delta=0.06,
                passed=True,
            )
        ],
        drift_summary=GovernanceDriftSummary(
            metric_count=1,
            failed_metric_count=0,
            max_abs_delta=0.06,
        ),
        dataset_source_refs=["explanation_review:pack-1:narrative:narrative"],
        created_by="model-owner-1",
        created_at=BASE_TIME,
        approval=GovernanceBaselineDecision(
            decision="approved",
            decided_by="supervisor-1",
            decided_at=BASE_TIME,
            rationale="Approved baseline.",
        ),
    )


def _report_service(
    eval_repository: InMemoryGovernanceEvalRepository,
) -> GovernanceReportService:
    playbooks = InMemoryPlaybookRepository()
    playbooks.upsert_snapshot(_playbook_snapshot())
    return GovernanceReportService(
        playbook_repository=playbooks,
        workflow_definition_repository=InMemoryWorkflowDefinitionRepository(),
        explanation_review_service=ExplanationReviewService(
            InMemoryExplanationReviewRepository()
        ),
        eval_repository=eval_repository,
        clock=lambda: BASE_TIME,
    )


def _metric(
    name: str,
    *,
    baseline: float,
    candidate: float,
    direction: GovernanceMetricDirection,
) -> GovernanceMetricInput:
    return GovernanceMetricInput(
        name=name,
        baseline_value=baseline,
        candidate_value=candidate,
        threshold=0.0,
        direction=direction,
    )


def _playbook_snapshot() -> PlaybookSnapshot:
    return PlaybookSnapshot(
        snapshot_id=f"{KB_ID}:{DOMAIN_NAME}:billing-review:v1",
        knowledge_base_id=KB_ID,
        domain_name=DOMAIN_NAME,
        playbook_id="billing-review",
        version="v1",
        definition=FraudPlaybookConfig(
            id="billing-review",
            version="v1",
            title="Billing review",
            status="published",
        ),
        source="api_publish",
        published_by="supervisor-1",
        published_at=BASE_TIME,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
