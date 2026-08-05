"""Tests for SAFE-CMS-020 governance report composition."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.explainability.reviews import (
    ExplanationReviewCreate,
    ExplanationReviewTarget,
    ExplanationReviewService,
    InMemoryExplanationReviewRepository,
)
from config.loader import load_config
from config.schema import FraudPlaybookConfig
from governance.service import GovernanceReportService
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import PlaybookSnapshot
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import (
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    WorkflowStepDefinition,
)

BASE_TIME = datetime(2026, 8, 5, 14, 0, tzinfo=timezone.utc)
KB_ID = "kb-governance"
DOMAIN_NAME = "medicare_fraud"


def test_report_lists_published_playbooks_and_approved_workflows() -> None:
    service = _service(
        playbook_snapshots=[
            _playbook_snapshot(playbook_id="billing-review", version="v2"),
        ],
        workflow_definitions=[
            _workflow_definition(
                definition_id="alert-review",
                version="v1",
                status="approved",
                approved_by="supervisor-1",
            ),
        ],
    )

    report = service.build_report(knowledge_base_id=KB_ID, domain_name=DOMAIN_NAME)

    assert [
        (
            item.component_kind,
            item.component_id,
            item.version,
            item.status,
            item.approved_by,
        )
        for item in report.production_versions
    ] == [
        ("playbook", "billing-review", "v2", "published", "supervisor-1"),
        ("workflow_definition", "alert-review", "v1", "approved", "supervisor-1"),
    ]
    assert report.release_ready is True
    assert report.release_blockers == []


def test_draft_workflow_definition_requires_approval_before_release() -> None:
    service = _service(
        playbook_snapshots=[
            _playbook_snapshot(playbook_id="billing-review", version="v1"),
        ],
        workflow_definitions=[
            _workflow_definition(
                definition_id="release-candidate",
                version="v3",
                status="draft",
            ),
        ],
    )

    report = service.build_report(knowledge_base_id=KB_ID, domain_name=DOMAIN_NAME)

    assert [
        (item.approval_kind, item.resource_id, item.version, item.status)
        for item in report.pending_approvals
    ] == [("workflow_definition", "release-candidate", "v3", "draft")]
    assert [
        (blocker.severity, blocker.code, blocker.resource_type, blocker.resource_id)
        for blocker in report.release_blockers
    ] == [
        (
            "blocking",
            "pending_workflow_approval",
            "workflow_definition",
            "release-candidate:v3",
        )
    ]
    assert report.release_ready is False


def test_challenged_explanation_reviews_feed_governance_trends() -> None:
    review_service = ExplanationReviewService(
        InMemoryExplanationReviewRepository(),
        clock=lambda: BASE_TIME,
    )
    review_service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id=KB_ID,
            evidence_pack_id="pack-1",
            target=ExplanationReviewTarget(
                target_type="narrative",
                target_id="narrative",
            ),
            state="unsupported",
            reasons=["unsupported_claim"],
            actor_user_id="analyst-1",
        )
    )
    review_service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id=KB_ID,
            evidence_pack_id="pack-2",
            target=ExplanationReviewTarget(
                target_type="feature_attribution",
                target_id="billing_frequency",
            ),
            state="approved",
            actor_user_id="supervisor-1",
        )
    )
    service = _service(
        playbook_snapshots=[
            _playbook_snapshot(playbook_id="billing-review", version="v1"),
        ],
        explanation_review_service=review_service,
    )

    report = service.build_report(knowledge_base_id=KB_ID, domain_name=DOMAIN_NAME)

    assert report.feedback_trends.total_reviews == 2
    assert report.feedback_trends.challenged_reviews == 1
    assert report.feedback_trends.approved_reviews == 1
    assert report.feedback_trends.state_counts == {"approved": 1, "unsupported": 1}
    assert [
        (blocker.severity, blocker.code, blocker.resource_type, blocker.resource_id)
        for blocker in report.release_blockers
    ] == [("warning", "challenged_explanations", "evidence_review", KB_ID)]
    assert report.release_ready is True


def test_report_blocks_release_without_published_playbook_baseline() -> None:
    service = _service()

    report = service.build_report(knowledge_base_id=KB_ID, domain_name=DOMAIN_NAME)

    assert report.production_versions == []
    assert [
        (blocker.severity, blocker.code, blocker.resource_type, blocker.resource_id)
        for blocker in report.release_blockers
    ] == [
        (
            "blocking",
            "missing_playbook_baseline",
            "playbook",
            KB_ID,
        )
    ]
    assert report.release_ready is False


def test_report_inventory_reads_beyond_first_repository_pages() -> None:
    playbook_snapshots = [
        _playbook_snapshot(playbook_id=f"playbook-{index:03}", version="v1")
        for index in range(101)
    ]
    workflow_definitions = [
        _workflow_definition(
            definition_id=f"approved-{index:03}",
            version="v1",
            status="approved",
            approved_by="supervisor-1",
        )
        for index in range(100)
    ]
    workflow_definitions.append(
        _workflow_definition(
            definition_id="draft-after-first-page",
            version="v2",
            status="draft",
        )
    )
    service = _service(
        playbook_snapshots=playbook_snapshots,
        workflow_definitions=workflow_definitions,
    )

    report = service.build_report(knowledge_base_id=KB_ID, domain_name=DOMAIN_NAME)

    assert any(
        item.component_kind == "playbook" and item.component_id == "playbook-100"
        for item in report.production_versions
    )
    assert any(
        item.approval_kind == "workflow_definition"
        and item.resource_id == "draft-after-first-page"
        for item in report.pending_approvals
    )
    assert any(
        blocker.code == "pending_workflow_approval"
        and blocker.resource_id == "draft-after-first-page:v2"
        for blocker in report.release_blockers
    )


def test_feedback_trends_count_reviews_beyond_first_page() -> None:
    review_service = ExplanationReviewService(
        InMemoryExplanationReviewRepository(),
        clock=lambda: BASE_TIME,
    )
    for index in range(200):
        review_service.record_review(
            ExplanationReviewCreate(
                knowledge_base_id=KB_ID,
                evidence_pack_id=f"pack-approved-{index:03}",
                target=ExplanationReviewTarget(
                    target_type="narrative",
                    target_id="narrative",
                ),
                state="approved",
                actor_user_id="supervisor-1",
            )
        )
    review_service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id=KB_ID,
            evidence_pack_id="pack-challenged-after-page",
            target=ExplanationReviewTarget(
                target_type="narrative",
                target_id="narrative",
            ),
            state="misleading",
            reasons=["contradicts_evidence"],
            actor_user_id="analyst-1",
        )
    )
    service = _service(
        playbook_snapshots=[
            _playbook_snapshot(playbook_id="billing-review", version="v1"),
        ],
        explanation_review_service=review_service,
    )

    report = service.build_report(knowledge_base_id=KB_ID, domain_name=DOMAIN_NAME)

    assert report.feedback_trends.total_reviews == 201
    assert report.feedback_trends.approved_reviews == 200
    assert report.feedback_trends.challenged_reviews == 1
    assert report.feedback_trends.state_counts == {"approved": 200, "misleading": 1}
    assert [blocker.code for blocker in report.release_blockers] == [
        "challenged_explanations"
    ]


def _service(
    *,
    playbook_snapshots: list[PlaybookSnapshot] | None = None,
    workflow_definitions: list[WorkflowDefinition] | None = None,
    explanation_review_service: ExplanationReviewService | None = None,
) -> GovernanceReportService:
    playbooks = InMemoryPlaybookRepository()
    for snapshot in playbook_snapshots or []:
        playbooks.upsert_snapshot(snapshot)
    workflows = InMemoryWorkflowDefinitionRepository(workflow_definitions or [])
    return GovernanceReportService(
        playbook_repository=playbooks,
        workflow_definition_repository=workflows,
        explanation_review_service=(
            explanation_review_service
            or ExplanationReviewService(InMemoryExplanationReviewRepository())
        ),
        clock=lambda: BASE_TIME,
    )


def _playbook_snapshot(*, playbook_id: str, version: str) -> PlaybookSnapshot:
    return PlaybookSnapshot(
        snapshot_id=f"{KB_ID}:{DOMAIN_NAME}:{playbook_id}:{version}",
        knowledge_base_id=KB_ID,
        domain_name=DOMAIN_NAME,
        playbook_id=playbook_id,
        version=version,
        status="published",
        definition=FraudPlaybookConfig(
            id=playbook_id,
            version=version,
            title="Billing review",
            status="published",
        ),
        source="api_publish",
        published_by="supervisor-1",
        published_at=BASE_TIME,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _workflow_definition(
    *,
    definition_id: str,
    version: str,
    status: WorkflowDefinitionStatus,
    approved_by: str | None = None,
) -> WorkflowDefinition:
    approved_at = BASE_TIME if approved_by is not None else None
    return WorkflowDefinition(
        definition_id=definition_id,
        knowledge_base_id=KB_ID,
        domain_name=load_config().domain.name,
        name="Provider release review",
        version=version,
        status=status,
        allowed_capability_refs=["rag.query"],
        steps=[
            WorkflowStepDefinition(
                step_id="ask-rag",
                label="Ask RAG",
                capability_ref="rag.query",
            )
        ],
        created_by="analyst-1",
        approved_by=approved_by,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        approved_at=approved_at,
        retired_at=None,
    )
