"""Tests for SAFE-CMS-020 governance API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from analytics.explainability.reviews import (
    ExplanationReviewCreate,
    ExplanationReviewTarget,
    ExplanationReviewService,
    InMemoryExplanationReviewRepository,
)
from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_explanation_review_service,
    get_governance_eval_repository,
    get_knowledge_base_repository,
    get_playbook_repository,
    get_workflow_definition_repository,
)
from api.middleware.auth import User, get_current_user
from config.loader import load_config
from config.schema import AuthConfig, FraudPlaybookConfig
from governance.adapters.in_memory import InMemoryGovernanceEvalRepository
from governance.models import (
    GovernanceBaselineDecision,
    GovernanceComponentKind,
    GovernanceDriftSummary,
    GovernanceEvalRun,
    GovernanceMetricResult,
)
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from playbooks.adapters.in_memory import InMemoryPlaybookRepository
from playbooks.models import PlaybookSnapshot
from shared.types import KnowledgeBase
from workflow_definitions.adapters.in_memory import InMemoryWorkflowDefinitionRepository
from workflow_definitions.models import WorkflowDefinition, WorkflowStepDefinition

BASE_TIME = datetime(2026, 8, 5, 14, 30, tzinfo=timezone.utc)
KB_ID = "kb-governance"
BASE_URL = f"/knowledgebases/{KB_ID}/governance/report"
EVAL_RUNS_URL = f"/knowledgebases/{KB_ID}/governance/eval-runs"


def test_viewer_can_fetch_governance_report_for_authorized_kb() -> None:
    app, playbooks, workflows, evals, _ = _app_harness()
    playbooks.upsert_snapshot(_playbook_snapshot("billing-review", "v1"))
    workflows.save_definition(_workflow_definition("provider-review", "v1"))
    evals.save_eval_run(
        _approved_governance_eval_run(
            artifact_kind="playbook",
            artifact_id="billing-review",
            artifact_version="v1",
        )
    )
    evals.save_eval_run(
        _approved_governance_eval_run(
            artifact_kind="workflow_definition",
            artifact_id="provider-review",
            artifact_version="v1",
        )
    )
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_base_id"] == KB_ID
    assert body["domain_name"] == "medicare_fraud"
    assert body["release_ready"] is True
    assert body["feedback_trends"]["total_reviews"] == 0
    assert [
        (item["component_kind"], item["component_id"], item["version"], item["status"])
        for item in body["production_versions"]
    ] == [
        ("playbook", "billing-review", "v1", "published"),
        ("workflow_definition", "provider-review", "v1", "approved"),
    ]


def test_out_of_scope_kb_returns_404() -> None:
    app, _, _, _, _ = _app_harness()
    _set_user(app, _user("viewer", knowledge_base_ids=["other-kb"]))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 404


def test_missing_published_playbook_baseline_blocks_report() -> None:
    app, _, workflows, _, _ = _app_harness()
    workflows.save_definition(_workflow_definition("provider-review", "v1"))
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(BASE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["release_ready"] is False
    assert [
        (
            blocker["severity"],
            blocker["code"],
            blocker["resource_type"],
            blocker["resource_id"],
        )
        for blocker in body["release_blockers"]
    ] == [
        (
            "blocking",
            "missing_playbook_baseline",
            "playbook",
            KB_ID,
        ),
        (
            "blocking",
            "missing_eval_approval",
            "workflow_definition",
            "provider-review:v1",
        ),
    ]


def test_analyst_can_record_eval_run_and_report_blocks_until_approved() -> None:
    app, playbooks, _, _, reviews = _app_harness()
    playbooks.upsert_snapshot(_playbook_snapshot("billing-review", "v1"))
    reviews.record_review(
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
    _set_user(app, _user("analyst"))

    with TestClient(app) as client:
        create_response = client.post(
            EVAL_RUNS_URL,
            json={
                "artifact_kind": "model",
                "artifact_id": "risk-scorer",
                "artifact_version": "candidate-v2",
                "baseline_version": "prod-v1",
                "dataset_id": "tn-demo-1pct",
                "metrics": [
                    {
                        "name": "precision",
                        "baseline_value": 0.72,
                        "candidate_value": 0.78,
                        "threshold": 0.0,
                        "direction": "higher",
                    }
                ],
                "affected_alert_ids": ["alert-1"],
                "affected_case_ids": ["case-1"],
            },
        )
        report_response = client.get(BASE_URL)

    assert create_response.status_code == 201
    body = create_response.json()
    assert body["run_id"] == "kb-governance:model:risk-scorer:candidate-v2:tn-demo-1pct"
    assert body["status"] == "candidate"
    assert body["metrics"][0]["passed"] is True
    assert body["drift_summary"]["failed_metric_count"] == 0
    assert body["dataset_source_refs"] == [
        "explanation_review:pack-1:narrative:narrative"
    ]

    report = report_response.json()
    assert [
        (run["artifact_kind"], run["artifact_id"], run["status"])
        for run in report["eval_runs"]
    ] == [("model", "risk-scorer", "candidate")]
    assert ("blocking", "pending_eval_approval", "governance_eval_run") in [
        (blocker["severity"], blocker["code"], blocker["resource_type"])
        for blocker in report["release_blockers"]
    ]
    assert report["release_ready"] is False


def test_duplicate_eval_run_submission_returns_409() -> None:
    app, _, _, _, _ = _app_harness()
    _set_user(app, _user("analyst"))
    payload = {
        "artifact_kind": "model",
        "artifact_id": "risk-scorer",
        "artifact_version": "candidate-v2",
        "baseline_version": "prod-v1",
        "dataset_id": "tn-demo-1pct",
        "metrics": [
            {
                "name": "precision",
                "baseline_value": 0.72,
                "candidate_value": 0.78,
                "threshold": 0.0,
                "direction": "higher",
            }
        ],
    }

    with TestClient(app) as client:
        first = client.post(EVAL_RUNS_URL, json=payload)
        second = client.post(EVAL_RUNS_URL, json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == (
        "Governance eval run 'kb-governance:model:risk-scorer:candidate-v2:tn-demo-1pct' "
        "already exists."
    )


def test_eval_run_list_reports_total_items_beyond_first_page() -> None:
    app, _, _, evals, _ = _app_harness()
    for index in range(51):
        evals.save_eval_run(
            _governance_eval_run(
                artifact_id=f"risk-scorer-{index:03}",
                created_at=datetime(2026, 8, 5, 12, index % 60, tzinfo=timezone.utc),
            )
        )
    _set_user(app, _user("viewer"))

    with TestClient(app) as client:
        response = client.get(f"{EVAL_RUNS_URL}?limit=50&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 50
    assert body["total_items"] == 51


def test_admin_approval_promotes_passing_eval_candidate() -> None:
    app, _, _, _, _ = _app_harness()
    _set_user(app, _user("admin"))

    with TestClient(app) as client:
        create_response = client.post(
            EVAL_RUNS_URL,
            json={
                "artifact_kind": "workflow_definition",
                "artifact_id": "provider-review",
                "artifact_version": "v2",
                "baseline_version": "v1",
                "dataset_id": "tn-demo-1pct",
                "metrics": [
                    {
                        "name": "completion_rate",
                        "baseline_value": 0.94,
                        "candidate_value": 0.97,
                        "threshold": 0.0,
                        "direction": "higher",
                    }
                ],
            },
        )
        run_id = create_response.json()["run_id"]
        approval_response = client.post(
            f"{EVAL_RUNS_URL}/{run_id}/approve",
            json={"rationale": "Candidate improves completion rate."},
        )

    assert approval_response.status_code == 200
    body = approval_response.json()
    assert body["status"] == "approved"
    assert body["approval"]["decision"] == "approved"
    assert body["approval"]["decided_by"] == "admin-1"


def test_admin_approval_rejects_failed_eval_candidate() -> None:
    app, _, _, _, _ = _app_harness()
    _set_user(app, _user("admin"))

    with TestClient(app) as client:
        create_response = client.post(
            EVAL_RUNS_URL,
            json={
                "artifact_kind": "model",
                "artifact_id": "risk-scorer",
                "artifact_version": "candidate-v2",
                "baseline_version": "prod-v1",
                "dataset_id": "tn-demo-1pct",
                "metrics": [
                    {
                        "name": "precision",
                        "baseline_value": 0.72,
                        "candidate_value": 0.68,
                        "threshold": 0.0,
                        "direction": "higher",
                    }
                ],
            },
        )
        run_id = create_response.json()["run_id"]
        approval_response = client.post(
            f"{EVAL_RUNS_URL}/{run_id}/approve",
            json={"rationale": "Promote candidate."},
        )

    assert approval_response.status_code == 409
    assert approval_response.json()["detail"] == "Cannot approve eval run with failed metrics."


def test_admin_cannot_approve_eval_run_through_different_kb_path() -> None:
    app, _, _, evals, _ = _app_harness()
    run = _governance_eval_run()
    evals.save_eval_run(run)
    _set_user(app, _user("admin", knowledge_base_ids=[KB_ID, "other-kb"]))

    with TestClient(app) as client:
        response = client.post(
            f"/knowledgebases/other-kb/governance/eval-runs/{run.run_id}/approve",
            json={"rationale": "Promote candidate."},
        )

    assert response.status_code == 404
    persisted = evals.get_eval_run(run.run_id)
    assert persisted is not None
    assert persisted.status == "candidate"


def test_admin_can_reject_eval_candidate_and_report_blocks_release() -> None:
    app, _, _, _, _ = _app_harness()
    _set_user(app, _user("admin"))

    with TestClient(app) as client:
        create_response = client.post(
            EVAL_RUNS_URL,
            json={
                "artifact_kind": "model",
                "artifact_id": "risk-scorer",
                "artifact_version": "candidate-v2",
                "baseline_version": "prod-v1",
                "dataset_id": "tn-demo-1pct",
                "metrics": [
                    {
                        "name": "precision",
                        "baseline_value": 0.72,
                        "candidate_value": 0.78,
                        "threshold": 0.0,
                        "direction": "higher",
                    }
                ],
            },
        )
        run_id = create_response.json()["run_id"]
        reject_response = client.post(
            f"{EVAL_RUNS_URL}/{run_id}/reject",
            json={"rationale": "Dataset is too small."},
        )
        report_response = client.get(BASE_URL)

    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    assert ("blocking", "rejected_eval_candidate", run_id) in [
        (blocker["severity"], blocker["code"], blocker["resource_id"])
        for blocker in report_response.json()["release_blockers"]
    ]


def _app_harness() -> tuple[
    FastAPI,
    InMemoryPlaybookRepository,
    InMemoryWorkflowDefinitionRepository,
    InMemoryGovernanceEvalRepository,
    ExplanationReviewService,
]:
    app = create_app()
    kb_repository = InMemoryKnowledgeBaseRepository()
    kb_repository.create(
        KnowledgeBase(
            id=KB_ID,
            name="Governance KB",
            description="Governance API test KB",
            domain="medicare_fraud",
            created_at=BASE_TIME,
        )
    )
    kb_repository.create(
        KnowledgeBase(
            id="other-kb",
            name="Other governance KB",
            description="Other Governance API test KB",
            domain="medicare_fraud",
            created_at=BASE_TIME,
        )
    )
    playbooks = InMemoryPlaybookRepository()
    workflows = InMemoryWorkflowDefinitionRepository()
    reviews = ExplanationReviewService(InMemoryExplanationReviewRepository())
    evals = InMemoryGovernanceEvalRepository()

    app.dependency_overrides[get_domain_config] = lambda: load_config().model_copy(
        update={"auth": AuthConfig(enabled=True)}
    )
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_playbook_repository] = lambda: playbooks
    app.dependency_overrides[get_workflow_definition_repository] = lambda: workflows
    app.dependency_overrides[get_explanation_review_service] = lambda: reviews
    app.dependency_overrides[get_governance_eval_repository] = lambda: evals
    return app, playbooks, workflows, evals, reviews


def _set_user(app: FastAPI, user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _user(role: str, *, knowledge_base_ids: list[str] | None = None) -> User:
    return User(
        user_id=f"{role}-1",
        roles=[role],
        email=f"{role}-1@example.test",
        knowledge_base_ids=knowledge_base_ids if knowledge_base_ids is not None else [KB_ID],
    )


def _playbook_snapshot(playbook_id: str, version: str) -> PlaybookSnapshot:
    return PlaybookSnapshot(
        snapshot_id=f"{KB_ID}:medicare_fraud:{playbook_id}:{version}",
        knowledge_base_id=KB_ID,
        domain_name="medicare_fraud",
        playbook_id=playbook_id,
        version=version,
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


def _workflow_definition(definition_id: str, version: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        definition_id=definition_id,
        knowledge_base_id=KB_ID,
        domain_name="medicare_fraud",
        name="Provider review",
        version=version,
        status="approved",
        allowed_capability_refs=["rag.query"],
        steps=[
            WorkflowStepDefinition(
                step_id="ask-rag",
                label="Ask RAG",
                capability_ref="rag.query",
            )
        ],
        created_by="analyst-1",
        approved_by="supervisor-1",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        approved_at=BASE_TIME,
    )


def _governance_eval_run(
    *,
    artifact_id: str = "risk-scorer",
    created_at: datetime = BASE_TIME,
) -> GovernanceEvalRun:
    return GovernanceEvalRun(
        run_id=f"kb-governance:model:{artifact_id}:candidate-v2:tn-demo-1pct",
        knowledge_base_id=KB_ID,
        artifact_kind="model",
        artifact_id=artifact_id,
        artifact_version="candidate-v2",
        baseline_version="prod-v1",
        dataset_id="tn-demo-1pct",
        status="candidate",
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
        created_by="model-owner-1",
        created_at=created_at,
    )


def _approved_governance_eval_run(
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
