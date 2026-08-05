"""In-process capability registry and default SAFE-CMS-015 manifest catalog."""

from __future__ import annotations

from collections.abc import Iterable

from capabilities.models import (
    CapabilityDomainCompatibility,
    CapabilityExample,
    CapabilityHealth,
    CapabilityManifest,
    CapabilityPermission,
    JsonValue,
)


class CapabilityRegistry:
    """Simple typed registry for capability manifests."""

    def __init__(self, manifests: Iterable[CapabilityManifest] = ()) -> None:
        self._manifests: dict[str, CapabilityManifest] = {}
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: CapabilityManifest) -> None:
        if manifest.capability_id in self._manifests:
            raise ValueError(f"Duplicate capability id '{manifest.capability_id}'.")
        self._manifests[manifest.capability_id] = manifest

    def get(self, capability_id: str) -> CapabilityManifest | None:
        return self._manifests.get(capability_id)

    def list(self) -> list[CapabilityManifest]:
        return list(self._manifests.values())


def create_default_capability_registry() -> CapabilityRegistry:
    """Create the default SAFE-CMS-015 static capability catalog."""

    return CapabilityRegistry(_default_manifests())


def _object_schema(properties: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"type": "object", "properties": properties}


def _compat(*domains: str) -> CapabilityDomainCompatibility:
    return CapabilityDomainCompatibility(
        supported_domains=list(domains),
        environment_tags=["dev", "test", "production"],
    )


def _example(
    name: str,
    *,
    input: dict[str, JsonValue],
    output: dict[str, JsonValue],
) -> CapabilityExample:
    return CapabilityExample(name=name, input=input, output=output)


def _default_manifests() -> tuple[CapabilityManifest, ...]:
    return (
        CapabilityManifest(
            capability_id="analytics.peer_context",
            version="v1",
            module="analytics.peerstats",
            label="Peer context",
            description="Return peer cohort context for an entity and metric.",
            input_schema=_object_schema(
                {
                    "knowledge_base_id": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "metric_name": {"type": "string"},
                }
            ),
            output_schema=_object_schema(
                {
                    "entity_id": {"type": "string"},
                    "metric_name": {"type": "string"},
                    "peer_count": {"type": "integer"},
                    "z_score": {"type": "number"},
                }
            ),
            side_effect_class="read",
            permission=CapabilityPermission(required_roles=["viewer"]),
            domain_compatibility=_compat("medicare_fraud"),
            health=CapabilityHealth(status="healthy"),
            examples=[
                _example(
                    "Provider peer comparison",
                    input={
                        "knowledge_base_id": "kb-cms",
                        "entity_id": "npi-1558360921",
                        "metric_name": "billing_amount",
                    },
                    output={
                        "entity_id": "npi-1558360921",
                        "metric_name": "billing_amount",
                        "peer_count": 25,
                        "z_score": 2.7,
                    },
                )
            ],
        ),
        CapabilityManifest(
            capability_id="connector.sync.status",
            version="v1",
            module="connectors.status",
            label="Connector sync status",
            description="Return the last-known synchronization status for configured connectors.",
            input_schema=_object_schema(
                {
                    "knowledge_base_id": {"type": "string"},
                    "connector_id": {"type": "string"},
                }
            ),
            output_schema=_object_schema(
                {
                    "connector_id": {"type": "string"},
                    "status": {"type": "string"},
                    "last_synced_at": {"type": "string"},
                }
            ),
            side_effect_class="read",
            permission=CapabilityPermission(required_roles=["viewer"]),
            domain_compatibility=_compat("medicare_fraud", "af_housing", "food_supply_chain"),
            health=CapabilityHealth(status="healthy"),
            examples=[
                _example(
                    "CMS source status",
                    input={"knowledge_base_id": "kb-cms", "connector_id": "cms-claims"},
                    output={
                        "connector_id": "cms-claims",
                        "status": "healthy",
                        "last_synced_at": "2026-08-05T12:00:00Z",
                    },
                )
            ],
        ),
        CapabilityManifest(
            capability_id="evidence.checklist.generate",
            version="v1",
            module="evidence.packs",
            label="Evidence checklist generation",
            description="Generate a review checklist for a suspicious entity or alert.",
            input_schema=_object_schema(
                {
                    "knowledge_base_id": {"type": "string"},
                    "target_type": {"type": "string"},
                    "target_id": {"type": "string"},
                }
            ),
            output_schema=_object_schema(
                {
                    "checklist_id": {"type": "string"},
                    "item_count": {"type": "integer"},
                }
            ),
            side_effect_class="write",
            permission=CapabilityPermission(
                required_roles=["analyst"],
                requires_audit=True,
            ),
            domain_compatibility=_compat("medicare_fraud"),
            health=CapabilityHealth(status="healthy"),
            examples=[
                _example(
                    "Alert evidence checklist",
                    input={
                        "knowledge_base_id": "kb-cms",
                        "target_type": "alert",
                        "target_id": "alert-123",
                    },
                    output={"checklist_id": "checklist-123", "item_count": 7},
                )
            ],
        ),
        CapabilityManifest(
            capability_id="rag.query",
            version="v1",
            module="rag",
            label="Scoped RAG query",
            description="Query knowledge base context with explicit scope and citations.",
            input_schema=_object_schema(
                {
                    "knowledge_base_id": {"type": "string"},
                    "query": {"type": "string"},
                    "scope": {"type": "object"},
                }
            ),
            output_schema=_object_schema(
                {
                    "answer": {"type": "string"},
                    "citation_refs": {"type": "array"},
                }
            ),
            side_effect_class="read",
            permission=CapabilityPermission(required_roles=["viewer"]),
            domain_compatibility=_compat("medicare_fraud", "af_housing", "food_supply_chain"),
            health=CapabilityHealth(status="healthy"),
            examples=[
                _example(
                    "Alert context query",
                    input={
                        "knowledge_base_id": "kb-cms",
                        "query": "Why is this provider unusual?",
                        "scope": {"alert_id": "alert-123"},
                    },
                    output={"answer": "Peer billing is elevated.", "citation_refs": ["doc-1:3"]},
                )
            ],
        ),
        CapabilityManifest(
            capability_id="case.note.draft",
            version="v1",
            module="cases",
            label="Case note draft",
            description="Draft a case note for analyst review before persistence.",
            input_schema=_object_schema(
                {
                    "knowledge_base_id": {"type": "string"},
                    "case_id": {"type": "string"},
                    "summary": {"type": "string"},
                }
            ),
            output_schema=_object_schema(
                {
                    "draft_note": {"type": "string"},
                    "requires_human_approval": {"type": "boolean"},
                }
            ),
            side_effect_class="approval",
            permission=CapabilityPermission(
                required_roles=["analyst"],
                requires_audit=True,
            ),
            domain_compatibility=_compat("medicare_fraud", "af_housing", "food_supply_chain"),
            health=CapabilityHealth(status="healthy"),
            examples=[
                _example(
                    "Provider case note",
                    input={
                        "knowledge_base_id": "kb-cms",
                        "case_id": "case-123",
                        "summary": "Provider billing exceeds peer norms.",
                    },
                    output={
                        "draft_note": "Review provider billing outliers and supporting claims.",
                        "requires_human_approval": True,
                    },
                )
            ],
        ),
    )


__all__ = ["CapabilityRegistry", "create_default_capability_registry"]
