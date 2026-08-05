"""SAFE-CMS-020 governance report and evaluation services."""

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
    GovernanceBaselineDecision,
    GovernanceDriftSummary,
    GovernanceEvalRun,
    GovernanceEvalRunCreate,
    GovernanceEvalRunPage,
    GovernanceMetricInput,
    GovernanceMetricResult,
    GovernanceFeedbackTrend,
    GovernancePendingApproval,
    GovernanceReleaseBlocker,
    GovernanceReport,
    GovernanceVersionSummary,
)
from governance.repository import GovernanceEvalRepository
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
_PLAYBOOK_PAGE_LIMIT = 100
_WORKFLOW_PAGE_LIMIT = 100
_REVIEW_PAGE_LIMIT = 200
_EVAL_PAGE_LIMIT = 100


class GovernanceEvalError(Exception):
    """Base class for governance evaluation errors."""


class GovernanceEvalNotFoundError(GovernanceEvalError):
    """Raised when an evaluation run does not exist."""


class GovernanceEvalApprovalError(GovernanceEvalError):
    """Raised when a candidate cannot be approved."""


class GovernanceEvalService:
    """Record evaluation runs and baseline approval decisions."""

    def __init__(
        self,
        *,
        repository: GovernanceEvalRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def record_eval_run(self, payload: GovernanceEvalRunCreate) -> GovernanceEvalRun:
        metrics = [_metric_result(metric) for metric in payload.metrics]
        now = self._clock()
        run = GovernanceEvalRun(
            run_id=_run_id(payload),
            knowledge_base_id=payload.knowledge_base_id,
            artifact_kind=payload.artifact_kind,
            artifact_id=payload.artifact_id,
            artifact_version=payload.artifact_version,
            baseline_version=payload.baseline_version,
            dataset_id=payload.dataset_id,
            status="candidate",
            metrics=metrics,
            drift_summary=_drift_summary(metrics),
            dataset_source_refs=list(payload.dataset_source_refs),
            affected_alert_ids=list(payload.affected_alert_ids),
            affected_case_ids=list(payload.affected_case_ids),
            created_by=payload.created_by,
            created_at=now,
        )
        return self._repository.save_eval_run(run)

    def get_eval_run(self, run_id: str) -> GovernanceEvalRun:
        run = self._repository.get_eval_run(run_id)
        if run is None:
            raise GovernanceEvalNotFoundError(f"Governance eval run '{run_id}' not found.")
        return run

    def list_eval_runs(
        self, *, knowledge_base_id: str, limit: int = 50, offset: int = 0
    ) -> GovernanceEvalRunPage:
        return self._repository.list_eval_runs(
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            offset=offset,
        )

    def approve_baseline(
        self,
        *,
        run_id: str,
        approved_by: str,
        rationale: str,
    ) -> GovernanceEvalRun:
        run = self.get_eval_run(run_id)
        if run.status != "candidate":
            raise GovernanceEvalApprovalError("Only candidate eval runs can be approved.")
        if any(not metric.passed for metric in run.metrics):
            raise GovernanceEvalApprovalError(
                "Cannot approve eval run with failed metrics."
            )
        approved = run.model_copy(
            update={
                "status": "approved",
                "approval": GovernanceBaselineDecision(
                    decision="approved",
                    decided_by=approved_by,
                    decided_at=self._clock(),
                    rationale=rationale,
                ),
            }
        )
        return self._repository.update_eval_run(approved)

    def reject_baseline(
        self,
        *,
        run_id: str,
        rejected_by: str,
        rationale: str,
    ) -> GovernanceEvalRun:
        run = self.get_eval_run(run_id)
        if run.status != "candidate":
            raise GovernanceEvalApprovalError("Only candidate eval runs can be rejected.")
        rejected = run.model_copy(
            update={
                "status": "rejected",
                "approval": GovernanceBaselineDecision(
                    decision="rejected",
                    decided_by=rejected_by,
                    decided_at=self._clock(),
                    rationale=rationale,
                ),
            }
        )
        return self._repository.update_eval_run(rejected)

    def has_approved_eval(
        self,
        *,
        knowledge_base_id: str,
        artifact_kind: str,
        artifact_id: str,
        artifact_version: str,
    ) -> bool:
        page = self._repository.list_eval_runs(
            knowledge_base_id=knowledge_base_id,
            limit=_EVAL_PAGE_LIMIT,
            offset=0,
        )
        offset = 0
        while True:
            if any(
                run.status == "approved"
                and run.approval is not None
                and run.approval.decision == "approved"
                and run.artifact_kind == artifact_kind
                and run.artifact_id == artifact_id
                and run.artifact_version == artifact_version
                for run in page.items
            ):
                return True
            offset += len(page.items)
            if offset >= page.total_items or not page.items:
                return False
            page = self._repository.list_eval_runs(
                knowledge_base_id=knowledge_base_id,
                limit=_EVAL_PAGE_LIMIT,
                offset=offset,
            )


class GovernanceReportService:
    """Build read-only governance reports from existing durable artifacts."""

    def __init__(
        self,
        *,
        playbook_repository: PlaybookRepository,
        workflow_definition_repository: WorkflowDefinitionRepository,
        explanation_review_service: ExplanationReviewService,
        eval_repository: GovernanceEvalRepository | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._playbook_repository = playbook_repository
        self._workflow_definition_repository = workflow_definition_repository
        self._explanation_review_service = explanation_review_service
        self._eval_repository = eval_repository
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
        eval_runs = self._eval_runs(knowledge_base_id=knowledge_base_id)
        release_blockers = self._release_blockers(
            knowledge_base_id=knowledge_base_id,
            playbook_count=len(playbook_versions),
            production_versions=[*playbook_versions, *workflow_versions],
            pending_approvals=pending_approvals,
            feedback_trends=feedback_trends,
            eval_runs=eval_runs,
        )
        return GovernanceReport(
            knowledge_base_id=knowledge_base_id,
            domain_name=domain_name,
            generated_at=self._clock(),
            production_versions=[*playbook_versions, *workflow_versions],
            pending_approvals=pending_approvals,
            feedback_trends=feedback_trends,
            eval_runs=eval_runs,
            release_blockers=release_blockers,
        )

    def _playbook_versions(
        self, *, knowledge_base_id: str, domain_name: str
    ) -> list[GovernanceVersionSummary]:
        versions: list[GovernanceVersionSummary] = []
        offset = 0
        while True:
            page = self._playbook_repository.list_snapshots(
                knowledge_base_id=knowledge_base_id,
                domain_name=domain_name,
                limit=_PLAYBOOK_PAGE_LIMIT,
                offset=offset,
            )
            versions.extend(
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
            )
            offset += len(page.items)
            if offset >= page.total or not page.items:
                return versions

    def _workflow_versions(
        self, *, knowledge_base_id: str
    ) -> tuple[list[GovernanceVersionSummary], list[GovernancePendingApproval]]:
        versions: list[GovernanceVersionSummary] = []
        pending: list[GovernancePendingApproval] = []
        offset = 0
        while True:
            page = self._workflow_definition_repository.list_definitions(
                knowledge_base_id=knowledge_base_id,
                limit=_WORKFLOW_PAGE_LIMIT,
                offset=offset,
            )
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
            offset += len(page.items)
            if offset >= page.total_items or not page.items:
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
        first_page = self._explanation_review_service.list_reviews(
            ExplanationReviewQuery(
                knowledge_base_id=knowledge_base_id,
                limit=_REVIEW_PAGE_LIMIT,
                offset=0,
            )
        )
        if len(first_page.items) >= first_page.total:
            return first_page
        items = list(first_page.items)
        offset = len(first_page.items)
        while offset < first_page.total:
            page = self._explanation_review_service.list_reviews(
                ExplanationReviewQuery(
                    knowledge_base_id=knowledge_base_id,
                    limit=_REVIEW_PAGE_LIMIT,
                    offset=offset,
                )
            )
            items.extend(page.items)
            offset += len(page.items)
            if not page.items:
                break
        return ExplanationReviewPage(
            items=items,
            total=first_page.total,
            limit=first_page.limit,
            offset=0,
        )

    def _eval_runs(self, *, knowledge_base_id: str) -> list[GovernanceEvalRun]:
        if self._eval_repository is None:
            return []
        runs: list[GovernanceEvalRun] = []
        offset = 0
        while True:
            page = self._eval_repository.list_eval_runs(
                knowledge_base_id=knowledge_base_id,
                limit=_EVAL_PAGE_LIMIT,
                offset=offset,
            )
            runs.extend(page.items)
            offset += len(page.items)
            if offset >= page.total_items or not page.items:
                return runs

    @staticmethod
    def _release_blockers(
        *,
        knowledge_base_id: str,
        playbook_count: int,
        production_versions: list[GovernanceVersionSummary],
        pending_approvals: list[GovernancePendingApproval],
        feedback_trends: GovernanceFeedbackTrend,
        eval_runs: list[GovernanceEvalRun],
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
        approved_eval_keys = {
            (
                run.artifact_kind,
                run.artifact_id,
                run.artifact_version,
            )
            for run in eval_runs
            if run.status == "approved"
            and run.approval is not None
            and run.approval.decision == "approved"
        }
        for version in production_versions:
            if (
                version.component_kind,
                version.component_id,
                version.version,
            ) in approved_eval_keys:
                continue
            blockers.append(
                GovernanceReleaseBlocker(
                    severity="blocking",
                    code="missing_eval_approval",
                    message=(
                        "Approve a governance eval baseline for "
                        f"{version.component_kind} {version.component_id}:{version.version}."
                    ),
                    resource_type=version.component_kind,
                    resource_id=f"{version.component_id}:{version.version}",
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
        for run in eval_runs:
            failed_metrics = [metric for metric in run.metrics if not metric.passed]
            for metric in failed_metrics:
                blockers.append(
                    GovernanceReleaseBlocker(
                        severity="blocking",
                        code="failed_eval_metric",
                        message=(
                            f"Eval run {run.run_id} failed metric {metric.name} "
                            f"against baseline {run.baseline_version}."
                        ),
                        resource_type="governance_eval_run",
                        resource_id=run.run_id,
                    )
                )
            if run.status == "candidate" and not failed_metrics:
                blockers.append(
                    GovernanceReleaseBlocker(
                        severity="blocking",
                        code="pending_eval_approval",
                        message=(
                            f"Approve or reject governance eval run {run.run_id} "
                            "before release."
                        ),
                        resource_type="governance_eval_run",
                        resource_id=run.run_id,
                    )
                )
            if run.status == "rejected":
                blockers.append(
                    GovernanceReleaseBlocker(
                        severity="blocking",
                        code="rejected_eval_candidate",
                        message=(
                            f"Resolve rejected governance eval run {run.run_id} "
                            "before release."
                        ),
                        resource_type="governance_eval_run",
                        resource_id=run.run_id,
                    )
                )
        return blockers


def _metric_result(metric: GovernanceMetricInput) -> GovernanceMetricResult:
    delta = metric.candidate_value - metric.baseline_value
    passed = (
        delta >= -metric.threshold
        if metric.direction == "higher"
        else delta <= metric.threshold
    )
    return GovernanceMetricResult(
        name=metric.name,
        baseline_value=metric.baseline_value,
        candidate_value=metric.candidate_value,
        threshold=metric.threshold,
        direction=metric.direction,
        delta=delta,
        passed=passed,
    )


def _drift_summary(metrics: list[GovernanceMetricResult]) -> GovernanceDriftSummary:
    return GovernanceDriftSummary(
        metric_count=len(metrics),
        failed_metric_count=sum(1 for metric in metrics if not metric.passed),
        max_abs_delta=max((abs(metric.delta) for metric in metrics), default=0.0),
    )


def _run_id(payload: GovernanceEvalRunCreate) -> str:
    return (
        f"{payload.knowledge_base_id}:{payload.artifact_kind}:{payload.artifact_id}:"
        f"{payload.artifact_version}:{payload.dataset_id}"
    )


__all__ = [
    "CHALLENGED_REVIEW_STATES",
    "GovernanceEvalApprovalError",
    "GovernanceEvalError",
    "GovernanceEvalNotFoundError",
    "GovernanceEvalService",
    "GovernanceReportService",
]
