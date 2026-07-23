"""Tests for the feature-attribution seam: `NoopFeatureAttributor` + `ShapRiskAttributor`."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import ModuleType
from typing import cast

import pytest

from analytics.explainability.adapters.shap_attribution import (
    NoopFeatureAttributor,
    ShapRiskAttributor,
)
from analytics.explainability.models import (
    ExplanationContext,
    ExplanationItem,
    ExplanationSubgraph,
)
from analytics.explainability.protocols import FeatureAttributorProtocol
from shared.types import Alert, FeatureAttribution


def _context(scores: dict[str, float]) -> ExplanationContext:
    return ExplanationContext(
        knowledge_base_id="kb-1",
        alert=Alert(
            id="alert-1",
            entity_type="provider",
            entity_id="p-1",
            severity="high",
            title="Outlier provider",
            reasoning="Elevated composite risk score.",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        explanation_items=[
            ExplanationItem(
                source_id="s-1",
                source_type="risk_factor",
                quote="quote",
                rationale="rationale",
                score=0.5,
            )
        ],
        subgraph=ExplanationSubgraph(node_ids=["p-1"]),
        confidence=0.5,
        scores=scores,
    )


class TestNoopFeatureAttributor:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(NoopFeatureAttributor(), FeatureAttributorProtocol)

    def test_always_returns_empty_list(self) -> None:
        attributor = NoopFeatureAttributor()

        result = attributor.attribute(context=_context({"a": 0.3, "overall": 0.3}))

        assert result == []


class TestShapRiskAttributorConformance:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(ShapRiskAttributor(), FeatureAttributorProtocol)


class TestShapRiskAttributorDegrade:
    def test_no_non_overall_scores_returns_empty_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        attributor = ShapRiskAttributor()

        with caplog.at_level(logging.WARNING):
            result = attributor.attribute(context=_context({"overall": 0.5}))

        assert result == []
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_loader_raising_import_error_degrades(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _failing_loader() -> tuple[ModuleType, ModuleType]:
            raise ImportError("shap is not installed")

        attributor = ShapRiskAttributor(loader=_failing_loader)

        with caplog.at_level(logging.WARNING):
            result = attributor.attribute(
                context=_context({"a": 0.3, "b": 0.2, "overall": 0.5})
            )

        assert result == []
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_explainer_exception_degrades(self, caplog: pytest.LogCaptureFixture) -> None:
        class _ExplodingExplainer:
            def __call__(self, matrix: object) -> object:
                raise RuntimeError("boom")

        class _FakeShapModule:
            def Explainer(self, model: object, background: object) -> object:
                return _ExplodingExplainer()

        class _FakeNumpyModule:
            def array(self, data: object) -> object:
                return data

            def zeros(self, shape: tuple[int, int]) -> object:
                return [[0.0] * shape[1] for _ in range(shape[0])]

            def minimum(self, bound: float, values: object) -> object:
                return values

        def _fake_loader() -> tuple[ModuleType, ModuleType]:
            return (
                cast(ModuleType, _FakeShapModule()),
                cast(ModuleType, _FakeNumpyModule()),
            )

        attributor = ShapRiskAttributor(loader=_fake_loader)

        with caplog.at_level(logging.WARNING):
            result = attributor.attribute(
                context=_context({"a": 0.3, "b": 0.2, "overall": 0.5})
            )

        assert result == []
        assert any(record.levelno == logging.WARNING for record in caplog.records)


class _FakeExplanation:
    def __init__(self, values: list[list[float]]) -> None:
        self.values = values


class _FakeExplainerInstance:
    def __init__(self, values: list[list[float]]) -> None:
        self._values = values
        self.calls: list[object] = []

    def __call__(self, matrix: object) -> _FakeExplanation:
        self.calls.append(matrix)
        return _FakeExplanation(self._values)


class _FakeShapModuleHappy:
    def __init__(self, values: list[list[float]]) -> None:
        self._values = values
        self.constructed_with: list[tuple[object, object]] = []

    def Explainer(self, model: object, background: object) -> _FakeExplainerInstance:
        self.constructed_with.append((model, background))
        return _FakeExplainerInstance(self._values)


class _FakeNumpyModule:
    def array(self, data: object) -> object:
        return data

    def zeros(self, shape: tuple[int, int]) -> object:
        return [[0.0] * shape[1] for _ in range(shape[0])]

    def minimum(self, bound: float, values: object) -> object:
        return values


class TestShapRiskAttributorHappyPath:
    def test_happy_path_returns_sorted_attributions(self) -> None:
        # Scores sorted by key: a, b, c -> fake SHAP contributions below.
        fake_shap = _FakeShapModuleHappy(values=[[0.1, -0.5, 0.2]])
        fake_numpy = _FakeNumpyModule()

        def _fake_loader() -> tuple[ModuleType, ModuleType]:
            return cast(ModuleType, fake_shap), cast(ModuleType, fake_numpy)

        attributor = ShapRiskAttributor(loader=_fake_loader)

        result = attributor.attribute(
            context=_context({"a": 0.3, "b": 0.2, "c": 0.4, "overall": 0.9})
        )

        assert [item.feature_name for item in result] == ["b", "c", "a"]
        assert result[0].contribution == pytest.approx(-0.5)
        assert result[1].contribution == pytest.approx(0.2)
        assert result[2].contribution == pytest.approx(0.1)
        for item in result:
            assert isinstance(item, FeatureAttribution)
            assert item.rationale == (
                "SHAP attribution of the linear risk composite for "
                f"{item.feature_name}."
            )
        assert len(fake_shap.constructed_with) == 1


@pytest.mark.integration
class TestShapRiskAttributorIntegration:
    def test_real_shap_attributions_sum_to_predict_delta(self) -> None:
        pytest.importorskip("shap")
        pytest.importorskip("numpy")

        attributor = ShapRiskAttributor()

        result = attributor.attribute(
            context=_context({"a": 0.3, "b": 0.2, "overall": 0.5})
        )

        assert result != []
        total_contribution = sum(item.contribution for item in result)
        assert total_contribution == pytest.approx(0.5, abs=1e-3)
        for item in result:
            assert item.contribution > 0.0
