"""Unit tests for ``tools.demo_trigger_analytics``: builders + selection logic.

No redis and no docker: the API call is faked with ``httpx.MockTransport``,
and object-store selection is exercised against real committed domain pack
YAML (``config/defaults/*.yaml``) rather than a hand-built ``DomainConfig``,
so the test stays honest about the real config shape. The artifact builders
are round-tripped through the *real* ``GraphUpsertResult``/``ValidationReport``
Pydantic models (not re-parsed dicts) to pin BL-017 integrity-guard
compatibility: ``upserted_entity_ids`` must be a subset of the validation
report's entity ids.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from config.loader import load_config
from config.schema import DomainConfig, ObjectStoreConfig
from events.adapters.in_memory import InMemoryEventBus
from events.protocols import EventBus
from events.runtime import EventBusSettings
from events.types import GraphUpdatedEvent
from graph.models import GraphUpsertResult
from ingestion.models import ValidationReport
from storage.adapters.in_memory import InMemoryObjectStore
from storage.adapters.local_fs_adapter import LocalFsObjectStore
from storage.adapters.s3_adapter import S3ObjectStore
from storage.protocols import ObjectStore
from tools import demo_trigger_analytics as trigger

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "defaults"


def _now() -> datetime:
    return datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


class TestSelectTopRiskEntityIds:
    def test_returns_ranked_entity_ids_from_the_real_response_model(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/analytics/risk-scores"
            assert dict(request.url.params) == {
                "kb_id": "kb-1",
                "entity_type": "provider",
                "limit": "3",
            }
            return httpx.Response(
                200,
                json={
                    "knowledge_base_id": "kb-1",
                    "items": [
                        {
                            "entity_id": "provider:1",
                            "entity_type": "provider",
                            "overall_score": 0.9,
                            "risk_level": "critical",
                        },
                        {
                            "entity_id": "provider:2",
                            "entity_type": "provider",
                            "overall_score": 0.8,
                            "risk_level": "high",
                        },
                    ],
                    "total": 2,
                },
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://api:8000"
        )
        ids = trigger.select_top_risk_entity_ids(
            client, kb_id="kb-1", entity_type="provider", top=3
        )
        assert ids == ["provider:1", "provider:2"]

    def test_slices_to_top_when_the_api_returns_more(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "knowledge_base_id": "kb-1",
                    "items": [
                        {
                            "entity_id": f"provider:{i}",
                            "entity_type": "provider",
                            "overall_score": 1.0 - i * 0.1,
                            "risk_level": "high",
                        }
                        for i in range(5)
                    ],
                    "total": 5,
                },
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://api:8000"
        )
        ids = trigger.select_top_risk_entity_ids(
            client, kb_id="kb-1", entity_type="provider", top=2
        )
        assert ids == ["provider:0", "provider:1"]

    def test_empty_items_yields_empty_selection(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"knowledge_base_id": "kb-1", "items": [], "total": 0}
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://api:8000"
        )
        ids = trigger.select_top_risk_entity_ids(
            client, kb_id="kb-1", entity_type="provider", top=3
        )
        assert ids == []

    def test_raises_on_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "boom"})

        client = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://api:8000"
        )
        with pytest.raises(httpx.HTTPStatusError):
            trigger.select_top_risk_entity_ids(
                client, kb_id="kb-1", entity_type="provider", top=3
            )


class TestArtifactBuilders:
    def test_trigger_id_is_derived_from_the_given_timestamp(self) -> None:
        assert trigger.build_trigger_id(_now()) == "demo-trigger-20260723T120000Z"

    def test_artifact_storage_keys_avoid_the_real_pipeline_namespace(self) -> None:
        graph_key, validation_key = trigger.artifact_storage_keys(
            "kb-1", "demo-trigger-x"
        )
        assert graph_key == "graph-updates/kb-1/demo-trigger-x.json"
        assert validation_key == "validations/kb-1/demo-trigger-x.json"
        # Real pipeline artifacts live under knowledgebases/<kb>/... — no overlap.
        assert not graph_key.startswith("knowledgebases/")
        assert not validation_key.startswith("knowledgebases/")

    def test_graph_upsert_result_round_trips_through_the_real_pydantic_model(
        self,
    ) -> None:
        result = trigger.build_graph_upsert_result(
            knowledge_base_id="kb-1",
            trigger_id="demo-trigger-x",
            entity_ids=["provider:1", "provider:2"],
            now=_now(),
        )
        round_tripped = GraphUpsertResult.model_validate_json(result.model_dump_json())
        assert round_tripped.knowledge_base_id == "kb-1"
        assert round_tripped.upserted_entity_ids == ["provider:1", "provider:2"]
        assert round_tripped.upserted_relationship_ids == []
        assert round_tripped.validation_report_id == "demo-trigger-x"
        assert round_tripped.extraction_result_id == "demo-trigger-x"

    def test_validation_report_round_trips_and_covers_the_upserted_ids(self) -> None:
        entity_ids = ["provider:1", "provider:2"]
        report = trigger.build_validation_report(
            trigger_id="demo-trigger-x",
            entity_type="provider",
            entity_ids=entity_ids,
            now=_now(),
        )
        round_tripped = ValidationReport.model_validate_json(report.model_dump_json())
        assert {entity.id for entity in round_tripped.valid_entities} == set(entity_ids)
        assert all(entity.type == "provider" for entity in round_tripped.valid_entities)
        assert round_tripped.valid_relationships == []
        assert round_tripped.entity_errors == {}

    def test_upserted_ids_are_a_subset_of_validation_entities_bl017(self) -> None:
        """Pins the BL-017 integrity guard's precondition directly.

        ``agent.coordinator._select_upserted_entities`` raises ``ValueError``
        if any ``GraphUpsertResult.upserted_entity_ids`` is missing from the
        validation report's ``valid_entities`` — this is what the guard checks,
        exercised through the real models via JSON round-trip.
        """
        entity_ids = ["provider:1", "provider:2", "provider:3"]
        graph_update = GraphUpsertResult.model_validate_json(
            trigger.build_graph_upsert_result(
                knowledge_base_id="kb-1",
                trigger_id="demo-trigger-x",
                entity_ids=entity_ids,
                now=_now(),
            ).model_dump_json()
        )
        validation_report = ValidationReport.model_validate_json(
            trigger.build_validation_report(
                trigger_id="demo-trigger-x",
                entity_type="provider",
                entity_ids=entity_ids,
                now=_now(),
            ).model_dump_json()
        )
        validation_ids = {entity.id for entity in validation_report.valid_entities}
        assert set(graph_update.upserted_entity_ids) <= validation_ids

    def test_graph_updated_event_references_both_artifacts(self) -> None:
        event = trigger.build_graph_updated_event(
            knowledge_base_id="kb-1",
            trigger_id="demo-trigger-x",
            entity_count=2,
            graph_update_storage_key="graph-updates/kb-1/demo-trigger-x.json",
            validation_storage_key="validations/kb-1/demo-trigger-x.json",
        )
        assert event.event_type == "graph.updated"
        assert event.correlation_id == "demo-trigger-x"
        assert len(event.documents) == 1
        document = event.documents[0]
        assert document.knowledge_base_id == "kb-1"
        assert document.upserted_entity_count == 2
        assert document.upserted_relationship_count == 0
        assert (
            document.graph_update_storage_key
            == "graph-updates/kb-1/demo-trigger-x.json"
        )
        assert document.validation_storage_key == "validations/kb-1/demo-trigger-x.json"


class TestBuildObjectStore:
    def test_omitted_storage_section_falls_back_to_in_memory(self) -> None:
        # medicare_fraud.yaml has no `storage:` key. DomainConfig's
        # post-validator fills a default ObjectStoreConfig() in that case
        # (config.storage is never actually None after real loading) — an
        # all-defaults section is the real "unconfigured" signal.
        config = load_config(CONFIG_DIR / "medicare_fraud.yaml")
        assert config.storage == ObjectStoreConfig()
        store = trigger.build_object_store(config)
        assert isinstance(store, InMemoryObjectStore)

    def test_local_backend_selects_the_local_fs_adapter(
        self, tmp_path: Path
    ) -> None:
        config = load_config(CONFIG_DIR / "medicare_fraud_cms_desynpuf.yaml")
        assert config.storage is not None
        assert config.storage.backend == "local"
        # The real pack pins the in-container path /app/data/objects; retarget
        # to a host-writable tmp dir for the test while keeping everything
        # else from the real config.
        storage_config = config.storage.model_copy(
            update={"base_path": str(tmp_path)}
        )
        config = config.model_copy(update={"storage": storage_config})
        store = trigger.build_object_store(config)
        assert isinstance(store, LocalFsObjectStore)

    def test_s3_and_minio_backends_select_the_s3_adapter(self) -> None:
        base_config = load_config(CONFIG_DIR / "medicare_fraud_cms_desynpuf.yaml")
        assert base_config.storage is not None
        for backend in ("s3", "minio"):
            storage_config = base_config.storage.model_copy(
                update={"backend": backend, "bucket": "demo-bucket"}
            )
            config = base_config.model_copy(update={"storage": storage_config})
            store = trigger.build_object_store(config)
            assert isinstance(store, S3ObjectStore)


class TestEventBusSettings:
    def test_uses_the_active_packs_stream_prefix(self) -> None:
        config = load_config(CONFIG_DIR / "medicare_fraud_cms_desynpuf.yaml")
        assert config.events is not None
        settings = trigger.event_bus_settings(config, redis_url="redis://redis:6379")
        assert settings.backend == "redis"
        assert settings.redis_url == "redis://redis:6379"
        assert settings.stream_prefix == config.events.stream_prefix

    def test_falls_back_to_chili_prefix_when_events_section_is_unset(self) -> None:
        # DomainConfig's post-validator always fills a default EventBusConfig
        # (whose default stream_prefix already happens to be "chili"), so
        # config.events is never actually None after real loading. Construct
        # that case directly — model_copy does not re-run validators — to
        # exercise _event_bus_settings' defensive None-fallback branch.
        config = load_config(CONFIG_DIR / "medicare_fraud_cms_desynpuf.yaml")
        config_without_events = config.model_copy(update={"events": None})
        settings = trigger.event_bus_settings(
            config_without_events, redis_url="redis://redis:6379"
        )
        assert settings.stream_prefix == "chili"


class TestParseArgs:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("CHILI_API_URL", raising=False)
        args = trigger.parse_args(["--kb", "kb-1"])
        assert args.kb == "kb-1"
        assert args.top == 3
        assert args.redis_url == "redis://localhost:6379"
        assert args.api_url == trigger.DEFAULT_API_URL
        assert args.entity_type == trigger.DEFAULT_ENTITY_TYPE

    def test_overrides_and_env_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://redis:6379")
        args = trigger.parse_args(["--kb", "kb-1", "--top", "5"])
        assert args.top == 5
        assert args.redis_url == "redis://redis:6379"


class TestMain:
    """``main()`` end-to-end with fakes — no redis, no docker, no real HTTP.

    ``load_active_config``, ``build_object_store``, ``select_top_risk_entity_ids``,
    and ``create_event_bus`` are monkeypatched on the ``trigger`` module (Python
    resolves each by name from the module's globals at call time, so patching
    the module attribute redirects every call ``main()`` makes). The object
    store and event bus fakes are the *real* in-memory adapters
    (``InMemoryObjectStore``, ``InMemoryEventBus``) rather than hand-rolled
    mocks, so the assertions below round-trip through real ``put_bytes``/
    ``get_bytes``/``publish`` behavior, not a stub's approximation of it.
    """

    def _fake_config(self) -> DomainConfig:
        return load_config(CONFIG_DIR / "medicare_fraud_cms_desynpuf.yaml")

    def test_happy_path_stages_artifacts_and_publishes_event(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        object_store = InMemoryObjectStore()
        event_bus = InMemoryEventBus()
        fake_config = self._fake_config()

        def fake_load_active_config() -> DomainConfig:
            return fake_config

        def fake_build_object_store(config: DomainConfig) -> ObjectStore:
            assert config is fake_config
            return object_store

        def fake_select_top_risk_entity_ids(
            client: httpx.Client, *, kb_id: str, entity_type: str, top: int
        ) -> list[str]:
            assert kb_id == "kb-1"
            assert entity_type == "provider"
            assert top == 2
            return ["provider:1", "provider:2"]

        def fake_create_event_bus(settings: EventBusSettings) -> EventBus:
            assert settings.redis_url == "redis://redis:6379"
            return event_bus

        monkeypatch.setattr(trigger, "load_active_config", fake_load_active_config)
        monkeypatch.setattr(trigger, "build_object_store", fake_build_object_store)
        monkeypatch.setattr(
            trigger, "select_top_risk_entity_ids", fake_select_top_risk_entity_ids
        )
        monkeypatch.setattr(trigger, "create_event_bus", fake_create_event_bus)

        exit_code = trigger.main(
            ["--kb", "kb-1", "--top", "2", "--redis-url", "redis://redis:6379"]
        )

        assert exit_code == 0
        assert len(event_bus.published_events) == 1
        event = event_bus.published_events[0]
        assert isinstance(event, GraphUpdatedEvent)
        assert len(event.documents) == 1
        document = event.documents[0]
        assert document.knowledge_base_id == "kb-1"
        assert document.upserted_entity_count == 2
        assert document.upserted_relationship_count == 0
        assert document.graph_update_storage_key is not None
        assert document.validation_storage_key is not None
        assert document.graph_update_storage_key == f"graph-updates/kb-1/{event.correlation_id}.json"
        assert document.validation_storage_key == f"validations/kb-1/{event.correlation_id}.json"

        graph_update = GraphUpsertResult.model_validate_json(
            object_store.get_bytes(document.graph_update_storage_key).content
        )
        assert graph_update.upserted_entity_ids == ["provider:1", "provider:2"]
        assert graph_update.knowledge_base_id == "kb-1"

        validation_report = ValidationReport.model_validate_json(
            object_store.get_bytes(document.validation_storage_key).content
        )
        assert {entity.id for entity in validation_report.valid_entities} == {
            "provider:1",
            "provider:2",
        }

        captured = capsys.readouterr()
        assert "demo analytics trigger: kb=kb-1" in captured.out
        assert "entity_ids=['provider:1', 'provider:2']" in captured.out
        assert f"correlation_id={event.correlation_id}" in captured.out

    def test_no_risk_scores_exits_1_without_publishing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        object_store = InMemoryObjectStore()
        fake_config = self._fake_config()

        def fake_load_active_config() -> DomainConfig:
            return fake_config

        def fake_build_object_store(config: DomainConfig) -> ObjectStore:
            return object_store

        def fake_select_top_risk_entity_ids(
            client: httpx.Client, *, kb_id: str, entity_type: str, top: int
        ) -> list[str]:
            return []

        def unexpected_create_event_bus(settings: EventBusSettings) -> EventBus:
            raise AssertionError(
                "create_event_bus must not be called when there are no risk scores"
            )

        monkeypatch.setattr(trigger, "load_active_config", fake_load_active_config)
        monkeypatch.setattr(trigger, "build_object_store", fake_build_object_store)
        monkeypatch.setattr(
            trigger, "select_top_risk_entity_ids", fake_select_top_risk_entity_ids
        )
        monkeypatch.setattr(trigger, "create_event_bus", unexpected_create_event_bus)

        exit_code = trigger.main(["--kb", "kb-1"])

        assert exit_code == 1
        assert object_store.list_keys("") == []
        captured = capsys.readouterr()
        assert "No 'provider' risk scores found for KB kb-1; nothing to trigger." in captured.err
