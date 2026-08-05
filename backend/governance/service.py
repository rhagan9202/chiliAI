"""SAFE-CMS-020 governance report service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from analytics.explainability.reviews import (
    ExplanationReviewPage,
    ExplanationReviewQuery,
    ExplanationReviewService,
    ExplanationReviewState,
)
from governance.models import (
    GovernanceFeedbackTrend,
    GovernancePendingApproval,
    GovernanceReleaseBlocker,
    GovernanceReport,
    GovernanceVersionSummary,
)
from playbooks.repository import PlaybookRepository
from shared.utils import utc_now
from workflow_definitions.repository import WorkflowDefinitionRepository

CHALLENGED_REVIEW_STATES: frozenset[ExplanationReviewState] = frozenset(
    {
        "incomplete",
        "misleading",
        "unsupported",
        "rejected",
        "regeneration_requested",
    }
)


class GovernanceReportService:
    """Build read-only governance reports from existing durable artifacts."""

    def __init__(
        self,
        *,
        playbook_repository: PlaybookRepository,
        workflow_definition_repository: WorkflowDefinitionRepository,
        explanation_review_service: ExplanationReviewService,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._playbook_repository = playbook_repository
        self._workflow_definition_repository = workflow_definition_repository
        self._explanation_review_service = explanation_review_service
        self._clock = clock

    def build_report(self, *, knowledge_base_id: str, domain_name: str) -> GovernanceReport:
        playbook_versions = self._playbook_versions(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
        )
        workflow_versions, pending_approvals = self._workflow_versions(
            knowledge_base_id=knowledge_base_id
        )
        feedback_trends = self._feedback_trends(knowledge_base_id=knowledge_base_id)
        release_blockers = self._release_blockers(
            knowledge_base_id=knowledge_base_id,
            playbook_count=len(playbook_versions),
            pending_approvals=pending_approvals,
            feedback_trends=feedback_trends,
        )
        return GovernanceReport(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
            generated_at=self._clock(),
            production_versions=[*playbook_versions, *workflow_versions],
            pending_approvals=pending_approvals,
            feedback_trends=feedback_trends,
            release_blockers=release_blockers,
        )

    def _playbook_versions(
        self, *, knowledge_base_id: str, domain_name: str
    ) -> list[GovernanceVersionSummary]:
        page = self._playbook_repository.list_snapshots(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
            limit=100,
            offset=0,
        )
        return [
            GovernanceVersionSummary(
                component_kind="playbook",
                component_id=snapshot.playbook_id,
                version=snapshot.version,
                status=snapshot.status,
                source=snapshot.source,
                approved_by=snapshot.published_by,
                approved_at=snapshot.published_at,
            )
            for snapshot in page.items
            if snapshot.status == "published"
        ]

    def _workflow_versions(
        self, *, knowledge_base_id: str
    ) -> tuple[list[GovernanceVersionSummary], list[GovernancePendingApproval]]:
        page = self._workflow_definition_repository.list_definitions(
            knowledge_base_id=knowledge_base_id,
            limit=100,
            offset=0,
        )
        versions: list[GovernanceVersionSummary] = []
        pending: list[GovernancePendingApproval] = []
        for definition in page.items:
            if definition.status == "approved":
                versions.append(
                    GovernanceVersionSummary(
                        component_kind="workflow_definition",
                        component_id=definition.definition_id,
                        version=definition.version,
                        status=definition.status,
                        source="workflow_definition",
                        approved_by=definition.approved_by,
                        approved_at=definition.approved_at,
                    )
                )
            elif definition.status == "draft":
                pending.append(
                    GovernancePendingApproval(
                        approval_kind="workflow_definition",
                        resource_id=definition.definition_id,
                        version=definition.version,
                        status=definition.status,
                        requested_by=definition.created_by,
                        updated_at=definition.updated_at,
                    )
                )
        return versions, pending

    def _feedback_trends(self, *, knowledge_base_id: str) -> GovernanceFeedbackTrend:
        page = self._list_all_reviews(knowledge_base_id=knowledge_base_id)
        state_counts: dict[str, int] = {}
        challenged_reviews = 0
        approved_reviews = 0
        for review in page.items:
            state_counts[review.state] = state_counts.get(review.state, 0) + 1
            if review.state in CHALLENGED_REVIEW_STATES:
                challenged_reviews += 1
            if review.state == "approved":
                approved_reviews += 1
        return GovernanceFeedbackTrend(
            total_reviews=page.total,
            challenged_reviews=challenged_reviews,
            approved_reviews=approved_reviews,
            state_counts=dict(sorted(state_counts.items())),
        )

    def _list_all_reviews(self, *, knowledge_base_id: str) -> ExplanationReviewPage:
        return self._explanation_review_service.list_reviews(
            ExplanationReviewQuery(
                knowledge_base_id=knowledge_base_id,
                limit=200,
                offset=0,
            )
        )

    @staticmethod
    def _release_blockers(
        *,
        knowledge_base_id: str,
        playbook_count: int,
        pending_approvals: list[GovernancePendingApproval],
        feedback_trends: GovernanceFeedbackTrend,
    ) -> list[GovernanceReleaseBlocker]:
        blockers: list[GovernanceReleaseBlocker] = []
        if playbook_count == 0:
            blockers.append(
                GovernanceReleaseBlocker(
                    severity="blocking",
                    code="missing_playbook_baseline",
                    message="Publish at least one playbook snapshot before release.",
                    resource_type="playbook",
                    resource_id=knowledge_base_id,
                )
            )
        for approval in pending_approvals:
            blockers.append(
                GovernanceReleaseBlocker(
                    severity="blocking",
                    code="pending_workflow_approval",
                    message=(
                        "Approve or retire workflow definition "
                        f"{approval.resource_id}:{approval.version} before release."
                    ),
                    resource_type=approval.approval_kind,
                    resource_id=f"{approval.resource_id}:{approval.version}",
                )
            )
        if feedback_trends.challenged_reviews > 0:
            blockers.append(
                GovernanceReleaseBlocker(
                    severity="warning",
                    code="challenged_explanations",
                    message=(
                        f"{feedback_trends.challenged_reviews} challenged explanation "
                        "review(s) should be reviewed before release."
                    ),
                    resource_type="evidence_review",
                    resource_id=knowledge_base_id,
                )
            )
        return blockers


__all__ = ["CHALLENGED_REVIEW_STATES", "GovernanceReportService"]
