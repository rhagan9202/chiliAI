"""Tests for the dev/e2e-only seed endpoint.

The endpoint derives its demo scenario from the ACTIVE ``DomainConfig`` (E8):

* under the default medicare pack it must keep the exact display shapes the
  Playwright e2e suite asserts on (entity ids, alert/case/policy titles);
* under any other pack (food supply chain here) it must seed data typed and
  validated against that pack — never medicare type names;
* packs without relationships or entity-target policy rules degrade cleanly.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.routers import dev_seed as dev_seed_module
from api.routers.dev_seed import (
    build_demo_entity,
    generate_property_value,
    pattern_example,
    resolve_matched_value,
    select_demo_shape,
)
from config.loader import load_config
from config.schema import (
    AlertsConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    PolicyPredicate,
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
)
from shared.types import (
    Entity,
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
    Relationship,
    RelationshipDefinition,
    validate_entity,
    validate_relationship,
)

_DEFAULTS_DIR = Path(__file__).resolve().parents[2] / "config" / "defaults"
_MEDICARE_CONFIG_PATH = _DEFAULTS_DIR / "medicare_fraud.yaml"
_FOOD_CONFIG_PATH = _DEFAULTS_DIR / "food_supply_chain.yaml"

_MEDICARE_TYPE_NAMES = {"provider", "claim", "beneficiary"}
_MEDICARE_RELATIONSHIP_NAMES = {"submitted_by", "billed_for", "performed_at", "referred_by"}


def _get_client() -> TestClient:
    return TestClient(create_app())


def _seeded_subgraph(
    client: TestClient, entity_id: str, kb_id: str
) -> tuple[list[Entity], list[Relationship]]:
    """Read the seeded neighborhood back and rehydrate shared platform types."""
    neighborhood = client.get(
        f"/investigation/entities/{entity_id}/neighborhood",
        params={"knowledge_base_id": kb_id, "depth": 2},
    )
    assert neighborhood.status_code == 200
    payload = neighborhood.json()
    entities = [Entity.model_validate(item) for item in payload["entities"]]
    relationships = [
        Relationship.model_validate(item) for item in payload["relationships"]
    ]
    return entities, relationships


# ---------------------------------------------------------------------------
# Default (medicare) pack — existing behavior preserved
# ---------------------------------------------------------------------------


def test_dev_seed_writes_real_alert_evidence_case_and_kb() -> None:
    client = _get_client()

    resp = client.post("/admin/dev-seed")
    assert resp.status_code == 200
    ids = resp.json()
    kb = ids["knowledge_base_id"]
    assert kb and ids["alert_id"] and ids["evidence_pack_id"] and ids["case_id"]

    # The alert is in the real projection feed, KB-scoped.
    alerts = client.get("/alerts").json()["items"]
    seeded = next((a for a in alerts if a["id"] == ids["alert_id"]), None)
    assert seeded is not None
    assert seeded["knowledge_base_id"] == kb
    assert seeded["evidence_pack_id"] == ids["evidence_pack_id"]

    # The evidence pack is served from the real repository.
    ev = client.get(
        f"/evidence-packs/{ids['evidence_pack_id']}", params={"knowledge_base_id": kb}
    )
    assert ev.status_code == 200
    assert ev.json()["subgraph_node_ids"]

    # The case is served from the real repository (KB-scoped). It is independent
    # of the seeded alert so that alert stays promotable in the promote spec.
    case = client.get(f"/cases/{ids['case_id']}", params={"knowledge_base_id": kb})
    assert case.status_code == 200
    assert case.json()["case"]["knowledge_base_id"] == kb
    assert case.json()["case"]["alert_ids"] == []

    # The KB is listed.
    kbs = client.get("/knowledgebases").json()["items"]
    assert any(k["id"] == kb for k in kbs)

    # The seeded entity + its neighborhood are in the REAL graph (the endpoints
    # the workbench / EvidencePackViewer actually query).
    detail = client.get(f"/investigation/entities/{ids['entity_id']}", params={"knowledge_base_id": kb})
    assert detail.status_code == 200
    assert detail.json()["entity"]["id"] == ids["entity_id"]

    neighborhood = client.get(
        f"/investigation/entities/{ids['entity_id']}/neighborhood",
        params={"knowledge_base_id": kb, "depth": 2},
    )
    assert neighborhood.status_code == 200
    node_ids = {e["id"] for e in neighborhood.json()["entities"]}
    assert {"provider-1", "claim-1", "beneficiary-1"} <= node_ids


def test_dev_seed_serves_entity_via_graph_read_model() -> None:
    # BL-012: /graph/entities/{id} now reads the durable graph the seeder wrote.
    client = _get_client()

    ids = client.post("/admin/dev-seed").json()

    detail = client.get(f"/graph/entities/{ids['entity_id']}")
    assert detail.status_code == 200
    assert detail.json()["entity"]["id"] == ids["entity_id"]


def test_dev_seed_creates_a_conversation() -> None:
    # BL-012: the seeder writes one durable chat conversation for the KB.
    client = _get_client()

    body = client.post("/admin/dev-seed").json()
    conversation_id = body["conversation_id"]
    assert conversation_id

    conversation = client.get(f"/chat/conversations/{conversation_id}")
    assert conversation.status_code == 200
    payload = conversation.json()
    assert payload["knowledge_base_id"] == body["knowledge_base_id"]
    assert len(payload["messages"]) == 2
    assert payload["messages"][-1]["role"] == "assistant"


def test_dev_seed_creates_a_policy_item() -> None:
    client = _get_client()

    res = client.post("/admin/dev-seed")
    assert res.status_code == 200
    body = res.json()
    assert body["policy_item_id"]
    kb = body["knowledge_base_id"]
    got = client.get(f"/policy/items/{body['policy_item_id']}?knowledge_base_id={kb}")
    assert got.status_code == 200
    assert got.json()["item"]["status"] == "open"


# ---------------------------------------------------------------------------
# Medicare pack — the e2e-locked display shapes must stay exactly as the
# Playwright suite asserts them (chili_app/e2e/*.spec.ts).
# ---------------------------------------------------------------------------


def test_dev_seed_medicare_keeps_e2e_locked_display_shapes() -> None:
    client = _get_client()

    ids = client.post("/admin/dev-seed").json()
    kb = ids["knowledge_base_id"]
    assert ids["entity_id"] == "provider-1"

    alert = next(
        a for a in client.get("/alerts").json()["items"] if a["id"] == ids["alert_id"]
    )
    assert alert["entity_label"] == "Redwood DME Group"
    assert alert["title"] == "Outlier billing concentration"
    assert alert["entity_type"] == "provider"
    assert alert["entity_id"] == "provider-1"
    assert alert["severity"] == "critical"

    case = client.get(f"/cases/{ids['case_id']}", params={"knowledge_base_id": kb})
    assert case.json()["case"]["title"] == "Redwood DME escalation"

    policy = client.get(
        f"/policy/items/{ids['policy_item_id']}", params={"knowledge_base_id": kb}
    ).json()
    assert policy["item"]["title"] == "Claim claim-1 exceeds the billing threshold"
    assert policy["item"]["rule_id"] == "claim_over_billed"
    assert policy["item"]["rule_pack_id"] == "billing_thresholds"
    assert policy["item"]["target_ref"] == "claim-1"

    ev = client.get(
        f"/evidence-packs/{ids['evidence_pack_id']}", params={"knowledge_base_id": kb}
    ).json()
    assert ev["reasoning"] == (
        "Provider billing concentration and upcoding indicate elevated fraud risk."
    )
    assert ev["confidence"] == pytest.approx(0.82)


def test_dev_seed_medicare_output_validates_under_active_config() -> None:
    client = _get_client()
    config = load_config(_MEDICARE_CONFIG_PATH)

    ids = client.post("/admin/dev-seed").json()
    entities, relationships = _seeded_subgraph(
        client, ids["entity_id"], ids["knowledge_base_id"]
    )
    assert entities and relationships

    errors: list[str] = []
    for entity in entities:
        errors.extend(validate_entity(entity, config.entities))
    entities_by_id = {entity.id: entity for entity in entities}
    for relationship in relationships:
        errors.extend(
            validate_relationship(relationship, config.relationships, entities_by_id)
        )
    assert errors == []


# ---------------------------------------------------------------------------
# Food pack — food-typed valid data, zero medicare names
# ---------------------------------------------------------------------------


def test_dev_seed_under_food_pack_seeds_food_typed_valid_data() -> None:
    # The app runs with in-memory dev infra (medicare env defaults); the route
    # itself derives everything from the injected food pack, read fresh so the
    # assertions track the pack as it is finalized.
    food_config = load_config(_FOOD_CONFIG_PATH)
    app = create_app()
    app.dependency_overrides[dev_seed_module.get_domain_config] = lambda: food_config
    client = TestClient(app)

    res = client.post("/admin/dev-seed")
    assert res.status_code == 200
    ids = res.json()
    kb = ids["knowledge_base_id"]

    food_entity_names = {definition.name for definition in food_config.entities}
    food_relationship_names = {
        definition.name for definition in food_config.relationships
    }

    entities, relationships = _seeded_subgraph(client, ids["entity_id"], kb)
    assert entities and relationships

    seeded_entity_types = {entity.type for entity in entities}
    seeded_relationship_types = {relationship.type for relationship in relationships}
    assert seeded_entity_types <= food_entity_names
    assert seeded_relationship_types <= food_relationship_names
    # Never medicare type names under a non-medicare pack.
    assert seeded_entity_types.isdisjoint(_MEDICARE_TYPE_NAMES)
    assert seeded_relationship_types.isdisjoint(_MEDICARE_RELATIONSHIP_NAMES)

    # Everything seeded validates against the FOOD definitions.
    errors: list[str] = []
    for entity in entities:
        errors.extend(validate_entity(entity, food_config.entities))
    entities_by_id = {entity.id: entity for entity in entities}
    for relationship in relationships:
        errors.extend(
            validate_relationship(
                relationship, food_config.relationships, entities_by_id
            )
        )
    assert errors == []

    # The alert anchors on a food-typed entity.
    alert = next(
        a for a in client.get("/alerts").json()["items"] if a["id"] == ids["alert_id"]
    )
    assert alert["entity_type"] in food_entity_names
    assert alert["entity_label"]
    assert "Redwood" not in alert["entity_label"]

    # The policy item comes from the food pack's own rules and its target is a
    # real, food-typed graph entity.
    assert ids["policy_item_id"]
    policy = client.get(
        f"/policy/items/{ids['policy_item_id']}", params={"knowledge_base_id": kb}
    ).json()
    food_rule_ids = {
        rule.id for pack in food_config.policy_rules for rule in pack.rules
    }
    food_pack_ids = {pack.id for pack in food_config.policy_rules}
    assert policy["item"]["rule_id"] in food_rule_ids
    assert policy["item"]["rule_pack_id"] in food_pack_ids
    target = client.get(f"/graph/entities/{policy['item']['target_ref']}")
    assert target.status_code == 200
    assert target.json()["entity"]["type"] in food_entity_names

    # The case exists and carries no medicare display strings.
    case = client.get(f"/cases/{ids['case_id']}", params={"knowledge_base_id": kb})
    assert case.status_code == 200
    assert "Redwood" not in case.json()["case"]["title"]


def test_dev_seed_response_shape_is_stable_across_packs() -> None:
    """The wire contract (key set + value types) is identical for every pack."""
    expected_keys = {
        "knowledge_base_id",
        "entity_id",
        "alert_id",
        "evidence_pack_id",
        "case_id",
        "policy_item_id",
        "conversation_id",
    }

    medicare_client = _get_client()
    medicare_body = medicare_client.post("/admin/dev-seed").json()

    food_config = load_config(_FOOD_CONFIG_PATH)
    food_app = create_app()
    food_app.dependency_overrides[dev_seed_module.get_domain_config] = (
        lambda: food_config
    )
    food_body = TestClient(food_app).post("/admin/dev-seed").json()

    for body in (medicare_body, food_body):
        assert set(body.keys()) == expected_keys
        assert all(isinstance(value, str) for value in body.values())


# ---------------------------------------------------------------------------
# Degenerate packs — clean gating instead of wrong-domain data
# ---------------------------------------------------------------------------


def _minimal_config(
    entities: list[EntityDefinition],
    policy_rules: list[PolicyRulePack] | None = None,
    relationships: list[RelationshipDefinition] | None = None,
) -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="widgets", display_name="Widgets", description="Test"),
        entities=entities,
        relationships=relationships or [],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        alerts=AlertsConfig(thresholds={}),
        policy_rules=policy_rules or [],
    )


def _widget_definition() -> EntityDefinition:
    return EntityDefinition(
        name="widget",
        display_label="Widget",
        icon="box",
        properties={
            "widget_id": PropertyDefinition(
                type=PropertyType.STRING, display="Widget ID", required=True
            )
        },
        natural_key=["widget_id"],
    )


def _client_with_config(config: DomainConfig) -> TestClient:
    app = create_app()
    app.dependency_overrides[dev_seed_module.get_domain_config] = lambda: config
    return TestClient(app)


def test_dev_seed_without_relationships_or_rules_seeds_lone_entity() -> None:
    client = _client_with_config(_minimal_config([_widget_definition()]))

    res = client.post("/admin/dev-seed")
    assert res.status_code == 200
    ids = res.json()
    # A relationship-less pack seeds a single hub entity and skips the policy
    # item (the pack declares no entity-target rules) with a "" sentinel.
    assert ids["entity_id"] == "widget-1"
    assert ids["policy_item_id"] == ""

    alert = next(
        a for a in client.get("/alerts").json()["items"] if a["id"] == ids["alert_id"]
    )
    assert alert["entity_type"] == "widget"
    assert alert["knowledge_base_id"] == ids["knowledge_base_id"]


def test_dev_seed_policy_rule_without_entity_selector_targets_the_hub() -> None:
    pack = PolicyRulePack(
        id="widget_rules",
        name="Widget rules",
        rules=[
            PolicyRule(
                id="widget_watch",
                title_template="Widget {target_ref} is on the watch list",
                severity="medium",
                target_kind="entity",
                predicate=PolicyPredicate(
                    field="properties.widget_id",
                    op="in",
                    value=PolicyPredicateValue(literal=["widget-1", "widget-9"]),
                ),
            )
        ],
    )
    client = _client_with_config(_minimal_config([_widget_definition()], [pack]))

    ids = client.post("/admin/dev-seed").json()
    assert ids["policy_item_id"]
    policy = client.get(
        f"/policy/items/{ids['policy_item_id']}",
        params={"knowledge_base_id": ids["knowledge_base_id"]},
    ).json()
    assert policy["item"]["target_ref"] == "widget-1"
    assert policy["item"]["title"] == "Widget widget-1 is on the watch list"
    assert policy["matched_fields"] == {"properties.widget_id": "widget-1"}


def test_dev_seed_unsatisfiable_pattern_answers_422_and_writes_nothing() -> None:
    # A required pattern outside the supported synthesis subset cannot yield a
    # valid demo value: the endpoint must refuse rather than persist invalid
    # data for the active domain.
    definition = EntityDefinition(
        name="widget",
        display_label="Widget",
        icon="box",
        properties={
            "widget_id": PropertyDefinition(
                type=PropertyType.STRING,
                display="Widget ID",
                required=True,
                pattern="(alpha|beta)",
            )
        },
    )
    client = _client_with_config(_minimal_config([definition]))

    res = client.post("/admin/dev-seed")
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert "nothing was written" in detail["message"]
    assert detail["errors"]

    kbs = client.get("/knowledgebases").json()["items"]
    assert not any(k["name"] == "E2E Seed KB" for k in kbs)


def test_dev_seed_with_no_entity_types_gates_cleanly() -> None:
    client = _client_with_config(_minimal_config([]))

    res = client.post("/admin/dev-seed")
    assert res.status_code == 422
    assert "nothing to seed" in res.json()["detail"]

    # Nothing was written.
    kbs = client.get("/knowledgebases").json()["items"]
    assert not any(k["name"] == "E2E Seed KB" for k in kbs)


# ---------------------------------------------------------------------------
# Config-driven generators (public helpers)
# ---------------------------------------------------------------------------


def test_select_demo_shape_prefers_the_multi_relationship_hub() -> None:
    medicare = load_config(_MEDICARE_CONFIG_PATH)
    shape = select_demo_shape(medicare)
    assert shape.hub.name == "claim"
    assert [rel.name for rel, _ in shape.spokes] == ["submitted_by", "billed_for"]
    assert [target.name for _, target in shape.spokes] == ["provider", "beneficiary"]

    # Structural invariants for the food pack (read fresh; the pack is being
    # finalized in parallel — assert shape, not hardcoded food entity names).
    food = load_config(_FOOD_CONFIG_PATH)
    food_shape = select_demo_shape(food)
    outgoing = [
        rel for rel in food.relationships if rel.source == food_shape.hub.name
    ]
    assert len(outgoing) >= 2
    assert len(food_shape.spokes) == 2
    for relationship, target in food_shape.spokes:
        assert relationship.source == food_shape.hub.name
        assert relationship.target == target.name


def test_select_demo_shape_falls_back_to_the_single_relationship() -> None:
    # No source appears in two relationships: the first declared relationship
    # becomes the (single-spoke) demo shape.
    gadget = EntityDefinition(
        name="gadget",
        display_label="Gadget",
        icon="cpu",
        properties={
            "gadget_id": PropertyDefinition(
                type=PropertyType.STRING, display="Gadget ID", required=True
            )
        },
    )
    config = _minimal_config(
        [_widget_definition(), gadget],
        relationships=[
            RelationshipDefinition(
                name="paired_with",
                display_label="Paired with",
                source="widget",
                target="gadget",
            )
        ],
    )
    shape = select_demo_shape(config)
    assert shape.hub.name == "widget"
    assert [(rel.name, target.name) for rel, target in shape.spokes] == [
        ("paired_with", "gadget")
    ]


def test_build_demo_entity_is_valid_for_every_declared_type() -> None:
    for config_path in (_MEDICARE_CONFIG_PATH, _FOOD_CONFIG_PATH):
        config = load_config(config_path)
        for definition in config.entities:
            first = build_demo_entity(definition, 1)
            second = build_demo_entity(definition, 2)
            assert validate_entity(first, config.entities) == []
            assert validate_entity(second, config.entities) == []
            assert first.id != second.id
            # String-typed natural keys stay unique across instances.
            for key in definition.natural_key:
                if definition.properties[key].type is PropertyType.STRING:
                    assert first.properties[key] != second.properties[key]


def test_pattern_example_covers_the_supported_construct_subset() -> None:
    assert pattern_example("^[0-9]{10}$", 7) == "0000000007"
    assert pattern_example(r"^\d{3}-[A-Z]{2}$", 42) == "042-AA"
    assert pattern_example(r"^[A-Z]\d+$", 5) == "A5"
    assert pattern_example(r"^npi\.[0-9]*$", 3) == "npi."
    assert pattern_example("^literal$", 1) == "literal"
    # Escapes inside character classes, digit ranges, and mixed classes.
    assert pattern_example(r"^[\d]{2}$", 3) == "03"
    assert pattern_example(r"^[\-]X$", 1) == "-X"
    assert pattern_example("^[a-c]{2}$", 1) == "aa"
    # A digit-only class is a digit slot: it round-trips only when the index
    # happens to satisfy the class, otherwise the fullmatch check rejects it.
    assert pattern_example("^x[5]$", 5) == "x5"
    assert pattern_example("^x[5]$", 1) is None
    # Wildcard, \w, \s, optional / lazy quantifiers, {n,m} ranges.
    assert pattern_example(r"^.\w\sZ$", 1) == "aa Z"
    assert pattern_example(r"^a{2,4}b?$", 1) == "aa"
    assert pattern_example(r"^\d+?$", 8) == "8"


def test_pattern_example_returns_none_for_unsupported_constructs() -> None:
    assert pattern_example("^(ab|cd)$", 1) is None
    assert pattern_example("^[^0-9]{3}$", 1) is None
    assert pattern_example(r"^\D+$", 1) is None
    assert pattern_example("^[0-9$", 1) is None  # unterminated class


def test_generate_property_value_conforms_to_each_definition_type() -> None:
    enum_value = generate_property_value(
        "grade",
        PropertyDefinition(type=PropertyType.ENUM, display="Grade", enum_values=["A", "B"]),
        1,
    )
    assert enum_value == "A"

    assert generate_property_value(
        "flag", PropertyDefinition(type=PropertyType.BOOLEAN, display="Flag"), 1
    ) is True

    assert generate_property_value(
        "count",
        PropertyDefinition(type=PropertyType.INTEGER, display="Count", min_value=5),
        1,
    ) == 5
    assert generate_property_value(
        "count",
        PropertyDefinition(type=PropertyType.INTEGER, display="Count", max_value=0),
        1,
    ) == 0

    assert generate_property_value(
        "amount",
        PropertyDefinition(type=PropertyType.DECIMAL, display="Amount", min_value=2.5),
        1,
    ) == 2.5
    assert generate_property_value(
        "amount",
        PropertyDefinition(type=PropertyType.DECIMAL, display="Amount", max_value=0.5),
        1,
    ) == 0.5

    date_value = generate_property_value(
        "when", PropertyDefinition(type=PropertyType.DATE, display="When"), 1
    )
    assert isinstance(date_value, str)
    assert date.fromisoformat(date_value)

    list_value = generate_property_value(
        "codes",
        PropertyDefinition(type=PropertyType.LIST, display="Codes", min_length=2),
        1,
    )
    assert isinstance(list_value, list)
    assert len(list_value) == 2

    assert generate_property_value(
        "meta", PropertyDefinition(type=PropertyType.NESTED, display="Meta"), 1
    ) == {}

    padded = generate_property_value(
        "id",
        PropertyDefinition(type=PropertyType.STRING, display="Id", min_length=12),
        1,
    )
    assert isinstance(padded, str) and len(padded) >= 12
    truncated = generate_property_value(
        "id",
        PropertyDefinition(type=PropertyType.STRING, display="Id", max_length=3),
        1,
    )
    assert isinstance(truncated, str) and len(truncated) <= 3

    # Unsupported pattern falls back to the plain deterministic string; the
    # endpoint's validate-before-write guardrail reports the gap loudly.
    fallback = generate_property_value(
        "code",
        PropertyDefinition(type=PropertyType.STRING, display="Code", pattern="(a|b)"),
        1,
    )
    assert fallback == "code-1"


def _rule(op: str, value: PolicyPredicateValue) -> tuple[PolicyRulePack, PolicyRule]:
    rule = PolicyRule(
        id="r1",
        title_template="{target_ref}",
        severity="high",
        target_kind="entity",
        predicate=PolicyPredicate.model_validate(
            {"field": "properties.amount", "op": op, "value": value}
        ),
    )
    pack = PolicyRulePack(
        id="p1", name="Pack", thresholds={"ceiling": 5000}, rules=[rule]
    )
    return pack, rule


def test_resolve_matched_value_crosses_strict_numeric_bounds() -> None:
    pack, rule = _rule("gt", PolicyPredicateValue(config_ref="ceiling"))
    assert resolve_matched_value(pack, rule) == 5001

    pack, rule = _rule("lt", PolicyPredicateValue(literal=10))
    assert resolve_matched_value(pack, rule) == 9

    pack, rule = _rule("eq", PolicyPredicateValue(literal=True))
    assert resolve_matched_value(pack, rule) is True

    pack, rule = _rule("in", PolicyPredicateValue(literal=["x", "y"]))
    assert resolve_matched_value(pack, rule) == "x"

    # Non-strict numeric ops satisfy the predicate with the value itself.
    pack, rule = _rule("gte", PolicyPredicateValue(config_ref="ceiling"))
    assert resolve_matched_value(pack, rule) == 5000
