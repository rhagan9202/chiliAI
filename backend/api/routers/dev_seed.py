"""Dev/e2e-only seed endpoint.

Writes a deterministic, fully-formed investigation scenario (knowledge base +
graph subgraph + alert projection + evidence pack + case) directly into the
*real* repositories so full-stack e2e tests can assert the UI against real data
served by the real API.

The alert/evidence pipeline (Flow B) is LLM-dependent and cannot deterministically
produce alerts in a dev stack, so this endpoint inserts the alert and evidence
into the same real stores the worker would write to — no component, endpoint, or
integration is mocked; only the (non-deterministic) generation step is bypassed.

This router is registered ONLY when ``CHILI_ENV != production`` (see
``api/app.py``), so the endpoint does not exist in production.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from analytics.explainability.repository import EvidencePackRepository
from api._alert_store import AlertProjectionRecord, AlertProjectionRepository
from api.dependencies import (
    get_alert_repository,
    get_case_repository,
    get_evidence_pack_repository,
    get_graph_repository,
    get_knowledge_base_repository,
    get_policy_repository,
)
from api.middleware.rbac import require_role
from policy.adapters.protocols import PolicyItemRepository
from policy.service import create_policy_service
from cases.adapters.protocols import CaseRepository
from cases.models import Case
from graph.adapters.protocols import GraphRepository
from knowledgebases import KnowledgeBaseRepository
from shared.types import Alert, Entity, EvidencePack, KnowledgeBase, Relationship
from shared.utils import generate_id, utc_now

__all__ = ["router"]

router = APIRouter(prefix="/admin/dev-seed", tags=["dev"])


class DevSeedResponse(BaseModel):
    """Identifiers of the deterministic scenario seeded into the real stores."""

    knowledge_base_id: str
    entity_id: str
    alert_id: str
    evidence_pack_id: str
    case_id: str
    policy_item_id: str


@router.post(
    "",
    response_model=DevSeedResponse,
    dependencies=[Depends(require_role("analyst"))],
)
async def dev_seed(
    request: Request,
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_repository: GraphRepository = Depends(get_graph_repository),
    alert_repository: AlertProjectionRepository = Depends(get_alert_repository),
    evidence_repository: EvidencePackRepository = Depends(get_evidence_pack_repository),
    case_repository: CaseRepository = Depends(get_case_repository),
    policy_repository: PolicyItemRepository = Depends(get_policy_repository),
) -> DevSeedResponse:
    """Seed a deterministic KB + subgraph + alert + evidence + case (dev/e2e only)."""
    now = utc_now()
    kb_id = generate_id()

    # --- knowledge base ---------------------------------------------------
    kb_repository.create(
        KnowledgeBase(
            id=kb_id,
            name="E2E Seed KB",
            description="Deterministic scenario for full-stack e2e.",
            entity_count=3,
            relationship_count=2,
            status="ready",
            created_at=now,
        )
    )

    # --- graph subgraph (provider <- claim -> beneficiary) ----------------
    provider_id, claim_id, beneficiary_id = "provider-1", "claim-1", "beneficiary-1"
    entities = [
        Entity(id=provider_id, type="provider", properties={"display_name": "Redwood DME Group"}),
        Entity(id=claim_id, type="claim", properties={"display_name": "Claim CLM-001"}),
        Entity(id=beneficiary_id, type="beneficiary", properties={"display_name": "Beneficiary B-77"}),
    ]
    relationships = [
        Relationship(id="rel-submitted", type="submitted_by", source_id=claim_id, target_id=provider_id),
        Relationship(id="rel-billed", type="billed_for", source_id=claim_id, target_id=beneficiary_id),
    ]
    graph_repository.upsert_entities(kb_id, entities)
    graph_repository.upsert_relationships(kb_id, relationships)

    # --- evidence pack ----------------------------------------------------
    evidence_pack_id = generate_id()
    alert_id = generate_id()
    evidence_repository.put(
        kb_id,
        EvidencePack(
            id=evidence_pack_id,
            alert_id=alert_id,
            reasoning="Provider billing concentration and upcoding indicate elevated fraud risk.",
            subgraph_nodes=[provider_id, claim_id, beneficiary_id],
            subgraph_edges=["rel-submitted", "rel-billed"],
            confidence=0.82,
            scores={"overall": 0.82, "peer_deviation": 0.94},
        ),
    )

    # --- alert projection -------------------------------------------------
    alert_repository.upsert(
        AlertProjectionRecord(
            knowledge_base_id=kb_id,
            alert=Alert(
                id=alert_id,
                entity_type="provider",
                entity_id=provider_id,
                severity="critical",
                title="Outlier billing concentration",
                reasoning="Provider activity is materially above peers.",
                evidence_pack_id=evidence_pack_id,
                created_at=now,
            ),
            entity_label="Redwood DME Group",
            confidence=0.96,
            tags=["billing", "peer-deviation"],
            related_entity_ids=[provider_id, claim_id],
        )
    )

    # --- case (independent of the alert so the alert stays promotable) ----
    case_id = generate_id()
    case_repository.create(
        Case(
            id=case_id,
            knowledge_base_id=kb_id,
            title="Redwood DME escalation",
            status="open",
            priority="high",
            assignee="analyst@example.com",
            alert_ids=[],
        )
    )

    # --- policy item (open, targeting the seeded claim entity) --------------
    policy_service = create_policy_service(policy_repository)
    policy_item = policy_service.record_match(
        knowledge_base_id=kb_id,
        rule_id="claim_over_billed",
        rule_pack_id="billing_thresholds",
        target_kind="entity",
        target_ref=claim_id,
        title=f"Claim {claim_id} exceeds the billing threshold",
        severity="high",
        matched_fields={"properties.amount": 1500.0},
        citations=[],
    )

    return DevSeedResponse(
        knowledge_base_id=kb_id,
        entity_id=provider_id,
        alert_id=alert_id,
        evidence_pack_id=evidence_pack_id,
        case_id=case_id,
        policy_item_id=policy_item.id,
    )
